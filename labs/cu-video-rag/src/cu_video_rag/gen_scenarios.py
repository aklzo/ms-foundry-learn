"""生成コーパス(90 本)— テンプレートエンジンによる多様なシナリオの量産。

構成(すべて決定的。乱数はシード固定で再現可能):
- 26 業務ドメイン × 手続きタイプ 3 種 = 78 本(ナレーション付き UI 操作)
- 8 本: 無音・テロップのみ(パネル操作手順)
- 4 本: スライド講義型

仕込み(画面のみ情報)の値は **動画インデックスから一意に採番**(内線 5xxx、
ERR-1xx 等)し、100 本規模でも回答値が動画間で衝突しないようにする。
自動生成クエリはナレーションの言い回しと違う表現(パラフレーズ)にする。
"""

from __future__ import annotations

import random

from .scenarios import Scenario, Step

# (key, アプリ名, 対象物, 一覧メニュー, 入力フィールド例)
DOMAINS: list[tuple[str, str, str, list[str], list[dict]]] = [
    ("meetroom", "会議室予約システム", "会議室の予約", ["新規予約", "予約一覧", "設備一覧"], [{"label": "会議室", "value": "7F 大会議室"}, {"label": "日時", "value": "2026/09/05 14:00"}]),
    ("car", "社用車予約システム", "社用車の予約", ["新規予約", "利用実績", "車両一覧"], [{"label": "車両", "value": "プリウス 3 号車"}, {"label": "利用日", "value": "2026/09/08"}]),
    ("elearn", "e-ラーニングシステム", "研修の受講", ["受講一覧", "必須研修", "修了証"], [{"label": "コース", "value": "情報セキュリティ 2026"}, {"label": "期限", "value": "2026/09/30"}]),
    ("contract", "電子契約システム", "契約書の送信", ["新規契約", "承認待ち", "締結済み"], [{"label": "契約書名", "value": "業務委託基本契約"}, {"label": "相手先", "value": "株式会社サンプル"}]),
    ("invoice", "請求書発行システム", "請求書の発行", ["新規作成", "下書き", "送付済み"], [{"label": "請求先", "value": "株式会社サンプル"}, {"label": "金額", "value": "330,000円"}]),
    ("purchase", "購買システム", "備品の発注", ["新規発注", "承認待ち", "納品確認"], [{"label": "品名", "value": "モニター 27 インチ"}, {"label": "数量", "value": "2"}]),
    ("inventory", "備品管理システム", "備品の登録", ["備品登録", "貸出", "棚卸"], [{"label": "備品名", "value": "プロジェクター"}, {"label": "管理番号", "value": "BP-0042"}]),
    ("crm", "顧客管理システム", "顧客情報の登録", ["顧客登録", "商談一覧", "レポート"], [{"label": "会社名", "value": "株式会社サンプル"}, {"label": "担当者", "value": "佐藤 様"}]),
    ("project", "案件管理システム", "案件の登録", ["案件登録", "工数入力", "進捗一覧"], [{"label": "案件名", "value": "基幹システム更改"}, {"label": "開始日", "value": "2026/10/01"}]),
    ("task", "タスク管理ツール", "タスクの割り当て", ["タスク作成", "ボード", "レポート"], [{"label": "タスク名", "value": "見積書レビュー"}, {"label": "担当", "value": "山田"}]),
    ("chat", "ビジネスチャット", "チャンネルの作成", ["チャンネル作成", "メンバー管理", "通知設定"], [{"label": "チャンネル名", "value": "#proj-kikan"}, {"label": "公開範囲", "value": "社内公開"}]),
    ("calendar", "共有カレンダー", "予定の共有", ["予定作成", "共有設定", "会議室連携"], [{"label": "予定", "value": "定例ミーティング"}, {"label": "繰り返し", "value": "毎週火曜"}]),
    ("storage", "オンラインストレージ", "ファイルの共有", ["アップロード", "共有リンク", "ゴミ箱"], [{"label": "ファイル", "value": "提案資料.pptx"}, {"label": "共有先", "value": "営業部"}]),
    ("rdp", "リモートデスクトップ", "社内 PC への接続", ["接続先一覧", "新規接続", "設定"], [{"label": "接続先", "value": "PC-YAMADA-01"}, {"label": "ゲートウェイ", "value": "rdgw.corp.example"}]),
    ("license", "ライセンス管理システム", "ソフトウェアの利用申請", ["利用申請", "割当一覧", "棚卸"], [{"label": "ソフトウェア", "value": "図面作成ツール Pro"}, {"label": "利用期間", "value": "1 年"}]),
    ("asset", "IT 資産管理システム", "資産情報の更新", ["資産検索", "情報更新", "返却申請"], [{"label": "資産番号", "value": "NB-2026-118"}, {"label": "設置場所", "value": "本社 5F"}]),
    ("badge", "入退室管理システム", "入館証の再発行申請", ["再発行申請", "入退室履歴", "臨時入館"], [{"label": "理由", "value": "紛失のため"}, {"label": "受取場所", "value": "総務窓口"}]),
    ("survey", "社内アンケートシステム", "アンケートの作成", ["新規作成", "回答状況", "集計"], [{"label": "タイトル", "value": "職場環境アンケート"}, {"label": "回答期限", "value": "2026/09/19"}]),
    ("payroll", "給与明細システム", "明細の確認", ["最新明細", "過去明細", "源泉徴収票"], [{"label": "対象月", "value": "2026 年 8 月"}, {"label": "形式", "value": "PDF"}]),
    ("benefit", "福利厚生ポータル", "補助の申請", ["補助申請", "申請履歴", "制度一覧"], [{"label": "制度", "value": "書籍購入補助"}, {"label": "金額", "value": "3,200円"}]),
    ("health", "健康診断予約システム", "健診の予約", ["予約", "予約変更", "結果確認"], [{"label": "会場", "value": "本社クリニック"}, {"label": "希望日", "value": "2026/10/14"}]),
    ("safety", "安否確認システム", "安否応答の登録", ["応答登録", "家族設定", "訓練履歴"], [{"label": "状況", "value": "無事"}, {"label": "出社可否", "value": "可能"}]),
    ("portal", "社内ポータル", "お知らせの掲載", ["記事作成", "承認依頼", "公開管理"], [{"label": "タイトル", "value": "年末調整のご案内"}, {"label": "公開日", "value": "2026/11/01"}]),
    ("backup", "バックアップツール", "バックアップの設定", ["バックアップ設定", "復元", "履歴"], [{"label": "対象", "value": "ドキュメントフォルダ"}, {"label": "頻度", "value": "毎日 21:00"}]),
    ("vdi", "仮想デスクトップ", "VDI への接続", ["接続", "再起動", "設定"], [{"label": "デスクトップ", "value": "標準デスクトップ"}, {"label": "画質", "value": "自動"}]),
    ("printacct", "印刷管理システム", "印刷上限の確認", ["利用状況", "上限申請", "部署集計"], [{"label": "今月の印刷", "value": "312 枚"}, {"label": "カラー比率", "value": "18%"}]),
]

