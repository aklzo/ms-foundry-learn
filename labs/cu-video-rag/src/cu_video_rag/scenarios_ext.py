"""コアシナリオ拡張(9 本)— 形態の多様化。

- 6〜10: ナレーション付き UI 操作(新ドメイン 5 本。既存動画と語彙が被る誘導あり)
- 11〜12: **無音・テロップのみ**(書き起こしが空になる = 構成 A では原理的に索引不能)
- 13:     **スライド講義型**(UI 操作なし)
- 14:     **長尺 3 章構成**(約 3 分。セグメント分割の質を見る)

narration="" のステップは無音(テロップの読み時間で表示秒数が決まる)。
"""

from __future__ import annotations

from .scenarios import Scenario, Step

SCENARIOS_EXT: list[Scenario] = [
    # ============================== 6. 社内 Wi-Fi(vpn-setup と語彙が被る)
    Scenario(
        id="wifi-8021x",
        title="スマートフォンを社内 Wi-Fi に接続する",
        app_name="Wi-Fi 設定",
        screen_only_facts={"ssid": "CORP-SECURE-5G"},
        steps=[
            Step(
                "スマートフォンを社内の無線ネットワークに接続する手順を説明します。設定アプリから Wi-Fi を開いてください。",
                [
                    {"op": "screen", "title": "Wi-Fi 設定", "subtitle": "利用可能なネットワーク"},
                    {"op": "list", "items": ["CORP-SECURE-5G", "CORP-GUEST", "その他のネットワーク"]},
                ],
            ),
            Step(
                "接続先は、画面の一覧に表示されている社内用のネットワーク名を選んでください。ゲスト用とは別ですので注意してください。",
                [
                    {"op": "click", "label": "CORP-SECURE-5G"},
                    {"op": "note", "text": "社内用 SSID: CORP-SECURE-5G"},
                ],
            ),
            Step(
                "認証画面では社員番号とパスワードを入力します。証明書の確認を求められたら、信頼するを選択してください。",
                [
                    {"op": "screen", "title": "ネットワーク認証", "subtitle": "CORP-SECURE-5G"},
                    {"op": "show_fields", "items": [
                        {"label": "ID(社員番号)", "value": "E12345"},
                        {"label": "パスワード", "value": "●●●●●●●●●●"},
                    ]},
                    {"op": "dialog", "title": "証明書の確認", "lines": ["radius.corp.example", "信頼しますか?"]},
                ],
            ),
            Step(
                "接続済みと表示されれば完了です。繋がらない場合は、機内モードになっていないかを確認し、一度このネットワークの設定を削除してからやり直してください。",
                [
                    {"op": "close_dialog"},
                    {"op": "toast", "text": "CORP-SECURE-5G に接続済み"},
                ],
            ),
        ],
    ),
    # ============================== 7. 勤怠の打刻修正(expense-apply と語彙が被る)
    Scenario(
        id="kintai-fix",
        title="勤怠システムで打刻を修正する",
        app_name="勤怠管理システム",
        screen_only_facts={"deadline": "毎月 5 日"},
        steps=[
            Step(
                "打刻を忘れたときの修正申請の手順を説明します。勤怠管理システムにサインインして、打刻修正メニューを開いてください。",
                [
                    {"op": "screen", "title": "勤怠管理システム", "subtitle": "ホーム"},
                    {"op": "list", "items": ["出退勤打刻", "打刻修正", "休暇申請"]},
                    {"op": "click", "label": "打刻修正"},
                ],
            ),
            Step(
                "修正したい日付を選び、正しい出勤時刻と修正理由を入力します。理由は具体的に書いてください。",
                [
                    {"op": "screen", "title": "打刻修正申請", "subtitle": ""},
                    {"op": "show_fields", "items": [
                        {"label": "対象日", "value": "2026/08/28"},
                        {"label": "正しい出勤時刻", "value": "09:00"},
                        {"label": "修正理由", "value": "入館時に打刻端末が故障していたため"},
                    ]},
                ],
            ),
            Step(
                "申請すると上長の承認に回ります。月の締め処理の期限は画面の注意書きを確認して、それまでに申請を済ませてください。",
                [
                    {"op": "click", "label": "申請"},
                    {"op": "note", "text": "締め処理: 毎月 5 日まで"},
                    {"op": "toast", "text": "申請を送信しました"},
                ],
            ),
            Step(
                "差し戻された場合は、コメントを確認して理由を書き直し、再申請してください。以上で打刻修正の手順は終わりです。",
                [{"op": "toast", "text": "手順は以上です"}],
            ),
        ],
    ),
    # ============================== 8. メール署名と自動返信
    Scenario(
        id="mail-signature",
        title="メール署名と不在時の自動返信を設定する",
        app_name="メール設定",
        screen_only_facts={"template": "テンプレート T-03"},
        steps=[
            Step(
                "メールの署名と、休暇中の自動返信を設定する手順を説明します。メールアプリの設定から署名の管理を開いてください。",
                [
                    {"op": "screen", "title": "メール設定", "subtitle": "署名の管理"},
                    {"op": "list", "items": ["署名の管理", "自動返信", "転送ルール"]},
                ],
            ),
            Step(
                "署名は会社標準のテンプレートを使います。一覧から画面に表示されている標準テンプレートを選んで、自分の部署名に書き換えてください。",
                [
                    {"op": "dialog", "title": "標準テンプレート", "lines": ["テンプレート T-03(社外向け標準)", "部署名は各自で変更"]},
                ],
            ),
            Step(
                "次に自動返信です。不在期間の開始日と終了日を設定し、返信文には戻り予定日と緊急連絡先を書いてください。",
                [
                    {"op": "close_dialog"},
                    {"op": "screen", "title": "自動返信の設定", "subtitle": ""},
                    {"op": "show_fields", "items": [
                        {"label": "開始日", "value": "2026/09/10"},
                        {"label": "終了日", "value": "2026/09/12"},
                        {"label": "返信文", "value": "9/13 に戻ります。緊急時は代表番号へ…"},
                    ]},
                ],
            ),
            Step(
                "保存したら、自分宛てにテストメールを送って署名と自動返信を確認してください。以上で設定は完了です。",
                [
                    {"op": "click", "label": "保存"},
                    {"op": "toast", "text": "設定を保存しました"},
                ],
            ),
        ],
    ),
    # ============================== 9. ファイルサーバーのアクセス権申請
    Scenario(
        id="fileserver-access",
        title="共有フォルダのアクセス権を申請する",
        app_name="アクセス申請ポータル",
        screen_only_facts={"sla": "3 営業日"},
        steps=[
            Step(
                "共有フォルダが開けないときのアクセス権申請の手順を説明します。アクセス申請ポータルを開いて、新規申請を選んでください。",
                [
                    {"op": "screen", "title": "アクセス申請ポータル", "subtitle": "ホーム"},
                    {"op": "click", "label": "新規申請"},
                ],
            ),
            Step(
                "開きたいフォルダのパスを貼り付け、権限の種類を選びます。編集が必要ない場合は読み取りを選んでください。",
                [
                    {"op": "screen", "title": "アクセス権申請", "subtitle": ""},
                    {"op": "show_fields", "items": [
                        {"label": "フォルダパス", "value": "\\\\fs01\\営業部\\提案書"},
                        {"label": "権限", "value": "読み取り"},
                        {"label": "申請理由", "value": "異動に伴い過去提案書の参照が必要"},
                    ]},
                ],
            ),
            Step(
                "申請はフォルダの管理者が承認します。承認までの目安の日数は画面の案内を確認してください。",
                [
                    {"op": "click", "label": "申請"},
                    {"op": "note", "text": "承認まで: 3 営業日"},
                    {"op": "toast", "text": "申請 #AR-1024 を送信しました"},
                ],
            ),
            Step(
                "承認後は一度サインアウトしてサインインし直すと権限が反映されます。開けない場合はヘルプデスクに問い合わせてください。以上で手順は終わりです。",
                [{"op": "toast", "text": "手順は以上です"}],
            ),
        ],
    ),
    # ============================== 10. ウイルス対策のフルスキャン
    Scenario(
        id="antivirus-scan",
        title="ウイルス対策ソフトでフルスキャンを実行する",
        app_name="エンドポイント保護",
        screen_only_facts={"retention": "30 日"},
        steps=[
            Step(
                "ウイルス対策ソフトでパソコン全体をスキャンする手順を説明します。タスクトレイからエンドポイント保護を開いてください。",
                [
                    {"op": "screen", "title": "エンドポイント保護", "subtitle": "保護の状態: 有効"},
                    {"op": "list", "items": ["クイックスキャン", "フルスキャン", "隔離されたファイル"]},
                ],
            ),
            Step(
                "フルスキャンを選んで開始します。時間がかかるので、退勤前など業務に影響しない時間帯に実行してください。",
                [
                    {"op": "click", "label": "フルスキャン"},
                    {"op": "toast", "text": "スキャンを実行中… 12%"},
                ],
            ),
            Step(
                "脅威が見つかったファイルは自動で隔離されます。隔離されたファイルが保存される期間は、画面の説明を確認してください。",
                [
                    {"op": "dialog", "title": "隔離の設定", "lines": ["隔離ファイルの保持期間: 30 日", "期間を過ぎると自動削除"]},
                ],
            ),
            Step(
                "業務で使うファイルが誤って隔離された場合は、自分で復元せずに、ヘルプデスクへ復元申請を出してください。以上でスキャンの手順は終わりです。",
                [
                    {"op": "close_dialog"},
                    {"op": "toast", "text": "手順は以上です"},
                ],
            ),
        ],
    ),
    # ============================== 11. ショートカット集(無音・テロップのみ)
    Scenario(
        id="shortcut-tips",
        title="業務効率化ショートカット集",
        app_name="操作テクニック集",
        screen_only_facts={"screenshot_key": "Win + Shift + S", "clipboard_key": "Win + V"},
        steps=[
            Step(
                "",
                [
                    {"op": "screen", "title": "業務効率化ショートカット集", "subtitle": "音声なし・字幕でご覧ください"},
                    {"op": "caption", "text": "よく使うショートカットを 3 つ紹介します"},
                ],
            ),
            Step(
                "",
                [
                    {"op": "screen", "title": "範囲を指定してスクリーンショット", "subtitle": ""},
                    {"op": "dialog", "title": "Win + Shift + S", "lines": ["画面の一部を選択して撮影", "撮影後はクリップボードに保存される"]},
                    {"op": "caption", "text": "範囲指定のスクリーンショットは Win + Shift + S"},
                ],
            ),
            Step(
                "",
                [
                    {"op": "close_dialog"},
                    {"op": "screen", "title": "クリップボードの履歴", "subtitle": ""},
                    {"op": "dialog", "title": "Win + V", "lines": ["過去にコピーした内容を一覧から貼り付け", "初回は履歴を有効化する"]},
                    {"op": "caption", "text": "クリップボード履歴は Win + V で開けます"},
                ],
            ),
            Step(
                "",
                [
                    {"op": "close_dialog"},
                    {"op": "screen", "title": "ウィンドウの切り替え", "subtitle": ""},
                    {"op": "dialog", "title": "Alt + Tab", "lines": ["開いているウィンドウを素早く切り替え"]},
                    {"op": "caption", "text": "ウィンドウ切り替えは Alt + Tab。以上です"},
                ],
            ),
        ],
    ),
    # ============================== 12. 紙詰まり対処(無音・テロップのみ。printer-duplex と被る)
    Scenario(
        id="paper-jam",
        title="複合機の紙詰まり対処",
        app_name="複合機パネル",
        screen_only_facts={"error_code": "J-02", "cover": "カバー B", "contact": "内線 1200"},
        steps=[
            Step(
                "",
                [
                    {"op": "screen", "title": "複合機パネル", "subtitle": "3F 複合機"},
                    {"op": "error", "code": "紙詰まり J-02", "text": "本体右側のカバー B を開けてください"},
                    {"op": "caption", "text": "紙詰まりエラー J-02 が表示されたら"},
                ],
            ),
            Step(
                "",
                [
                    {"op": "close_dialog"},
                    {"op": "screen", "title": "手順 1: カバー B を開ける", "subtitle": "本体右側のレバーを引く"},
                    {"op": "caption", "text": "本体右側のレバーを引いてカバー B を開けます"},
                ],
            ),
            Step(
                "",
                [
                    {"op": "screen", "title": "手順 2: 用紙を取り除く", "subtitle": "矢印の方向へゆっくり引き抜く"},
                    {"op": "caption", "text": "詰まった用紙は矢印の方向へゆっくり引き抜きます(破らないこと)"},
                ],
            ),
            Step(
                "",
                [
                    {"op": "screen", "title": "手順 3: カバーを閉じる", "subtitle": "エラー表示が消えれば復旧完了"},
                    {"op": "toast", "text": "エラーが解除されました"},
                    {"op": "caption", "text": "カバーを閉じてエラーが消えれば完了。直らない場合は内線 1200 へ"},
                ],
            ),
        ],
    ),
    # ============================== 13. セキュリティ研修(スライド講義型)
    Scenario(
        id="security-basics",
        title="情報セキュリティ基礎研修",
        app_name="社内研修",
        screen_only_facts={"contact": "内線 5500"},
        steps=[
            Step(
                "情報セキュリティ基礎研修を始めます。この研修では、パスワードの管理と不審なメールへの対応について学びます。",
                [
                    {"op": "slide", "title": "情報セキュリティ基礎研修", "bullets": ["対象: 全社員", "所要時間: 約 3 分", "内容: パスワード管理 / 不審メール対応"]},
                ],
            ),
            Step(
                "まずパスワードの管理です。パスワードは使い回さず、システムごとに変えてください。付箋に書いて貼るのは禁止です。",
                [
                    {"op": "slide", "title": "パスワード管理の原則", "bullets": ["使い回しをしない", "紙に書いて貼らない", "パスワードマネージャーの利用を推奨"]},
                ],
            ),
            Step(
                "次に不審なメールへの対応です。心当たりのない添付ファイルは開かず、リンクも押さないでください。受信したら、スライドに記載の窓口へすぐ連絡してください。",
                [
                    {"op": "slide", "title": "不審メールを受け取ったら", "bullets": ["添付を開かない・リンクを押さない", "転送せずそのまま保全", "連絡先: セキュリティ窓口 内線 5500"]},
                ],
            ),
            Step(
                "最後にまとめです。少しでも不審に思ったら、自分で判断せずに必ず相談してください。以上で研修を終わります。",
                [
                    {"op": "slide", "title": "まとめ", "bullets": ["迷ったら相談", "報告は減点にならない", "初動の速さが被害を減らす"]},
                ],
            ),
        ],
    ),
    # ============================== 14. 新入社員オリエン(長尺 3 章)
    Scenario(
        id="newhire-orientation",
        title="新入社員 IT オリエンテーション",
        app_name="IT セットアップガイド",
        screen_only_facts={"initial_pw_expiry": "24 時間", "helpdesk": "内線 1234"},
        steps=[
            Step(
                "新入社員向けに、パソコンの初期設定をひととおり説明します。アカウントの初期設定、メールの設定、プリンタの登録の順に進めます。",
                [
                    {"op": "screen", "title": "IT セットアップガイド", "subtitle": "全 3 章"},
                    {"op": "list", "items": ["第 1 章 アカウント初期設定", "第 2 章 メール設定", "第 3 章 プリンタ登録"]},
                ],
            ),
            Step(
                "第一章、アカウントの初期設定です。入社時に配られた用紙の初期パスワードでサインインしてください。初期パスワードの有効期限は画面の注意書きを確認してください。",
                [
                    {"op": "click", "label": "第 1 章 アカウント初期設定"},
                    {"op": "screen", "title": "第 1 章: アカウント初期設定", "subtitle": "初回サインイン"},
                    {"op": "note", "text": "初期パスワードの有効期限: 発行から 24 時間"},
                ],
            ),
            Step(
                "サインインできたら、すぐに自分のパスワードへ変更します。変更後は多要素認証のアプリを登録してください。",
                [
                    {"op": "show_fields", "items": [
                        {"label": "新しいパスワード", "value": "●●●●●●●●●●●●●"},
                        {"label": "多要素認証", "value": "認証アプリを登録済み"},
                    ]},
                    {"op": "toast", "text": "パスワードを変更しました"},
                ],
            ),
            Step(
                "第二章、メールの設定です。メールアプリを開くと自動で設定が始まります。表示名は姓名をそのまま使ってください。",
                [
                    {"op": "screen", "title": "第 2 章: メール設定", "subtitle": "自動セットアップ"},
                    {"op": "show_fields", "items": [
                        {"label": "メールアドレス", "value": "e12345@corp.example"},
                        {"label": "表示名", "value": "山田 太郎"},
                    ]},
                ],
            ),
            Step(
                "署名は会社標準のテンプレートが自動で入ります。テストとして、隣の席の先輩にメールを送ってみてください。",
                [
                    {"op": "click", "label": "テスト送信"},
                    {"op": "toast", "text": "テストメールを送信しました"},
                ],
            ),
            Step(
                "第三章、プリンタの登録です。設定アプリからプリンタの追加を開くと、自分のフロアの複合機が一覧に出ます。",
                [
                    {"op": "screen", "title": "第 3 章: プリンタ登録", "subtitle": "プリンタの追加"},
                    {"op": "dialog", "title": "検出されたプリンタ", "lines": ["3F 複合機", "4F 複合機"]},
                ],
            ),
            Step(
                "自分のフロアの複合機を選んでインストールします。印刷の初期設定は両面のモノクロになっています。",
                [
                    {"op": "close_dialog"},
                    {"op": "show_fields", "items": [
                        {"label": "選択中", "value": "3F 複合機"},
                        {"label": "初期設定", "value": "両面・モノクロ"},
                    ]},
                ],
            ),
            Step(
                "以上で初期設定は完了です。途中でうまくいかない場合の問い合わせ先は、画面に表示されているヘルプデスクの内線番号へ連絡してください。",
                [
                    {"op": "screen", "title": "セットアップ完了", "subtitle": "おつかれさまでした"},
                    {"op": "note", "text": "ヘルプデスク: 内線 1234"},
                    {"op": "toast", "text": "全 3 章が完了しました"},
                ],
            ),
        ],
    ),
]


