"""Conversations API(Agents v2 のサービス側会話状態)の挙動確認。

maf-ports では会話状態をすべてクライアント側(MAF)で持っていたため、
サービス側の Conversations / Items / Responses の挙動が未検証だった。

観点:
  A. どのサーフェスで使えるか(アカウント openai/v1 vs プロジェクト経由)
  B. 会話の作成 — id 形式・作成時フィールド(TTL/expiry の有無)・metadata
  C. responses.create(conversation=...) で履歴を再送しない多ターン継続
  D. items の記録粒度(ロール・型・ツール呼び出しがどう残るか)
  E. previous_response_id 連鎖(conversation なし)との比較
  F. store=False と conversation の同時指定
  G. 別モデルで同一 conversation を続けられるか
  H. 存在しない conversation id のエラー形
  I. 削除と削除後アクセス
"""

from __future__ import annotations

import sys

from foundry_probes.common import Settings, make_openai_client, make_project_client, section, show


def viewpoint(title):
    def deco(fn):
        fn._title = title
        return fn

    return deco


def run(fn, *args):
    section(fn._title)
    try:
        fn(*args)
    except Exception as exc:  # 失敗も観察対象
        print(f"!! {type(exc).__name__}: {exc}")


def main() -> int:
    settings = Settings.from_env()
    account_client = make_openai_client(settings)  # アカウントの openai/v1
    project = make_project_client(settings)
    project_client = project.get_openai_client()  # プロジェクト経由

    conv_ids: dict[str, str] = {}

    @viewpoint("A. サーフェス: アカウント openai/v1 で conversations.create")
    def a_account_surface():
        conv = account_client.conversations.create(metadata={"probe": "01-account"})
        show("account v1 で作成した conversation", conv)
        conv_ids["account"] = conv.id

    @viewpoint("A'. サーフェス: プロジェクト経由で conversations.create")
    def a_project_surface():
        conv = project_client.conversations.create(metadata={"probe": "01-project"})
        show("project client で作成した conversation", conv)
        conv_ids["project"] = conv.id

    @viewpoint("B. 作成時フィールド(TTL/expiry の有無)")
    def b_fields():
        conv = project_client.conversations.retrieve(conv_ids["project"])
        show("retrieve 結果(生 dict)", conv.model_dump())

    @viewpoint("C. 多ターン継続(履歴を再送しない)")
    def c_multiturn():
        cid = conv_ids["project"]
        r1 = project_client.responses.create(
            model=settings.model, conversation=cid,
            input="私の好きな色は青です。覚えてください。",
        )
        show("turn1 output_text", r1.output_text)
        r2 = project_client.responses.create(
            model=settings.model, conversation=cid,
            input="私の好きな色は何でしたか?色名だけ答えて。",
        )
        show("turn2 output_text(履歴未再送で『青』と答えれば状態保持)", r2.output_text)
        show("turn2 response.conversation", getattr(r2, "conversation", None))

    @viewpoint("D. items の記録粒度")
    def d_items():
        items = project_client.conversations.items.list(conv_ids["project"], limit=20)
        for item in items:
            d = item.model_dump()
            print(f"  type={d.get('type')} role={d.get('role')} id={d.get('id','')[:28]}")
        show("先頭 item の生 dict", next(iter(items)).model_dump(), limit=600)

    @viewpoint("E. previous_response_id 連鎖(conversation なし)")
    def e_prev_id():
        r1 = project_client.responses.create(
            model=settings.model, input="合言葉は『やまびこ』です。覚えて。")
        r2 = project_client.responses.create(
            model=settings.model, previous_response_id=r1.id,
            input="合言葉は?単語だけ答えて。")
        show("chained output_text", r2.output_text)
        print(f"  r1.id={r1.id[:30]} r2.previous_response_id={r2.previous_response_id[:30]}")

    @viewpoint("F. store=False と conversation の同時指定(items に残るか)")
    def f_store_false():
        conv = project_client.conversations.create()
        r = project_client.responses.create(
            model=settings.model, conversation=conv.id,
            input="これは store=False のテストです。", store=False,
        )
        show("store=False の応答 id", r.id)
        items = list(project_client.conversations.items.list(conv.id))
        print(f"  store=False ターン後の items 件数: {len(items)}(0 なら会話にも残らない)")
        project_client.conversations.delete(conv.id)

    @viewpoint("G. 別モデルで同一 conversation 継続")
    def g_cross_model():
        r = project_client.responses.create(
            model="model-router", conversation=conv_ids["project"],
            input="私の好きな色をもう一度。色名だけ。",
        )
        show("model-router での継続 output_text", r.output_text)
        show("実際に使われたモデル", r.model)

    @viewpoint("H. 存在しない conversation id")
    def h_missing():
        project_client.responses.create(
            model=settings.model, conversation="conv_000000000000000000000000",
            input="hello")

    @viewpoint("I. 削除と削除後アクセス")
    def i_delete():
        deleted = project_client.conversations.delete(conv_ids["project"])
        show("delete 結果", deleted)
        project_client.conversations.items.list(conv_ids["project"])

    for fn in (a_account_surface, a_project_surface, b_fields, c_multiturn, d_items,
               e_prev_id, f_store_false, g_cross_model, h_missing, i_delete):
        run(fn)

    # 後片付け(アカウント側)
    try:
        if "account" in conv_ids:
            account_client.conversations.delete(conv_ids["account"])
    except Exception:  # noqa: S110 — 後片付けの失敗は無視してよい
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