# 手続きタイプ: (key, 表示名, ステップビルダー名)
PROCEDURES = ["setup", "request", "config", "trouble", "export", "cancel"]
PROC_LABEL = {
    "setup": "初期設定", "request": "申請", "config": "通知設定の変更",
    "trouble": "トラブル対処", "export": "データのエクスポート", "cancel": "取り消し・変更",
}

# 仕込み(画面のみ情報)の型: (fact_key, 値テンプレート, 表示テンプレート, S クエリ, ref_answer)
FACT_KINDS = [
    ("deadline", "毎月 {n5} 日", "締め切り: 毎月 {n5} 日", "{app}の{task}はいつまでに行えばいい?", "毎月 {n5} 日まで(画面の注意書きに表示)。"),
    ("contact", "内線 {n5000}", "問い合わせ: 内線 {n5000}", "{app}のトラブルはどこに問い合わせればいい?", "内線 {n5000} のサポート窓口へ問い合わせる。"),
    ("code", "ERR-{n100}", "エラーコード ERR-{n100}", "{app}で失敗したときに表示されるエラーコードは?", "エラーコード ERR-{n100} が表示される。"),
    ("limit", "{n2}0 件", "一度に扱える上限: {n2}0 件", "{app}で一度に処理できる件数の上限は?", "上限は {n2}0 件(画面の注意書きに表示)。"),
    ("retention", "{n30} 日間", "保存期間: {n30} 日間", "{app}のデータは何日間保存される?", "{n30} 日間保存される。"),
]