# コア拡張シナリオの評価クエリ(24 問。type: N/S/C は scenarios.py と同義)
QUERIES_EXT: list[dict] = [
    {"qid": "E01", "type": "N", "text": "社内 Wi-Fi の認証画面では何を入力する?", "video": "wifi-8021x", "expected_step": 2, "ref_answer": "社員番号とパスワードを入力し、証明書の確認では信頼するを選ぶ。"},
    {"qid": "E02", "type": "S", "text": "社内用 Wi-Fi の SSID(ネットワーク名)は?", "video": "wifi-8021x", "expected_step": 1, "answer": "CORP-SECURE-5G", "ref_answer": "CORP-SECURE-5G(ゲスト用 CORP-GUEST とは別)。"},
    {"qid": "E03", "type": "C", "text": "スマホが社内の無線に繋がらないとき最初に確認することは?", "video": "wifi-8021x", "expected_step": 3, "ref_answer": "機内モードになっていないか確認し、ネットワーク設定を削除して再設定する。"},
    {"qid": "E04", "type": "N", "text": "打刻修正の申請で入力する項目は?", "video": "kintai-fix", "expected_step": 1, "ref_answer": "対象日・正しい出勤時刻・修正理由(具体的に書く)。"},
    {"qid": "E05", "type": "S", "text": "勤怠の締め処理はいつまでに申請が必要?", "video": "kintai-fix", "expected_step": 2, "answer": "毎月 5 日", "ref_answer": "毎月 5 日の締め処理まで(画面の注意書きに表示)。"},
    {"qid": "E06", "type": "C", "text": "勤怠の申請が差し戻されたらどうする?", "video": "kintai-fix", "expected_step": 3, "ref_answer": "コメントを確認して理由を書き直し、再申請する。"},
    {"qid": "E07", "type": "N", "text": "不在時の自動返信の文面には何を書く?", "video": "mail-signature", "expected_step": 2, "ref_answer": "戻り予定日と緊急連絡先を書く。"},
    {"qid": "E08", "type": "S", "text": "メール署名の会社標準テンプレートの番号は?", "video": "mail-signature", "expected_step": 1, "answer": "T-03", "ref_answer": "テンプレート T-03(社外向け標準)。"},
    {"qid": "E09", "type": "N", "text": "共有フォルダの権限申請で編集が不要な場合は何を選ぶ?", "video": "fileserver-access", "expected_step": 1, "ref_answer": "読み取り権限を選ぶ。"},
    {"qid": "E10", "type": "S", "text": "アクセス権の申請から承認まで何日かかる?", "video": "fileserver-access", "expected_step": 2, "answer": "3 営業日", "ref_answer": "目安 3 営業日(画面の案内に表示)。"},
    {"qid": "E11", "type": "N", "text": "アクセス権が承認された後に権限を反映させるには?", "video": "fileserver-access", "expected_step": 3, "ref_answer": "一度サインアウトしてサインインし直す。"},
    {"qid": "E12", "type": "N", "text": "ウイルスのフルスキャンはいつ実行するのがよい?", "video": "antivirus-scan", "expected_step": 1, "ref_answer": "退勤前など業務に影響しない時間帯。"},
    {"qid": "E13", "type": "S", "text": "隔離されたファイルは何日で自動削除される?", "video": "antivirus-scan", "expected_step": 2, "answer": "30 日", "ref_answer": "保持期間 30 日を過ぎると自動削除される。"},
    {"qid": "E14", "type": "N", "text": "業務ファイルが誤って隔離されたときの対応は?", "video": "antivirus-scan", "expected_step": 3, "ref_answer": "自分で復元せず、ヘルプデスクへ復元申請を出す。"},
    {"qid": "E15", "type": "S", "text": "範囲を指定してスクリーンショットを撮るショートカットキーは?", "video": "shortcut-tips", "expected_step": 1, "answer": "Win + Shift + S", "ref_answer": "Win + Shift + S(撮影後はクリップボードに保存)。"},
    {"qid": "E16", "type": "S", "text": "クリップボードの履歴を開くショートカットキーは?", "video": "shortcut-tips", "expected_step": 2, "answer": "Win + V", "ref_answer": "Win + V(初回は履歴の有効化が必要)。"},
    {"qid": "E17", "type": "S", "text": "複合機の紙詰まりのとき開けるカバーはどれ?", "video": "paper-jam", "expected_step": 1, "answer": "カバー B", "ref_answer": "本体右側のレバーを引いてカバー B を開ける。"},
    {"qid": "E18", "type": "C", "text": "複合機で紙が詰まったときの最初の操作は?", "video": "paper-jam", "expected_step": 1, "ref_answer": "本体右側のカバー B を開ける(エラー J-02 の対処)。"},
    {"qid": "E19", "type": "N", "text": "パスワード管理で禁止されていることは?", "video": "security-basics", "expected_step": 1, "ref_answer": "使い回しと、紙(付箋)に書いて貼ること。"},
    {"qid": "E20", "type": "S", "text": "不審なメールを受け取ったときの連絡先は?", "video": "security-basics", "expected_step": 2, "answer": "内線 5500", "ref_answer": "セキュリティ窓口(内線 5500)へすぐ連絡する。"},
    {"qid": "E21", "type": "S", "text": "新入社員の初期パスワードの有効期限は?", "video": "newhire-orientation", "expected_step": 1, "answer": "24 時間", "ref_answer": "発行から 24 時間(画面の注意書きに表示)。"},
    {"qid": "E22", "type": "N", "text": "新入社員のメール設定で表示名はどうする?", "video": "newhire-orientation", "expected_step": 3, "ref_answer": "姓名をそのまま使う。"},
    {"qid": "E23", "type": "C", "text": "新入社員がプリンタを登録する手順は?", "video": "newhire-orientation", "expected_step": 5, "ref_answer": "設定アプリからプリンタの追加を開き、自分のフロアの複合機を選んでインストールする。"},
    {"qid": "E24", "type": "S", "text": "セットアップで困ったときのヘルプデスクの内線番号は?", "video": "newhire-orientation", "expected_step": 7, "answer": "内線 1234", "ref_answer": "ヘルプデスク 内線 1234 へ連絡する。"},
]


