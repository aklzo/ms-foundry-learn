"""File Search + ベクトルストア(GA)の挙動確認。

corrective-rag / db-routing-iq は Azure AI Search を自前で使ったため、
Foundry 組み込みの File Search(埋め込みは text-embedding-3-large@256 固定・
自前デプロイ不要という survey 記載)が未検証だった。

観点:
  A. files.create の purpose と戻り値
  B. vector_stores.create + ファイル追加 → チャンク設定の既定値(800/400 か)
  C. インデックス完了までのポーリング挙動
  D. responses.create + file_search ツールで根拠つき回答(2 ファイルの出し分け)
  E. 引用(annotations)の形
  F. expires_after(会話由来ストア 7 日失効の一般化: 明示 TTL を設定できるか)
  G. 後片付け(store 削除でファイルはどうなるか)
"""

from __future__ import annotations

import io
import sys
import time

from foundry_probes.common import Settings, make_project_client, section, show

DOC_A = """製品コード ZR-100 は月見電機の家庭用ロボット掃除機である。
稼働時間は 180 分、集塵容量は 0.6 リットル。2025 年 4 月発売。
ZR-100 の保証期間は購入日から 3 年間である。"""

DOC_B = """製品コード KW-55 は月見電機の加湿器である。
タンク容量は 4.2 リットル、適用床面積は 19 畳。2024 年 11 月発売。
KW-55 の保証期間は購入日から 1 年間である。"""


def main() -> int:
    settings = Settings.from_env()
    project = make_project_client(settings)
    client = project.get_openai_client()

    section("A. files.create(purpose の受理)")
    f_a = client.files.create(file=("zr100.txt", io.BytesIO(DOC_A.encode())), purpose="assistants")
    f_b = client.files.create(file=("kw55.txt", io.BytesIO(DOC_B.encode())), purpose="assistants")
    show("file A", f_a.model_dump())

    section("B. vector_stores.create + ファイル追加(チャンク既定値)")
    store = client.vector_stores.create(name="probe-store")
    show("store 作成直後", store.model_dump())
    vf = client.vector_stores.files.create(vector_store_id=store.id, file_id=f_a.id)
    client.vector_stores.files.create(vector_store_id=store.id, file_id=f_b.id)
    show("store file(chunking_strategy 既定)", vf.model_dump())

    section("C. インデックス完了までのポーリング")
    t0 = time.monotonic()
    while True:
        s = client.vector_stores.retrieve(store.id)
        print(f"  {time.monotonic()-t0:5.1f}s status={s.status} counts={s.file_counts.model_dump()}")
        if s.status != "in_progress" and s.file_counts.in_progress == 0:
            break
        if time.monotonic() - t0 > 120:
            print("  !! 120s タイムアウト")
            break
        time.sleep(3)

    section("D. file_search ツールで出し分け質問")
    r = client.responses.create(
        model=settings.model,
        tools=[{"type": "file_search", "vector_store_ids": [store.id]}],
        input="ZR-100 の保証期間は?ファイルの根拠に基づいて一文で。",
    )
    show("output_text(3 年間と答えれば正解)", r.output_text)
    for item in r.output:
        print(f"  output item type={item.type}")

    section("E. 引用(annotations)の形")
    msg = next((i for i in r.output if i.type == "message"), None)
    if msg is not None:
        content = msg.content[0].model_dump()
        show("message content(annotations)", content, limit=1200)

    section("F. expires_after(明示 TTL)")
    try:
        s2 = client.vector_stores.create(
            name="probe-store-ttl", expires_after={"anchor": "last_active_at", "days": 1}
        )
        show("TTL つき store", {"id": s2.id, "expires_after": s2.expires_after, "expires_at": s2.expires_at})
        client.vector_stores.delete(s2.id)
    except Exception as exc:
        print(f"!! {type(exc).__name__}: {exc}")

    section("G. 後片付け(store 削除後のファイル残存)")
    client.vector_stores.delete(store.id)
    try:
        remaining = client.files.retrieve(f_a.id)
        print(f"  store 削除後もファイルは残る: {remaining.id}(files.delete が別途必要)")
    except Exception as exc:
        print(f"  store 削除でファイルも消えた? {type(exc).__name__}: {exc}")
    for fid in (f_a.id, f_b.id):
        try:
            client.files.delete(fid)
        except Exception:  # noqa: S110 — 後片付けの失敗は無視してよい
            pass
    print("  files.delete 済み")
    return 0


if __name__ == "__main__":
    sys.exit(main())