def _fact(i: int) -> dict:
    kind, val_t, disp_t, q_t, a_t = FACT_KINDS[i % len(FACT_KINDS)]
    vals = {"n5": 3 + i % 5, "n5000": 5000 + i, "n100": 100 + i, "n2": 2 + i % 7, "n30": 10 + i % 60}
    return {
        "kind": kind,
        "value": val_t.format(**vals),
        "display": disp_t.format(**vals),
        "query": q_t,
        "ref_answer": a_t.format(**vals),
    }


def _ui_steps(dom: tuple, proc: str, fact: dict | None) -> list[Step]:
    key, app, task, menu, fields = dom
    label = PROC_LABEL[proc]
    steps = [
        Step(
            f"この動画では、{app}での{task}に関する{label}の手順を説明します。まずメニューから{menu[0]}を開いてください。",
            [
                {"op": "screen", "title": app, "subtitle": "ホーム"},
                {"op": "list", "items": menu},
                {"op": "click", "label": menu[0]},
            ],
        ),
        Step(
            "必要な項目を入力します。入力内容は画面の例を参考にしてください。",
            [
                {"op": "screen", "title": f"{menu[0]}", "subtitle": app},
                {"op": "show_fields", "items": fields},
            ],
        ),
    ]
    if proc == "trouble":
        steps.append(
            Step(
                "処理に失敗した場合は、エラーの内容を控えてから、もう一度やり直してください。何度も失敗する場合は画面の案内先へ連絡します。",
                [{"op": "error", "code": fact["display"] if fact and fact["kind"] == "code" else "エラー", "text": "処理を完了できませんでした"}]
                + ([{"op": "note", "text": fact["display"]}] if fact and fact["kind"] != "code" else []),
            )
        )
        steps.append(Step("以上でトラブル時の対処は終わりです。", [{"op": "close_dialog"}, {"op": "toast", "text": "手順は以上です"}]))
    else:
        confirm_ops: list[dict] = [{"op": "click", "label": "確定"}, {"op": "toast", "text": "処理を受け付けました"}]
        if fact:
            confirm_ops.insert(1, {"op": "note", "text": fact["display"]})
        steps.append(
            Step(
                "内容を確認して確定します。制限や期限は画面の注意書きを確認してください。"
                if fact
                else "内容を確認して確定します。",
                confirm_ops,
            )
        )
        steps.append(
            Step(
                f"完了すると通知が届きます。以上で{app}の{label}の手順は終わりです。",
                [{"op": "toast", "text": "手順は以上です"}],
            )
        )
    return steps