# コーパスに根拠が無い質問(U タイプ)。RAG が「分かりません」と棄権できるか(捏造しないか)を
# 測る。retrieval 指標(hit@k 等)の対象外で、rag-answer → 棄権率(abstention)にのみ使う。
# 題材は 26 業務ドメイン+コア 14 本のいずれにも無いものを選んでいる。
QUERIES_UNANSWERABLE: list[dict] = [
    {"qid": "U01", "type": "U", "text": "出張の航空券はどのシステムで手配する?"},
    {"qid": "U02", "type": "U", "text": "社員食堂の支払いに使える決済方法は?"},
    {"qid": "U03", "type": "U", "text": "名刺の追加発注はどこに依頼する?"},
    {"qid": "U04", "type": "U", "text": "育児休業の申請書はどこで入手できる?"},
    {"qid": "U05", "type": "U", "text": "社内図書室の本は何冊まで借りられる?"},
    {"qid": "U06", "type": "U", "text": "制服のサイズ交換は誰に申し出る?"},
    {"qid": "U07", "type": "U", "text": "従業員持株会の拠出額の上限は?"},
    {"qid": "U08", "type": "U", "text": "社内駐車場の月極利用料はいくら?"},
]
for _q in QUERIES_UNANSWERABLE:
    _q["ref_answer"] = "コーパスに根拠が無いため「提供された情報からは分かりません」と答えるのが正しい。"
