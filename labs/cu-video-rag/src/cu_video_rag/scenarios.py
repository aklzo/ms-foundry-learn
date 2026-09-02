"""検証用データセットの定義(台本・画面操作・評価クエリ)= 本ラボの ground truth。

設計方針(docs/design.md):
- 5 本の「社内 IT 操作研修動画」。日本語ナレーション+日本語 UI
- 各ステップ = (ナレーション 1〜2 文, 画面操作の宣言的リスト)。ナレーション全文が
  書き起こしの正解(CER 測定)、ステップ境界の実時刻が検索評価の正解時間範囲になる
- **画面のみ情報(screen_only_facts)**: ナレーションでは言わず画面にだけ出す事実。
  「書き起こしのみ」構成では原理的に検索不能 → 視覚理解(セグメント記述)の寄与を
  分離測定する仕掛け
- 動画 1(VPN)と 5(Web 会議)は「接続・切断」語彙を意図的に共有し、検索の
  紛らわしさを作る(C タイプのクエリで評価)

CU のフレーム制約(約 1 FPS・512×512 縮小 = 小さい文字が落ちる)を踏まえ、
画面のみ情報はダイアログの大きな文字で表示する(それでも落ちるかが検証項目)。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Step:
    narration: str
    ops: list[dict] = field(default_factory=list)


@dataclass
class Scenario:
    id: str
    title: str
    app_name: str
    steps: list[Step]
    screen_only_facts: dict[str, str] = field(default_factory=dict)  # 説明用(正解の根拠)


SCENARIOS: list[Scenario] = [
    # ================================================== 1. VPN 接続設定
    Scenario(
        id="vpn-setup",
        title="社外から VPN に接続する",
        app_name="リモートアクセスポータル",
        screen_only_facts={
            "server_address": "vpn.contoso-jp.example",  # ナレーションでは「画面のアドレス」とだけ言う
            "error_code": "809",
        },
        steps=[
            Step(
                "この動画では、社外のネットワークから社内システムへ VPN 接続する手順を説明します。まずデスクトップのリモートアクセスポータルを開いてください。",
                [
                    {"op": "screen", "title": "リモートアクセスポータル", "subtitle": "社外接続メニュー"},
                    {"op": "list", "items": ["VPN 接続", "接続状態の確認", "利用マニュアル"]},
                ],
            ),
            Step(
                "メニューから VPN 接続を選びます。接続先サーバーには、画面に表示されているアドレスをそのまま入力してください。",
                [
                    {"op": "click", "label": "VPN 接続"},
                    {"op": "screen", "title": "VPN 接続設定", "subtitle": "新しい接続を作成"},
                    {"op": "show_fields", "items": [
                        {"label": "接続先サーバー", "value": "vpn.contoso-jp.example"},
                        {"label": "接続名", "value": "社内VPN"},
                    ]},
                    {"op": "note", "text": "接続先サーバー: vpn.contoso-jp.example"},
                ],
            ),
            Step(
                "サインインには社員番号と、いつものパスワードを使います。ワンタイムコードの入力を求められたら、スマートフォンの認証アプリの数字を入力してください。",
                [
                    {"op": "show_fields", "items": [
                        {"label": "社員番号", "value": "E12345"},
                        {"label": "パスワード", "value": "●●●●●●●●●●"},
                        {"label": "ワンタイムコード", "placeholder": "認証アプリの 6 桁"},
                    ]},
                ],
            ),
            Step(
                "入力できたら接続ボタンを押します。ステータスが接続済みになれば完了です。",
                [
                    {"op": "click", "label": "接続"},
                    {"op": "toast", "text": "ステータス: 接続済み"},
                ],
            ),
            Step(
                "もし接続に失敗してエラーが表示された場合は、自宅のルーターを再起動してから、もう一度接続を試してください。",
                [
                    {"op": "error", "code": "エラー 809", "text": "接続がタイムアウトしました"},
                ],
            ),
            Step(
                "それでも繋がらない場合は、パスワードを最近変更していないか確認し、資格情報を入力し直してください。以上で VPN 接続の手順は終わりです。",
                [
                    {"op": "close_dialog"},
                    {"op": "toast", "text": "手順は以上です"},
                ],
            ),
        ],
    ),
    # ================================================== 2. パスワード再設定
    Scenario(
        id="password-reset",
        title="パスワードの再設定",
        app_name="アカウント管理センター",
        screen_only_facts={
            "policy": "12文字以上・記号を1つ以上",  # ナレーションでは「画面の要件」とだけ言う
        },
        steps=[
            Step(
                "パスワードを忘れたときの再設定手順を説明します。アカウント管理センターを開いて、パスワードを忘れた場合、をクリックしてください。",
                [
                    {"op": "screen", "title": "アカウント管理センター", "subtitle": "サインイン"},
                    {"op": "list", "items": ["サインイン", "パスワードを忘れた場合"]},
                    {"op": "click", "label": "パスワードを忘れた場合"},
                ],
            ),
            Step(
                "本人確認のため、社員番号と生年月日を入力します。続いて、社給スマートフォンに届く確認コードを入力してください。",
                [
                    {"op": "screen", "title": "本人確認", "subtitle": "アカウントの確認"},
                    {"op": "show_fields", "items": [
                        {"label": "社員番号", "value": "E12345"},
                        {"label": "生年月日", "value": "1990/04/01"},
                        {"label": "確認コード", "placeholder": "SMS の 6 桁"},
                    ]},
                ],
            ),
            Step(
                "新しいパスワードを決めます。文字数と使える記号の条件は、画面に表示されている要件を確認してください。",
                [
                    {"op": "screen", "title": "新しいパスワードの設定", "subtitle": ""},
                    {"op": "dialog", "title": "パスワード要件", "lines": ["12文字以上", "記号を1つ以上含める"]},
                ],
            ),
            Step(
                "要件を満たすパスワードを二回入力し、変更ボタンを押します。",
                [
                    {"op": "close_dialog"},
                    {"op": "show_fields", "items": [
                        {"label": "新しいパスワード", "value": "●●●●●●●●●●●●●"},
                        {"label": "新しいパスワード(確認)", "value": "●●●●●●●●●●●●●"},
                    ]},
                    {"op": "click", "label": "変更"},
                ],
            ),
            Step(
                "パスワードを変えた直後は、社給スマートフォンのメール同期が一度エラーになることがあります。その場合はスマートフォン側でも新しいパスワードを入力し直してください。以上で再設定は完了です。",
                [
                    {"op": "toast", "text": "パスワードを変更しました"},
                ],
            ),
        ],
    ),
    # ================================================== 3. プリンタ追加と両面印刷
    Scenario(
        id="printer-duplex",
        title="プリンタの追加と両面印刷の設定",
        app_name="プリンタ設定",
        screen_only_facts={
            "driver_name": "PR-8600 Series",  # ナレーションでは「一覧のドライバー」とだけ言う
        },
        steps=[
            Step(
                "オフィスの複合機で印刷するための設定手順を説明します。設定アプリからプリンタとスキャナーを開いてください。",
                [
                    {"op": "screen", "title": "プリンタとスキャナー", "subtitle": "設定"},
                    {"op": "list", "items": ["プリンタの追加", "既定のプリンタ", "印刷キュー"]},
                ],
            ),
            Step(
                "プリンタの追加をクリックすると、社内ネットワークの複合機が一覧に表示されます。自分のフロアの複合機を選び、一覧に表示されたドライバーをそのままインストールしてください。",
                [
                    {"op": "click", "label": "プリンタの追加"},
                    {"op": "dialog", "title": "検出されたプリンタ", "lines": ["3F 複合機", "ドライバー: PR-8600 Series"]},
                ],
            ),
            Step(
                "インストールが終わったら、印刷設定を開いて、両面印刷を長辺とじに変更します。会社の規定で、社内資料は両面印刷が標準です。",
                [
                    {"op": "close_dialog"},
                    {"op": "screen", "title": "印刷設定", "subtitle": "3F 複合機"},
                    {"op": "show_fields", "items": [
                        {"label": "両面印刷", "value": "長辺とじ"},
                        {"label": "カラーモード", "value": "モノクロ"},
                    ]},
                ],
            ),
            Step(
                "最後にテストページを印刷して、両面で出力されることを確認してください。印刷できない場合は、印刷キューを開いて、詰まっているジョブを削除してから試し直します。以上で設定は完了です。",
                [
                    {"op": "click", "label": "テストページを印刷"},
                    {"op": "toast", "text": "テストページを送信しました"},
                ],
            ),
        ],
    ),
    # ================================================== 4. 経費精算の申請(ノイズドメイン)
    Scenario(
        id="expense-apply",
        title="経費精算の申請",
        app_name="経費精算システム",
        screen_only_facts={
            "limit": "50,000円",  # ナレーションでは「画面の上限額」とだけ言う
        },
        steps=[
            Step(
                "この動画では、立て替えた経費を精算する手順を説明します。経費精算システムにサインインして、新規申請ボタンを押してください。",
                [
                    {"op": "screen", "title": "経費精算システム", "subtitle": "ホーム"},
                    {"op": "click", "label": "新規申請"},
                ],
            ),
            Step(
                "申請の種類は交通費、日付と金額、行き先を入力します。一回の申請で入力できる上限額は画面の注意書きを確認してください。",
                [
                    {"op": "screen", "title": "新規申請", "subtitle": "交通費"},
                    {"op": "show_fields", "items": [
                        {"label": "日付", "value": "2026/08/28"},
                        {"label": "金額", "value": "1,240円"},
                        {"label": "行き先", "value": "顧客先(品川)"},
                    ]},
                    {"op": "note", "text": "1 回の申請上限: 50,000円"},
                ],
            ),
            Step(
                "領収書はスマートフォンで撮影して、ファイルを添付します。画像がぼやけていると差し戻しになるので注意してください。",
                [
                    {"op": "click", "label": "領収書を添付"},
                    {"op": "toast", "text": "receipt_0828.jpg を添付しました"},
                ],
            ),
            Step(
                "入力が終わったら申請ボタンを押します。承認者は自動で上長に設定されます。差し戻された場合は、コメントを確認して修正のうえ再申請してください。以上で経費精算の手順は終わりです。",
                [
                    {"op": "click", "label": "申請"},
                    {"op": "toast", "text": "申請 #20260828-012 を送信しました"},
                ],
            ),
        ],
    ),
    # ================================================== 5. Web 会議の画面共有(1 と語彙が被る)
    Scenario(
        id="meeting-share",
        title="Web 会議での画面共有とマイク設定",
        app_name="会議アプリ",
        screen_only_facts={
            "bandwidth": "2 Mbps",  # ナレーションでは「画面の推奨値」とだけ言う
        },
        steps=[
            Step(
                "Web 会議で画面共有がうまくいかないときの設定手順を説明します。会議に接続したら、まず画面下の共有ボタンをクリックしてください。",
                [
                    {"op": "screen", "title": "会議アプリ", "subtitle": "会議中: 定例ミーティング"},
                    {"op": "list", "items": ["ミュート", "カメラ", "共有", "退出"]},
                    {"op": "click", "label": "共有"},
                ],
            ),
            Step(
                "共有する対象は、デスクトップ全体ではなく、見せたいウィンドウだけを選ぶのが基本です。資料のウィンドウを選んで共有を開始します。",
                [
                    {"op": "dialog", "title": "共有する内容を選択", "lines": ["ウィンドウ: 提案資料.pptx", "デスクトップ全体"]},
                    {"op": "close_dialog"},
                    {"op": "toast", "text": "提案資料.pptx を共有中"},
                ],
            ),
            Step(
                "映像がカクカクする場合は、ネットワークの帯域が足りていません。画面に表示される推奨値を目安に、有線接続への切り替えを検討してください。",
                [
                    {"op": "error", "code": "帯域警告", "text": "推奨帯域: 2 Mbps 以上"},
                ],
            ),
            Step(
                "自分の声が相手に聞こえない場合は、設定からマイクのデバイスを確認します。ヘッドセットを接続し直して、正しいデバイスを選び直してください。",
                [
                    {"op": "close_dialog"},
                    {"op": "screen", "title": "デバイス設定", "subtitle": "音声"},
                    {"op": "show_fields", "items": [
                        {"label": "マイク", "value": "ヘッドセット (USB)"},
                        {"label": "スピーカー", "value": "ヘッドセット (USB)"},
                    ]},
                ],
            ),
            Step(
                "会議が終わったら、共有の停止を忘れずに押してから退出してください。以上で画面共有の手順は終わりです。",
                [
                    {"op": "click", "label": "共有を停止"},
                    {"op": "toast", "text": "共有を停止しました"},
                ],
            ),
        ],
    ),
]


# ================================================== 評価クエリ(正解ラベルつき)
# type: N = ナレーション由来 / S = 画面のみ情報(書き起こしでは原理的に不可) /
#       C = 紛らわしい(横断語彙の切り分け)
# expected_step は 0 始まり。検索評価では該当動画ヒット(hit@k)と、トップチャンクの
# 時間範囲が正解ステップ時刻と重なるか(segment hit)を測る。
QUERIES: list[dict] = [
    # --- N: ナレーション由来
    {"qid": "N01", "type": "N", "text": "VPN 接続でワンタイムコードはどこの数字を入力する?", "video": "vpn-setup", "expected_step": 2, "ref_answer": "スマートフォンの認証アプリに表示される 6 桁の数字を入力する。"},
    {"qid": "N02", "type": "N", "text": "VPN が繋がらないときに最初に試すことは?", "video": "vpn-setup", "expected_step": 4, "ref_answer": "自宅のルーターを再起動してから、もう一度接続を試す。"},
    {"qid": "N03", "type": "N", "text": "パスワード再設定の本人確認では何を入力する?", "video": "password-reset", "expected_step": 1, "ref_answer": "社員番号と生年月日を入力し、SMS の確認コードを入力する。"},
    {"qid": "N04", "type": "N", "text": "パスワード変更後にスマホのメールがエラーになったらどうする?", "video": "password-reset", "expected_step": 4, "ref_answer": "スマートフォン側でも新しいパスワードを入力し直す。"},
    {"qid": "N05", "type": "N", "text": "社内資料の印刷で標準とされている設定は?", "video": "printer-duplex", "expected_step": 2, "ref_answer": "両面印刷(長辺とじ)が標準。"},
    {"qid": "N06", "type": "N", "text": "印刷できないときは何を削除すればよい?", "video": "printer-duplex", "expected_step": 3, "ref_answer": "印刷キューを開いて、詰まっているジョブを削除する。"},
    {"qid": "N07", "type": "N", "text": "領収書の添付で差し戻しになるのはどんな場合?", "video": "expense-apply", "expected_step": 2, "ref_answer": "領収書の画像がぼやけている場合に差し戻しになる。"},
    {"qid": "N08", "type": "N", "text": "経費申請の承認者は誰に設定される?", "video": "expense-apply", "expected_step": 3, "ref_answer": "承認者は自動で上長に設定される。"},
    {"qid": "N09", "type": "N", "text": "画面共有では何を共有するのが基本?", "video": "meeting-share", "expected_step": 1, "ref_answer": "デスクトップ全体ではなく、見せたいウィンドウだけを共有する。"},
    {"qid": "N10", "type": "N", "text": "自分の声が相手に聞こえないときの確認手順は?", "video": "meeting-share", "expected_step": 3, "ref_answer": "設定からマイクのデバイスを確認し、ヘッドセットを接続し直して正しいデバイスを選ぶ。"},
    # --- S: 画面のみ情報(ナレーションに存在しない)
    {"qid": "S01", "type": "S", "text": "VPN の接続先サーバーのアドレスは?", "answer": "vpn.contoso-jp.example", "video": "vpn-setup", "expected_step": 1, "ref_answer": "vpn.contoso-jp.example(画面に表示)。"},
    {"qid": "S02", "type": "S", "text": "VPN 接続失敗時に表示されるエラー番号は?", "answer": "809", "video": "vpn-setup", "expected_step": 4, "ref_answer": "エラー 809(接続タイムアウト)。"},
    {"qid": "S03", "type": "S", "text": "新しいパスワードは何文字以上にする必要がある?", "answer": "12文字以上", "video": "password-reset", "expected_step": 2, "ref_answer": "12 文字以上・記号を 1 つ以上含める。"},
    {"qid": "S04", "type": "S", "text": "複合機のプリンタドライバーの型番は?", "answer": "PR-8600", "video": "printer-duplex", "expected_step": 1, "ref_answer": "PR-8600 Series。"},
    {"qid": "S05", "type": "S", "text": "経費精算で 1 回に申請できる上限金額は?", "answer": "50,000円", "video": "expense-apply", "expected_step": 1, "ref_answer": "50,000 円(1 回の申請上限)。"},
    {"qid": "S06", "type": "S", "text": "Web 会議で推奨されるネットワーク帯域は何 Mbps?", "answer": "2 Mbps", "video": "meeting-share", "expected_step": 2, "ref_answer": "2 Mbps 以上が推奨帯域。"},
    # --- C: 紛らわしい(vpn-setup と meeting-share の「接続」語彙の切り分け)
    {"qid": "C01", "type": "C", "text": "会議の映像がカクカクするときはどうすればいい?", "video": "meeting-share", "expected_step": 2, "ref_answer": "ネットワーク帯域が不足しているので、有線接続への切り替えを検討する。"},
    {"qid": "C02", "type": "C", "text": "接続がタイムアウトしたときにルーターをどうする?", "video": "vpn-setup", "expected_step": 4, "ref_answer": "自宅のルーターを再起動する。"},
    {"qid": "C03", "type": "C", "text": "会議から抜ける前に忘れずに押すボタンは?", "video": "meeting-share", "expected_step": 4, "ref_answer": "共有を停止ボタンを押してから退出する。"},
    {"qid": "C04", "type": "C", "text": "サインインで社員番号と一緒に使う認証アプリは何のため?", "video": "vpn-setup", "expected_step": 2, "ref_answer": "多要素認証のワンタイムコードを発行するため。"},
]