def _silent_steps(dom: tuple, fact: dict | None) -> list[Step]:
    key, app, task, menu, fields = dom
    ops1: list[dict] = [
        {"op": "screen", "title": f"{app} クイックガイド", "subtitle": "音声なし・字幕でご覧ください"},
        {"op": "caption", "text": f"{app}で{task}を行う手順です"},
    ]
    ops2: list[dict] = [
        {"op": "screen", "title": menu[0], "subtitle": app},
        {"op": "list", "items": menu},
        {"op": "caption", "text": f"メニューから{menu[0]}を選びます"},
    ]
    ops3: list[dict] = [
        {"op": "show_fields", "items": fields},
        {"op": "caption", "text": "必要な項目を入力して確定します"},
    ]
    if fact:
        ops3.insert(1, {"op": "dialog", "title": "注意", "lines": [fact["display"]]})
    ops4: list[dict] = [
        {"op": "close_dialog"},
        {"op": "toast", "text": "処理を受け付けました"},
        {"op": "caption", "text": "完了メッセージが出れば終了です"},
    ]
    return [Step("", ops1), Step("", ops2), Step("", ops3), Step("", ops4)]


SLIDE_TOPICS = [
    ("slide-backup", "バックアップの重要性", [
        ("なぜバックアップが必要か", ["PC 故障は突然起きる", "ローカル保存のみのファイルは復元不可", "会社データは共有ドライブへ"]),
        ("バックアップの基本ルール", ["重要ファイルは共有ドライブに保存", "個人フォルダは毎日自動バックアップ", "USB メモリの利用は申請制"]),
        ("復元したいときは", ["まず共有ドライブの履歴機能を確認", "見つからない場合は IT 部門へ依頼", "依頼から復元まで 2 営業日"]),
    ]),
    ("slide-phone", "電話応対の基本", [
        ("受けるとき", ["3 コール以内に出る", "部署名と名前を名乗る", "相手の社名・名前を復唱"]),
        ("取り次ぐとき", ["保留にしてから声をかける", "不在時は折り返しを提案", "伝言メモは 5W1H で残す"]),
        ("かけるとき", ["要件を整理してからかける", "昼休みの時間帯は避ける"]),
    ]),
    ("slide-files", "ファイル整理術", [
        ("フォルダ構成の原則", ["案件ごとにフォルダを分ける", "階層は 3 段まで", "個人名フォルダを作らない"]),
        ("ファイル名の付け方", ["日付_案件_内容 の順", "版数は v1, v2 で管理", "「最新」「final」は使わない"]),
        ("定期的な棚卸", ["四半期ごとに不要ファイルを削除", "完了案件はアーカイブへ移動"]),
    ]),
    ("slide-manner", "ビジネスチャットのマナー", [
        ("基本ルール", ["業務連絡はチャンネルで(DM は最小限)", "返信は 1 営業日以内", "スタンプでの既読反応は歓迎"]),
        ("メンションの使い方", ["@all は部署全体の連絡のみ", "個人メンションは要返信のときだけ"]),
        ("トラブル防止", ["機密情報は添付しない", "誤送信に気づいたらすぐ削除して連絡"]),
    ]),
]


def _slide_steps(title: str, slides: list[tuple[str, list[str]]]) -> list[Step]:
    steps = [
        Step(
            f"{title}についての研修を始めます。スライドに沿って説明します。",
            [{"op": "slide", "title": title, "bullets": [f"研修: {title}", "所要時間: 約 2 分"]}],
        )
    ]
    for stitle, bullets in slides:
        narration = f"{stitle}です。" + "。".join(b.rstrip("。") for b in bullets[:2]) + "。詳細はスライドを確認してください。"
        steps.append(Step(narration, [{"op": "slide", "title": stitle, "bullets": bullets}]))
    steps.append(Step("以上で研修を終わります。", [{"op": "slide", "title": "まとめ", "bullets": ["迷ったら担当部門へ相談", "ルールは社内ポータルにも掲載"]}]))
    return steps


def generate_corpus(seed: int = 42) -> tuple[list[Scenario], list[dict]]:
    """(シナリオ 90 本, 自動生成クエリ) を返す。決定的(seed 固定)。"""
    rng = random.Random(seed)
    scenarios: list[Scenario] = []
    queries: list[dict] = []
    qn = 0

    # --- 78 本: ドメイン × 手続き 3 種
    idx = 0
    for d_i, dom in enumerate(DOMAINS):
        procs = [PROCEDURES[(d_i + k) % len(PROCEDURES)] for k in range(3)]
        for proc in procs:
            fact = _fact(idx) if idx % 2 == 0 else None  # 半数に画面のみ情報を仕込む
            sid = f"g{idx:02d}-{dom[0]}-{proc}"
            sc = Scenario(
                id=sid,
                title=f"{dom[1]}: {dom[2]}の{PROC_LABEL[proc]}",
                app_name=dom[1],
                steps=_ui_steps(dom, proc, fact),
                screen_only_facts={fact["kind"]: fact["value"]} if fact else {},
            )
            scenarios.append(sc)
            # 自動クエリ: 3 本に 1 本 S(仕込みあり時)、4 本に 1 本 N
            if fact and idx % 4 in (0, 2):
                qn += 1
                queries.append({
                    "qid": f"GS{qn:02d}", "type": "S",
                    "text": fact["query"].format(app=dom[1], task=dom[2]),
                    "video": sid, "expected_step": 2 if len(sc.steps) > 2 else 1,
                    "answer": fact["value"], "ref_answer": fact["ref_answer"],
                })
            elif idx % 4 == 1:
                qn += 1
                queries.append({
                    "qid": f"GN{qn:02d}", "type": "N",
                    "text": f"{dom[1]}で{dom[2]}の{PROC_LABEL[proc]}を行う最初の操作は?",
                    "video": sid, "expected_step": 0,
                    "ref_answer": f"メニューから{dom[3][0]}を開く。",
                })
            idx += 1

    # --- 8 本: 無音・テロップ(ドメインを 8 つ抽出)
    for k, dom in enumerate(rng.sample(DOMAINS, 8)):
        fact = _fact(80 + k)
        sid = f"s{k:02d}-{dom[0]}-silent"
        scenarios.append(
            Scenario(
                id=sid,
                title=f"{dom[1]} クイックガイド(字幕)",
                app_name=dom[1],
                steps=_silent_steps(dom, fact),
                screen_only_facts={fact["kind"]: fact["value"]},
            )
        )
        if k % 2 == 0:
            qn += 1
            queries.append({
                "qid": f"GV{qn:02d}", "type": "S",
                "text": fact["query"].format(app=dom[1], task=dom[2]) + "(字幕動画)",
                "video": sid, "expected_step": 2,
                "answer": fact["value"], "ref_answer": fact["ref_answer"],
            })

    # --- 4 本: スライド講義
    for k, (skey, title, slides) in enumerate(SLIDE_TOPICS):
        scenarios.append(
            Scenario(
                id=skey,
                title=title,
                app_name="社内研修",
                steps=_slide_steps(title, slides),
                screen_only_facts={},
            )
        )
        qn += 1
        qtype = "S" if skey == "slide-backup" else "N"  # 2 営業日はスライドのみ表示(ナレーション外)
        queries.append({
            "qid": f"GL{qn:02d}", "type": qtype,
            **({"answer": "2 営業日"} if skey == "slide-backup" else {}),
            "text": {"slide-backup": "ファイルの復元依頼から復元までどのくらいかかる?",
                     "slide-phone": "電話は何コール以内に出るのがルール?",
                     "slide-files": "フォルダの階層は何段までにする?",
                     "slide-manner": "@all メンションを使っていいのはどんなとき?"}[skey],
            "video": skey, "expected_step": {"slide-backup": 3, "slide-phone": 1, "slide-files": 1, "slide-manner": 2}[skey],
            "ref_answer": {"slide-backup": "依頼から復元まで 2 営業日。",
                           "slide-phone": "3 コール以内に出る。",
                           "slide-files": "階層は 3 段まで。",
                           "slide-manner": "部署全体への連絡のときのみ。"}[skey],
        })

    return scenarios, queries
