---
marp: true
theme: si-foundry
paginate: true
footer: "Microsoft Foundry SI 勉強会 — 詳細: docs/survey/ 配下(各スライド下部のリンク参照)"
---

<!-- _class: lead -->
<!-- _paginate: false -->
<!-- _footer: "" -->

# Microsoft Foundry を SI で使う

## 技術選定とアーキテクチャ判断の基準

2026-08 / 課内勉強会
本リポジトリの調査(survey)+実装検証(labs)の入口となる資料

<!-- 発表の位置づけ: 課内で Foundry を調査した人はいるが情報が未集約、プロジェクト事例がなくアーキ検討に困っている、という状況への回答。この資料は全体の入口で、詳細はすべて survey の HTML に整備済み、と最初に伝える。 -->

---

<!-- header: "§0 はじめに" -->

# 今日のゴール

<div class="msg">持ち帰るのは機能の知識ではなく、3 つの「判断能力」</div>

<div class="cards c3">
<div class="card"><div class="t">① 決める順序</div>後戻りコストの大きい順に<br><b>5 つのゲート(G1〜G5)</b>で閉じる</div>
<div class="card"><div class="t">② 当たりの付け方</div>要件の言葉を<br><b>22 パターン+選定 3 軸</b>に当てて 1〜2 案に絞る</div>
<div class="card"><div class="t">③ 見積もりの現実</div><b>「やってくれないこと」と廃止期限</b>を工数・リスクに乗せる</div>
</div>

- 全機能の暗記は不要 — 「**どこを見れば載っているか**」が分かれば提案は書ける
- 略語は初出でスペルアウトし、巻末の**付録 A7 に用語集**を用意した

<div class="refs">2 層目の全体像: <a href="../survey/README.md">survey/README.md</a> — <span class="path">docs/survey/README.md</span></div>

<!-- ゴールは知識の網羅ではなく判断力。3 つの判断能力を最後にもう一度出すので、ここでは骨組みだけ覚えてもらえばよい。以降のセクション §2 が①、§3〜§4 が②、§5 が③に対応する。 -->

---

# 資料の全体像(2 層構成)

<div class="msg">この資料は入口(1 層目)— 詳細は 2 層目の調査資産に降りられる</div>

<div class="flow">
<div class="st" style="flex:1.2"><span class="t">このスライド(1 層目)</span><br>判断の骨組みだけを 45 分で</div>
<span class="arr">→</span>
<div class="st"><span class="t">features</span><br>その機能は<b>使えるのか</b><br>GA(一般提供)/ プレビューを約 200 機能・出典つきで。<b>月次更新</b></div>
<div class="st"><span class="t">architecture</span><br><b>どう組むか</b><br>公式リファレンス+ユースケース別パターン+運用・移行。<b>四半期更新</b></div>
<div class="st"><span class="t">proposal</span><br><b>どう提案するか</b><br>ヒアリング・コスト手順・日本規制・公開事例</div>
<div class="st"><span class="t">labs+選定ガイド</span><br>実装で<b>実証できたこと</b><br>動くコード 14 本+テスト約 470 件</div>
</div>

- 各スライドの下部に、該当する 2 層目へのリンクとリポジトリ内パスを常設してある
- 「公式ドキュメント調査(survey)」と「実装検証(labs)」は**出典を分離** — 提案書で根拠を二本立てにできる

<div class="refs">詳細: <a href="../survey/features/html/index.html">features</a> / <a href="../survey/architecture/html/index.html">architecture</a> / <a href="../survey/proposal/html/index.html">proposal</a> / <a href="../tech-selection-guide.md">tech-selection-guide</a> — <span class="path">docs/survey/README.md</span></div>

<!-- どの資料がどの問いに答えるかだけ覚えてもらう。features は「使えるか」、architecture は「どう組むか」、proposal は「どう提案するか」。労力の大半は 2 層目に既に積んであり、このスライドは道案内に徹する。 -->

---

<!-- header: "§1 Foundry の現在地" -->

# 前提: Ignite 2025 の改称

<div class="msg">検索で出てくる情報の大半は旧名義 — 新旧対応表を頭に入れて読む</div>

| 観点 | 旧 | 現行 |
|---|---|---|
| ブランド | Azure AI Studio / Azure AI Foundry | **Microsoft Foundry** |
| 付帯 AI サービス | Azure AI Services | **Foundry Tools** |
| エージェント API | Assistants API(Threads / Runs) | **Responses API(Agents v2)** |
| リソースモデル | Hub + Azure OpenAI + AI Services | **Foundry リソース**(単一) |
| SDK | `azure-ai-inference` 等 複数 | **`azure-ai-projects` 2.x + `openai`** |
| ドキュメント | /azure/ai-foundry/ | **/azure/foundry/**(新)+ /azure/foundry-classic/(旧) |

- 対応表なしで検索すると、**廃止済み API の記事で設計してしまう**(メンバーの過去調査も旧名義の可能性)

<div class="refs">詳細: <a href="../survey/features/html/index.html">features/index(前提知識の節)</a> — <span class="path">docs/survey/features/README.md</span></div>

<!-- 調査情報が未集約になる一因がこの改称。「Azure AI Foundry」で検索して出てくる記事はほぼ旧世代。読み替え表として使ってもらう。 -->

---

# 機能の全体像(8 カテゴリ)

<div class="msg">全機能は 8 カテゴリの「地図」に整理済み — 位置だけ覚えれば引ける</div>

<div class="cards c4">
<div class="card"><div class="t">01 プラットフォーム基盤</div>リソース / プロジェクト / アクセス制御 / ネットワーク / IaC(コード化したインフラ)</div>
<div class="card"><div class="t">02 モデル</div>カタログ(OpenAI / Claude / Grok 等)/ デプロイタイプ / Model router / Foundry Local</div>
<div class="card"><div class="t">03 Agent Service</div>Agents v2(Responses API)/ prompt・hosted エージェント / Memory / Routines</div>
<div class="card"><div class="t">04 ツール・ナレッジ</div>File Search / AI Search / Web search / MCP / Foundry IQ</div>
<div class="card"><div class="t">05 観測・評価</div>トレーシング / 評価器 / クラウド評価 / AI Red Teaming</div>
<div class="card"><div class="t">06 ガードレール</div>コンテンツフィルター / Prompt Shields / 根拠性検出 / 個人情報検出</div>
<div class="card"><div class="t">07 Foundry Tools</div>Speech(Voice Live)/ Document Intelligence / Content Understanding</div>
<div class="card"><div class="t">08 開発者サーフェス</div>v1 API / SDK / CLI / Bicep / Microsoft Agent Framework / LangGraph 統合</div>
</div>

- 各カテゴリとも GA / プレビュー+操作手段(ポータル / CLI / SDK / REST)を**全行出典つき**で整理済み

<div class="refs">詳細: <a href="../survey/features/html/index.html">features/index</a> — <span class="path">docs/survey/features/01〜08-*.md</span></div>

<!-- 個々の機能はこの場で覚えなくてよい。「この 8 分類のどこかに載っている」と分かればよい。番号は features のファイル番号と一致している。 -->

---

# GA / プレビューの現実

<div class="msg">「GA」を鵜呑みにしない — 選定に効く 4 つの現実</div>

<div class="cards c2">
<div class="card"><div class="t">① GA / プレビューは機能単位で混在</div>新ポータル自体は GA でも中身はバラバラ。体系的な一覧は公式 <b>Feature readiness at GA</b> が唯一 — 提案前に必ず引く</div>
<div class="card"><div class="t">② GA でも足元の基盤が動いている</div>hosted エージェントは 2026-08-20 に初期基盤終了(再デプロイ必須)、ビジュアル Workflows は 2026-12-01 廃止</div>
<div class="card"><div class="t">③ CLI は一級市民ではない</div>専用の <code>az foundry</code> は存在しない。多くの機能が「ポータル+SDK / REST のみ」— 自動化の見積もりに直接効く</div>
<div class="card"><div class="t">④ Claude(Anthropic)は独自制約つき</div>モデルとしては GA。ただし Anthropic SDK+Marketplace 課金+<b>Foundry 組み込みコンテンツフィルター非適用</b></div>
</div>

<div class="refs">詳細: <a href="../survey/features/html/index.html">features/index(ハイライトの節)</a> — <span class="path">docs/survey/features/README.md</span></div>

<!-- この 4 点は提案の失敗パターンに直結する。特に④フィルター非適用の Claude と②Workflows 廃止は後のスライドでも繰り返し出てくる。GA=一般提供、SLA つきの正式リリースという意味も一言添える。 -->

---

# 公式リファレンスアーキテクチャ

<div class="msg">公式リファレンスは 3 本だけ — 本番の出発点は Baseline Chat 一択</div>

![bg right:42% fit](../survey/architecture/images/baseline-chat.png)

<div class="cards" style="grid-template-columns:1fr">
<div class="card"><span class="chip gray">公式-A</span><b>Basic Chat</b> — PoC(概念実証)専用。記事自身が本番非推奨と明言</div>
<div class="card"><span class="chip">公式-B</span><b>Baseline Chat(図 →)</b> — 本番の出発点。Well-Architected Framework(設計原則集)が推奨と名指し</div>
<div class="card"><span class="chip gray">公式-C</span><b>Landing Zones 版</b> — 全社共通基盤(hub-spoke)向け。実装コードは削除済み・プレビュー</div>
</div>

- それ以外の公式ページは検証レベルが下がる — **提案での引用時は区別する**

<div class="refs">詳細: <a href="../survey/architecture/html/01-official-baselines.html">architecture/01-official-baselines</a> — <span class="path">docs/survey/architecture/01-official-baselines.md</span></div>

<!-- 「公式の推奨構成はどれか」と聞かれたら Baseline 一択。公式-B は Well-Architected Framework が「AI ワークロードの推奨アーキテクチャ」と名指ししている。それ以外の「ガイド」「ソリューションアイデア」を事例記事と同様にリファレンスとして引用しない、という区別が提案の信頼性を作る。図は Baseline Chat の構成図。 -->

---

<!-- header: "§2 判断①: 決める順序" -->

# 判断①: 5 つのゲート

<div class="msg">構成の決定は「後戻りコストの大きい順」— 5 つのゲートを上から閉じる</div>

<div class="gates">
<div class="axislabel">後戻りコスト 大 ▲</div>
<div class="gate g1"><span class="g">G1 データ・規制</span><span>そのデータを、どこで、誰に処理させてよいか</span><span>モデル・デプロイタイプ・外部ツール可否が決まる</span></div>
<div class="gate g2"><span class="g">G2 ネットワーク</span><span>閉域か、パブリックか</span><span>使える Foundry 機能の一覧が決まる(<b>後付け不可</b>)</span></div>
<div class="gate g3"><span class="g">G3 制御</span><span>明示的な分岐・承認・再開が要るか</span><span>ポータル完結か、コードファーストかが決まる</span></div>
<div class="gate g4"><span class="g">G4 統合</span><span>既存システムとの主従はどちらか</span><span>プラットフォームとして使うか、部品として使うか</span></div>
<div class="gate g5"><span class="g">G5 ライフサイクル</span><span>いつまで、誰が保守するか</span><span>プレビュー可否・IaC の作り込み度が決まる</span></div>
<div class="axislabel">後戻りコスト 小 ▼</div>
</div>

- 機能比較表から入ると G1 / G2 の手戻りで壊れる — **上から順に閉じる**のがこのガイドの背骨

<div class="refs">詳細: <a href="../survey/architecture/html/03-decision-guide.html">architecture/03-decision-guide</a> — <span class="path">docs/survey/architecture/03-decision-guide.md</span></div>

<!-- 「何から決めればいいか分からない」への回答がこの 5 ゲート。左帯の濃淡が後戻りコストの大きさ。以降のスライドは全部この順序の上に載っている。 -->

---

# G1 データ・G2 ネットワーク

<div class="msg">G1・G2 は後付けできない — 最初のヒアリングで確定させる 4 点</div>

<div class="cards c2">
<div class="card warn"><div class="t">閉域構成は作成後に変更できない</div>BYO VNet 注入(自前の仮想ネットワークへの組み込み)は<b>リソース作成時のみ</b>。後から閉域要件が出ると作り直し</div>
<div class="card warn"><div class="t">閉域では使えない機能が多い</div>File Search / トレース / Memory / 画像生成など。<b>「閉域で使えない機能の一覧」から設計を始める</b></div>
<div class="card warn"><div class="t">「国内処理の完結」は選択肢が 1 つ</div>Regional Standard(Japan East)のみ。<b>APAC Data Zone は日豪韓星印で処理されうるため不可</b></div>
<div class="card warn"><div class="t">Web 検索はコンプライアンス境界の外</div>Grounding with Bing は DPA(Microsoft のデータ保護補遺)対象外・別課金。<b>規制業種では原則不可</b>として扱う</div>
</div>

<div class="refs">詳細: <a href="../survey/architecture/html/07-usecase-regulated-edge.html">architecture/07-usecase-regulated-edge</a> — <span class="path">docs/survey/architecture/07-usecase-regulated-edge.md</span></div>

<!-- ヒアリングの地雷質問「閉域は要件か希望か」「データを国外に出せるか」はここに直結する。曖昧なまま構成を書かない。4 枚とも「あとで発覚すると作り直し」になる系。 -->

---

# G3〜G5 と机上決定

<div class="msg">事例がなくても構成は机上で決められる — 公式が「試作省略可」と明言</div>

<div class="cards c3">
<div class="card"><div class="t">G3 制御</div>分岐・ループ・承認・再開の明示制御が要るなら<b>コードファースト</b></div>
<div class="card"><div class="t">G4 統合</div>既存システムが主なら「<b>モデルとツールだけ借りる</b>」構成(Responses API のみ利用)</div>
<div class="card"><div class="t">G5 ライフサイクル</div>顧客内製・非開発者運用なら<b>ポータル中心</b>。プレビュー許容度もここで確定</div>
</div>

<div class="callout info"><span class="t">CAF(Cloud Adoption Framework: Microsoft のクラウド導入方法論)の明言</span> — 「Skip prototyping: <b>Yes</b>(複数試作の比較は不要)」「クリティカルな業務ロジックには決定的ワークフローを強制せよ(Foundry / MAF=Microsoft Agent Framework)」</div>

- 実測が要るのは**品質とコストの実額だけ** — そこは評価ハーネスで回帰可能にする

<div class="refs">詳細: <a href="../survey/architecture/html/11-decision-frameworks.html">architecture/11-decision-frameworks</a> — <span class="path">docs/survey/architecture/11-decision-frameworks.md</span></div>

<!-- 「事例がないからアーキを決められない」への直接の回答がこのスライド。公式フレームワーク(CAF / Azure Architecture Center)が 2025-12 以降に整備され、机上で決められる範囲が大きく広がった。 -->

---

<!-- header: "§3 判断②: 要件 → パターンの当たり付け" -->

# 判断②: パターン全体マップ

<div class="msg">要件の言葉をまず「5 つの家族・22 パターン」に当てる</div>

<div class="cards c3">
<div class="card"><div class="t">A 社内ナレッジ検索・RAG(A1〜A5)</div>RAG(検索拡張生成: 文書を検索して根拠つきで回答)。<b>SI 案件で最多</b>。部門 FAQ / 全社検索 / M365 連携など</div>
<div class="card"><div class="t">B 業務自動化・マルチエージェント(B1〜B5)</div>基幹 API 連携 / <b>承認付き自動化</b> / 長時間実行 / 複数エージェント協調</div>
<div class="card"><div class="t">C 顧客向け公開(C1〜C3)</div>不特定多数への公開 / マルチテナント SaaS / 大規模払い出し</div>
<div class="card"><div class="t">D 規制業種・閉域・エッジ(D1〜D3)</div>金融・公共の閉域 / 政府クラウド / オンプレ・エッジ実行</div>
<div class="card"><div class="t">E 特化型(E1〜E6)</div>音声 / 文書処理 / 大量バッチ / 画像・動画生成 / M365 連携 / 追加学習</div>
<div class="card"><div class="t">使い方</div>要件を聞いたら<b>この 22 パターンのどれかに落とす</b>。完全版の一覧表は<b>付録 A1</b>、要件の言葉からの逆引きは<b>付録 A6</b></div>
</div>

<div class="refs">詳細: <a href="../survey/architecture/html/index.html">architecture/index</a> — <span class="path">docs/survey/architecture/README.md</span></div>

<!-- 全部は説明しない。「要件を聞いたらこの地図のどれかに落とす」という使い方だけ伝え、A・B・C・D を代表として次のスライドから図で深掘りする。 -->

---

# A: 社内ナレッジ検索・RAG

<div class="msg">A1 で小さく始めて、権限制御が要るなら A2 に上げるのが本線</div>

<div class="duo">
<figure><img src="../survey/architecture/images/a1-prompt-rag-variants.png" alt="A1"><figcaption><b>A1: File Search 最小構成</b> — PoC 向け。権限制御なし・設定固定</figcaption></figure>
<figure><img src="../survey/architecture/images/a2-knowledge-search.png" alt="A2"><figcaption><b>A2: AI Search 自前索引</b> — 本番の標準形。ユーザーごとに見える文書を絞れる</figcaption></figure>
</div>

- 「部署によって見える文書が違う」と聞いたら **A2 一択**(GA 要件を満たす唯一の方式)
- PoC 段階で**難しい文書 20〜30 件**の検索品質を測ってから方式を確定する

<div class="refs">詳細: <a href="../survey/architecture/html/04-usecase-chat-rag.html">architecture/04-usecase-chat-rag</a> — <span class="path">docs/survey/architecture/04-usecase-chat-rag.md</span></div>

<!-- SI 案件で一番多い類型なので、左(A1)で始めて右(A2)に上げる、という段取りごと覚えてもらう。File Search は埋め込み・チャンク設定が固定で、日本語の長文・表主体文書で品質が出ないことがある。 -->

---

# A: ナレッジの持たせ方 5 分岐

<div class="msg">「データの場所と権限」で決まる — 上から順に聞けば 1 つに落ちる</div>

<div class="qtree">
<div class="q"><span class="cond">ユーザーごとに見える文書が違う?</span><span class="arr">はい →</span><span class="ans"><b>A2</b> AI Search 自前索引(本番の標準形)</span></div>
<div class="q"><span class="cond">M365 / SharePoint が主データ源?</span><span class="arr">はい →</span><span class="ans"><b>A4</b> SharePoint ツール(権限透過。ライセンス前提・プレビュー)</span></div>
<div class="q"><span class="cond">既存の AI Search 索引資産がある?</span><span class="arr">はい →</span><span class="ans"><b>A3</b> AI Search ツール直結(索引設計は自前で持ち続ける)</span></div>
<div class="q"><span class="cond">複数ソースを複数エージェントで共有?</span><span class="arr">はい →</span><span class="ans"><b>A5</b> Foundry IQ(agentic retrieval。一部 GA)</span></div>
<div class="q"><span class="cond">どれでもない(小規模・静的データ)</span><span class="arr">→</span><span class="ans"><b>A1</b> File Search 最小構成</span></div>
</div>

<div class="callout"><span class="t">⚠ Azure OpenAI On Your Data は 2026-10-14 廃止</span> — 「モデルが直接データを読む」構成の既存提案書は要更新(移行先: Agent Service+Foundry IQ)</div>

<div class="refs">詳細: <a href="../survey/architecture/html/04-usecase-chat-rag.html">architecture/04-usecase-chat-rag</a> — <span class="path">docs/survey/architecture/04-usecase-chat-rag.md</span></div>

<!-- RAG は「どれが優れているか」ではなく「データの場所・権限・運用体制でどれに落ちるか」。上から順に聞いていけば 1 つに落ちる。On Your Data 廃止は過去の提案書を持っているメンバーに一番効く情報。 -->

---

# B: 承認付き業務自動化

<div class="msg">本線は B2 —「担当者が承認してから実行」を MAF で作る</div>

![bg right:46% fit](../survey/architecture/images/b2-hitl-automation.png)

図: **B2 承認付き業務自動化**(MAF hosted エージェント)

- HITL(Human-in-the-Loop)= 処理の途中に**人の承認を挟む**構成
- 参照系(読み取りだけ)なら **B1** のツール呼び出し構成で足りる

<div class="refs">詳細: <a href="../survey/architecture/html/05-usecase-agent-automation.html">architecture/05-usecase-agent-automation</a> — <span class="path">docs/survey/architecture/05-usecase-agent-automation.md</span></div>

<!-- 「AI に業務をやらせたいが勝手に実行されるのは困る」という要望はほぼ B2。承認ステップの設計(誰が・どの粒度で承認するか)が要件定義の中心になる。MAF は §2 で出た Microsoft Agent Framework(コードでエージェントを組む公式フレームワーク)。 -->

---

# B: 長時間実行・複数エージェント

<div class="msg">承認待ちが日単位なら B3、権限を分けたいなら B4 に拡張する</div>

<div class="duo">
<figure><img src="../survey/architecture/images/b3-durable.png" alt="B3"><figcaption><b>B3: 長時間・確実な再開</b> — Durable Extension+DTS(Durable Task Scheduler)で数時間〜数日の停止・再開</figcaption></figure>
<figure><img src="../survey/architecture/images/b4-multi-agent.png" alt="B4"><figcaption><b>B4: マルチエージェント(専門分化)</b> — 領域ごとに権限・責務を分離</figcaption></figure>
</div>

- B3 は「承認者が数日戻らない」前提の設計。プロセス再起動をまたいで**確実に再開**できる
- B4 に進む前に**まず単一エージェントで始める**(協調の型は §4 で扱う)

<div class="refs">詳細: <a href="../survey/architecture/html/05-usecase-agent-automation.html">architecture/05-usecase-agent-automation</a> — <span class="path">docs/survey/architecture/05-usecase-agent-automation.md</span></div>

<!-- B2 で足りるかをまず問い、待ち時間の長さで B3、組織・権限の分離要件で B4 へ。どちらも「必要になってから」拡張する方向で提案する。 -->

---

# B: ビジュアル Workflows 廃止

<div class="msg">2026-12-01 に廃止 — ポータルでマルチエージェントは組まない</div>

![bg right:42% fit](../survey/architecture/images/b5-flow-engine.png)

図: **B5 業務フローエンジン主導**(Logic Apps / Copilot Studio)

- 廃止は**ビジュアル Workflows のみ** — エージェント作成・公開・Connected Agents は残る
- 移行先は **MAF(推奨)/ Logic Apps / A2A**(エージェント間連携プロトコル)
- ビジュアル保守を続けたいなら **B5** に倒す(境界線は付録 A4)

<div class="refs">詳細: <a href="../survey/architecture/html/05-usecase-agent-automation.html">architecture/05-usecase-agent-automation</a> — <span class="path">docs/survey/architecture/05-usecase-agent-automation.md</span></div>

<!-- 長期案件でビジュアル Workflows を提案すると納品前に廃止が来る。「ポータルで全部作れます」と言わないためのスライド。 -->

---

# C: 顧客向け公開・SaaS

<div class="msg">主戦場は境界防御 — 会話の認可を Foundry はやってくれない</div>

![bg right:42% fit](../survey/architecture/images/c2-multitenant-saas.png)

図: **C2 マルチテナント SaaS**(APIM 前段の標準構成)

- **BOLA 対策はアプリ側の必須実装**(BOLA = Broken Object Level Authorization: 他人の会話 ID を指定すると読めてしまう認可不備)
- 境界は WAF(Web Application Firewall)+APIM(Azure API Management)。**課金按分も APIM で自前**
- クォータは**デプロイ単位** — 分割で暴走を隔離

<div class="refs">詳細: <a href="../survey/architecture/html/06-usecase-customer-facing.html">architecture/06-usecase-customer-facing</a> — <span class="path">docs/survey/architecture/06-usecase-customer-facing.md</span></div>

<!-- 公開系は「Foundry の機能」より「Foundry がやらない境界防御」が主戦場。BOLA と按分は §5(やってくれないこと)にも再登場する。429 応答のリトライ実装もアプリ側の責務。 -->

---

# D: 規制業種・閉域・エッジ

<div class="msg">閉域は「使えない機能の一覧」から設計する — 月額の下限は固定費で決まる</div>

<div class="duo">
<figure><img src="../survey/architecture/images/d1-closed-network.png" alt="D1"><figcaption><b>D1: 規制業種・閉域</b> — BYO VNet+Private Endpoint(閉域接続の受け口)群</figcaption></figure>
<figure><img src="../survey/architecture/images/d3-edge-onprem.png" alt="D3"><figcaption><b>D3: エッジ・オンプレ</b> — Foundry Local / Azure Local / 切断コンテナ</figcaption></figure>
</div>

- **固定費を先に積む**(Firewall / Private Endpoint / APIM)— トークン代より固定費が支配的
- D2(政府クラウド)は hosted エージェント・MCP(ツール接続規格)・A2A が非対応

<div class="refs">詳細: <a href="../survey/architecture/html/07-usecase-regulated-edge.html">architecture/07-usecase-regulated-edge</a> — <span class="path">docs/survey/architecture/07-usecase-regulated-edge.md</span></div>

<!-- 金融・公共の案件はまずこの章。G2 ゲート(後付け不可)の実体がここにある。左が閉域の標準形、右がそもそもクラウドに出せない場合の 3 形態。 -->

---

# E: チャット以外の 6 類型

<div class="msg">「索引」と「落とし穴」だけ持ち帰る — 各類型の構成図は 2 層目にある</div>

| ID | 類型 | 使うもの | 落とし穴 |
|---|---|---|---|
| E1 | 音声エージェント | Voice Live API | SIP(電話網接続の標準プロトコル)非対応・ガードレール非適用 |
| E2 | 文書処理(IDP) | Document Intelligence(定型帳票)/ Content Understanding(非定型) | 後者はページ課金・BYO モデル接続必須 |
| E3 | 大量バッチ | Batch デプロイ | **50% 引き**だが 24 時間ターゲット・SLA なし |
| E4 | 画像・動画生成 | 非同期ジョブ | **閉域不可** |
| E5 | M365 / Teams 連携 | 公開フロー(GA) | Bot Service が別途必要 |
| E6 | ファインチューニング | MLOps パイプライン | **知識の追加は RAG、挙動・文体の変更が FT**。デプロイは作り直し前提 |

- IDP = Intelligent Document Processing(帳票・契約書の構造化抽出)。FT = Fine-tuning(追加学習)

<div class="refs">詳細: <a href="../survey/architecture/html/08-usecase-specialized.html">architecture/08-usecase-specialized</a> — <span class="path">docs/survey/architecture/08-usecase-specialized.md</span></div>

<!-- 「チャット以外」の引き合いが来たときの索引。E6 の「知識は RAG、挙動は FT」は顧客への説明でそのまま使える一行。各類型のアーキ図は architecture/08 に全部ある。 -->

---

<!-- header: "§4 判断②: ポータルか、コードか、どのフレームワークか" -->

# 判断②: フレームワーク選定の 3 軸

<div class="msg">「ポータル vs MAF vs LangGraph」と一列に並べない — 独立した 3 つの軸で決める</div>

<div class="axes">
<div class="axis"><span class="lab">軸A 定義方法</span><span class="opts"><span class="opt"><b>Prompt エージェント</b> — 構成のみ・フルマネージド実行</span><span class="opt"><b>Hosted エージェント</b> — 自前コードをデプロイ</span></span></div>
<div class="axis"><span class="lab">軸B フレームワーク</span><span class="opts"><span class="opt hl"><b>MAF</b></span><span class="opt">LangGraph</span><span class="opt">OpenAI Agents SDK</span><span class="opt">自前コード</span></span></div>
<div class="axis"><span class="lab">軸C 統合度</span><span class="opts"><span class="opt">フル統合</span><span class="opt"><b>Responses API のみ</b> — モデルとツールだけ借りる</span><span class="opt">Foundry 非依存</span></span></div>
</div>

- Hosted エージェントは **MAF 専用ではない** — LangGraph 製エージェントを Foundry にホストする構成も公式サポートの正規ルート
- 「Foundry を使うか」と「MAF を使うか」は**独立した判断**。既存システム組み込み型の SI 案件では軸C の「Responses API のみ」が重要

<div class="refs">詳細: <span class="path">docs/learning-plan.md §2(技術選定の全体像)</span> — <a href="../learning-plan.md">learning-plan.md</a></div>

<!-- 「ポータル vs MAF vs LangGraph」と一列に並べた瞬間に議論が壊れる。3 軸が独立していることだけ持ち帰ってもらえれば、このセクションは成功。 -->

---

# レイヤー別「任せる / 作る」

<div class="msg">16 のレイヤーごとに「Foundry に任せる / 自前で作る」を選ぶ — 全体表は付録 A5</div>

<div class="mhs">
<div class="row"><span>凡例: <b>M</b> フルマネージド(Foundry 機能)/ <b>H</b> ハイブリッド / <b>S</b> 自前実装</span><span class="opts"><span class="opt">M</span><span class="opt">H</span><span class="opt">S</span></span></div>
<div class="row"><span><b>L2 オーケストレーション</b> — 迷ったら Hosted エージェント(MAF / LangGraph)</span><span class="opts"><span class="opt">M</span><span class="opt sel">H</span><span class="opt">S</span></span></div>
<div class="row"><span><b>L4 長期記憶</b> — Foundry Memory はプレビュー。本番は自前サマライズ+ベクトル検索</span><span class="opts"><span class="opt">M</span><span class="opt">H</span><span class="opt sel">S</span></span></div>
<div class="row"><span><b>L5 ナレッジ / RAG</b> — 本番は AI Search 自前索引(A2 と同じ判断)</span><span class="opts"><span class="opt">M</span><span class="opt sel">H</span><span class="opt">S</span></span></div>
<div class="row"><span><b>L11 ゲートウェイ</b> — 按分・レート制御が要るなら APIM(AI ゲートウェイ)</span><span class="opts"><span class="opt">M</span><span class="opt sel">H</span><span class="opt">S</span></span></div>
<div class="row"><span><b>L16 IaC・CI/CD</b> — データプレーンは Bicep の外(§5 で詳述)</span><span class="opts"><span class="opt">M</span><span class="opt">H</span><span class="opt sel">S</span></span></div>
</div>

- 「迷ったら」列は**既定値であって正解ではない** — 各レイヤーの全選択肢と根拠は 2 層目に整理済み

<div class="refs">詳細(16 レイヤー全体): <a href="../survey/architecture/html/02-building-blocks.html">architecture/02-building-blocks</a> / 付録 A5 — <span class="path">docs/survey/architecture/02-building-blocks.md</span></div>

<!-- 発表ではこの 5 レイヤーだけ。全 16 レイヤーの M/H/S 表は付録 A5 と architecture/02 にある。個別レイヤーの議論になったらそちらに戻る。 -->

---

# マルチエージェント協調の型

<div class="msg">協調は 2 つの軸で 3 つの型に割り切れる — そもそも単一で始める</div>

<div class="qtree">
<div class="q"><span class="cond">制御の流れを<b>コード</b>が決める(順序・分岐が事前に確定)</span><span class="arr">→</span><span class="ans"><b>グラフ型</b> — MAF Workflow。直列・並列・分岐・ループ</span></div>
<div class="q"><span class="cond"><b>LLM</b> が相手を選び、応答が<b>戻る</b></span><span class="arr">→</span><span class="ans"><b>相談型(agent-as-tool)</b> — エージェントをツールとして呼ぶ</span></div>
<div class="q"><span class="cond"><b>LLM</b> が相手を選び、制御が<b>移る</b></span><span class="arr">→</span><span class="ans"><b>担当交代(handoff)</b> — サポートのエスカレーション等</span></div>
</div>

- そもそも**単一エージェントで始める** — CAF は最初からマルチにしてよい条件を 3 つに限定。Anthropic の公表値ではマルチはトークン消費 3〜10 倍
- 実測: 元アプリの「handoff」の多くは実は**固定シーケンス** — グラフ化で失うものはなく、型・テスト・可視化を得る

<div class="refs">詳細: <span class="path">docs/tech-selection-guide.md §1-1</span> / <a href="../survey/architecture/html/11-decision-frameworks.html">architecture/11(公式 5 パターンとの対照)</a></div>

<!-- Azure Architecture Center の 5 パターン・LangChain の 4 型もこの 2 軸(制御を誰が決めるか×制御が戻るか)に還元できる。労力をかけて覚えるのはこの 1 枚でよい。 -->

---

# フレームワーク移行コスト

<div class="msg">他フレームワークからの書き換えは実測済み — 移行は思ったより軽い</div>

| 元フレームワーク → MAF | 書き換えの実態(14 本の移植から) |
|---|---|
| LangGraph(StateGraph) | ノード→Executor、条件エッジ→switch-case。型なし共有 dict が**型付きメッセージ**になる |
| OpenAI Agents SDK | handoff 1 行 → 構造化出力+switch-case の数十行。**ただしテスト可能になる** |
| AG2 旧 Swarm | 長寿命エージェントの「必要悪」が、ステートレスな純関数に縮退 |
| LangChain ルーター | 三段カスケード約 150 行が **Foundry IQ の宣言に消滅**(可観測性・単体テストは失う) |
| ADK + FastAPI 常時稼働 | hosted エージェント化で変わるのは周辺 3 点のみ。cron 配管は Routines へ |

- 共通パターン: **書き換えで元コードの欠陥が見つかる** — 型付きグラフへの移植自体がコードレビューとして機能する

<div class="refs">詳細(全 14 行+検証元): <span class="path">docs/tech-selection-guide.md §1-3</span> — <a href="../tech-selection-guide.md">tech-selection-guide.md</a></div>

<!-- 「他フレームワークからの乗り換えは怖い」への実測回答。移行コストは思ったより一様に低いが、失うもの(LangChain ルーター行の可観測性など)も正直に書いてある。 -->

---

# 実証済みコードの対応表

<div class="msg">「事例がない」には動くコードで答える — 8 つの型 × 約 470 テスト</div>

| 作りたいもの | 実証済みの型 | 検証コード(labs) |
|---|---|---|
| 直列パイプライン | Executor+エッジ、進捗イベント | trend-analysis |
| 並列実行+合流 | fan-out / fan-in エッジ | mixture-of-agents |
| ルーティング / トリアージ | 構造化出力+switch-case | research-handoff |
| 自己補正 RAG | 採点→分岐→書き換えのグラフ+AI Search | corrective-rag |
| 評価駆動の品質ループ | サイクリックグラフ+クラウド評価 | critique-loop |
| 常時稼働+スケジュール | hosted エージェント+Routines | hn-briefing-hosted |
| 音声エージェント | Voice Live(3 層分離) | claim-voice-live |
| ガバナンス / 監査 | middleware 3 種+ハッシュ連鎖監査 | governed-agent |

- 顧客事例ではないが、**動くコード+テスト+IaC 一式**が型ごとにある — 実現可否確認と工数見積もりの根拠に使える
- **Foundry に載せる最初の動機は観測性** — トレース配線は実質 2 行

<div class="refs">詳細: <span class="path">labs/maf-ports/README.md(進捗表)/ docs/tech-selection-guide.md §3</span></div>

<!-- 「事例がない」への課内の回答がこの表。14 ポート合計約 470 テストをネットワークなしで実行できる。「エージェントはテストできない」は設計の問題。 -->

---

<!-- header: "§5 判断③: 見積もりに乗せる現実" -->

# 判断③: やってくれないこと

<div class="msg">「Foundry がやってくれないこと」を先に顧客と合意する — 頻出 5 つ</div>

<div class="cards c3">
<div class="card"><div class="t">① 災害復旧・フェイルオーバー</div>リージョン間の自動切替なし。<b>復旧は再構築</b> — アプリ層ルーティング+再構築パイプラインで埋める</div>
<div class="card"><div class="t">② 会話のユーザー単位認可</div>BOLA 対策なし — アプリ側で所有権をリクエストごとに検証</div>
<div class="card"><div class="t">③ blue-green / canary 配備</div>エージェントの段階的リリース機能なし — APIM 等のルーティング層で</div>
<div class="card"><div class="t">④ 部門・テナント別の課金按分</div>トークン計測は APIM の <code>llm-emit-token-metric</code> で自前実装</div>
<div class="card"><div class="t">⑤ コストのハードリミット</div>公式明記: <b>機能が存在しない</b> — 予算アラート+自作の自動化で</div>
<div class="card warn"><div class="t">⚠ フィルターはフェイルオープン</div>コンテンツフィルターが利用不能のとき<b>遮断せず素通しで HTTP 200</b> を返す — 規制業種は応答検証を必須実装に</div>
</div>

- 全 12 項目は**付録 A2** — 提案書の**除外事項・前提条件欄にそのまま転記**できる形にしてある

<div class="refs">詳細: <a href="../survey/architecture/html/index.html">architecture/index(全案件共通の前提の節)</a> — <span class="path">docs/survey/architecture/README.md</span></div>

<!-- 「Foundry でできます」と言った後に効いてくるのがこのリスト。フェイルオープンは finish_reason と content_filter_results の検証で防ぐ。 -->

---

# 重要期限 2026–2027

<div class="msg">提案書には賞味期限がある — 直近 4 つの廃止日は暗記する</div>

<div class="timeline">
<div class="tl hot"><span class="d">2026-08-20</span><br><b>Hosted エージェント旧基盤</b><br>自動移行なし。再デプロイ必須</div>
<div class="tl hot"><span class="d">2026-08-26</span><br><b>Assistants API</b><br>Threads / Runs 前提のアプリは全面改修</div>
<div class="tl hot"><span class="d">2026-10-14</span><br><b>On Your Data</b><br>RAG の既存提案書は要更新</div>
<div class="tl hot"><span class="d">2026-12-01</span><br><b>ビジュアル Workflows</b><br>ポータルでのマルチエージェント構成が消える</div>
<div class="tl"><span class="d">2027-03-31</span><br>Agents (classic)<br>状態データは移行されない</div>
<div class="tl"><span class="d">2027-04-20</span><br>prompt flow<br>新規開発に非推奨・MAF へ</div>
</div>

- PoC → 本番のスケジュールと**期限の衝突チェック**を提案フローに組み込む(期間内に廃止が来るなら最初から後継 API で作る)
- モデル自体のリタイア(gpt-4o 等 2026-10 前後)も含めた**全体表は付録 A3**

<div class="refs">詳細: <a href="../survey/architecture/html/10-migration-antipatterns.html">architecture/10-migration-antipatterns</a> / <a href="../survey/features/html/index.html">features/index(期限表)</a></div>

<!-- 「GA だから安心」ではなく「いつ消えるか」で見る。赤の 4 つは直近数か月なので暗記推奨。 -->

---

# 提案のアンチパターン

<div class="msg">踏みやすい 11 個のうち代表 3 つ — 言う前・見積もる前に確認する</div>

<div class="cards c3">
<div class="card warn"><div class="t">「ポータルで全部できます」</div>ポータル完結は「単一エージェント+カタログツール+公開」まで。分岐・承認・ローカルテストは入らない<br><span class="sub">対処: ポータル完結の範囲とコードが要る範囲の線引き表を提案に添える</span></div>
<div class="card warn"><div class="t">File Search で品質が出ないまま押し切る</div>チャンク・埋め込み設定は固定で、日本語長文・表主体の文書に合わないことがある<br><span class="sub">対処: PoC で難しい文書 20〜30 件を測り、駄目なら早期に AI Search へ</span></div>
<div class="card warn"><div class="t">az CLI で自動化できる前提の見積もり</div>専用の <code>az foundry</code> は存在せず、多くの機能はポータル+SDK / REST のみ<br><span class="sub">対処: 自動化は Bicep / Terraform(基盤)+SDK / REST(データ操作)前提で工数を積む</span></div>
</div>

<div class="refs">詳細(全 11 個): <a href="../survey/architecture/html/10-migration-antipatterns.html">architecture/10-migration-antipatterns</a> — <span class="path">docs/survey/architecture/10-migration-antipatterns.md</span></div>

<!-- 残り 8 個(閉域後付け・Claude のガードレール・プレビュー本番投入など)は既に他のスライドで触れたものも多い。設計レビュー前に 10 章を通読するのが実用的な使い方。 -->

---

# 実装のハマりどころ

<div class="msg">「半日溶けるポイント」は先に知っておく — 実測 3 点</div>

<div class="cards c3">
<div class="card"><div class="t">権限の反映が遅く・不均一</div>RBAC(ロールベースアクセス制御)の伝播は 5〜15 分。さらに Bicep 作成のプロジェクトは実行 ID にモデル操作権限が<b>自動付与されない</b>(ポータル作成は付く)— 401 エラーの切り分けで半日溶ける</div>
<div class="card"><div class="t">IaC だけでは完結しない</div>AI Search の索引や Memory ストアは Bicep / ARM で作れない。「<b>Bicep → セットアップスクリプトの 2 段デプロイ</b>」が定型 — IaC 完結前提の見積もりは崩れる</div>
<div class="card"><div class="t">Memory は「書いた直後に読めない」</div>Foundry Memory は同期書き込みではなく<b>非同期処理+既定 300 秒の遅延</b>(LRO+debounce)— UX とテストはその前提で設計する</div>
</div>

<div class="refs">詳細(全 13 点+検証元): <span class="path">docs/tech-selection-guide.md §2(実装ナレッジ集)</span> — <a href="../tech-selection-guide.md">tech-selection-guide.md</a></div>

<!-- 「運が悪いと半日〜1 日溶ける系」を 13 点まとめてある。実装フェーズに入るメンバーは tech-selection-guide §2 を最初に読むと元が取れる。 -->

---

<!-- header: "§6 提案実務への接続" -->

# 提案フロー

<div class="msg">5 ステップの型に資料を対応済み — 明日から使える</div>

<div class="flow">
<div class="st"><span class="t">1. ヒアリング</span><br>質問リストで要件採取<br><span class="chip gray">proposal/01</span></div>
<span class="arr">→</span>
<div class="st"><span class="t">2. 実現可否</span><br>GA / プレビュー確認<br><span class="chip gray">features</span></div>
<span class="arr">→</span>
<div class="st"><span class="t">3. 概算</span><br>月額レンジ試算<br><span class="chip gray">proposal/02</span></div>
<span class="arr">→</span>
<div class="st"><span class="t">4. 規制説明</span><br>顧客説明の論点<br><span class="chip gray">proposal/03</span></div>
<span class="arr">→</span>
<div class="st"><span class="t">5. 体制</span><br>知識ギャップ確認<br><span class="chip gray">proposal/04</span></div>
</div>

- ヒアリング後のアウトプット: 構成候補 1〜2 案 / **プレビュー依存リスト** / **廃止日程との衝突チェック** / 概算月額レンジ / 規制・契約の論点リスト

<div class="refs">詳細: <a href="../survey/proposal/html/index.html">proposal/index</a> — <span class="path">docs/survey/proposal/README.md</span></div>

<!-- 提案の型は既に 5 ステップに分解して資料化済み。「明日から案件で使える」状態であることを伝えるのがこのセクション。 -->

---

# ヒアリングとコスト概算

<div class="msg">ヒアリングは「地雷質問」から、コストは「固定費」から積む</div>

<div class="cards c2">
<div class="card"><div class="t">ヒアリングシート(proposal/01)</div>Phase 0〜7・約 30 問。太字は<b>地雷質問</b>(聞き漏らすと提案後に手戻り)<br><span class="sub">例: 閉域は要件か希望か / データを国外に出せるか / ユーザーごとに見えるデータが違うか / 引き渡し後は誰が運用するか</span></div>
<div class="card"><div class="t">コスト見積もり手順(proposal/02)</div>トークン推計(日本語 ≒ 1 文字 1 トークン。<b>エージェントは内部呼び出しで 2〜5 倍</b>)→ 構成要素チェック → 単価取得 → PTU(スループット予約)判断 → 削減レバー<br><span class="sub">単価はドキュメントに書かない主義(陳腐化対策)。モデル以外が過半になる構成は珍しくない</span></div>
</div>

- 閉域構成の経験則: **固定費(Firewall / Private Endpoint / APIM)だけで月額の下限が決まる** — 先に固定費、後から変動費

<div class="refs">詳細: <a href="../survey/proposal/html/01-hearing-sheet.html">proposal/01-hearing-sheet</a> / <a href="../survey/proposal/html/02-cost-estimation.html">proposal/02-cost-estimation</a></div>

<!-- ヒアリングシートは 60〜90 分の初回ヒアリングでそのまま使える。コスト手順は試算例 A / B / C(社内 RAG・顧客向け・文書処理バッチ)つき。 -->

---

# 日本の規制対応

<div class="msg">定番質問への「回答型」を用意済み — 登録状況は案件ごとに最新確認</div>

<div class="cards c2">
<div class="card"><div class="t">ISMAP(政府・自治体)</div>政府情報システムのクラウド登録制度。<b>対象サービスの登録状況の確認が先決</b> — 登録リストは変動するため文書に固定値を書かない設計</div>
<div class="card"><div class="t">FISC(金融)</div>金融機関の安全対策基準。対応整理+<b>閉域構成(D1)が前提</b>になりやすい</div>
<div class="card"><div class="t">個人情報保護法</div>委託構成の整理+<b>abuse monitoring(不正利用監視の人手レビュー)の説明</b>を準備 — オプトアウト申請の要否を含む</div>
<div class="card"><div class="t">3 省 2 ガイドライン(医療)</div>医療情報システムの安全管理ガイドライン。該当時の論点を整理済み</div>
</div>

- 位置づけ: **G1(データ・規制)/ G2(ネットワーク)ゲートの日本ローカル具体化**

<div class="refs">詳細: <a href="../survey/proposal/html/03-japan-compliance.html">proposal/03-japan-compliance</a> — <span class="path">docs/survey/proposal/03-japan-compliance.md</span></div>

<!-- 規制の細部を暗記する必要はない。「定番質問の回答型がある」「登録状況は案件ごとに最新確認」の 2 点だけ覚えてもらう。 -->

---

# 公開事例

<div class="msg">提案書で引ける事例を 21 件収録 — 公式出典のみ、数値は表現のまま使う</div>

<div class="cards c3">
<div class="card stat"><div class="n">67%</div><b>富士通</b> — 営業支援エージェントで生産性向上(Foundry 名指し)</div>
<div class="card stat"><div class="n">50%</div><b>NTT データ</b> — Fabric+Agent Service で市場投入を短縮</div>
<div class="card stat"><div class="n">4 万件/日</div><b>Air India</b> — 問い合わせを自動処理</div>
</div>

- ほかに Sky / 大和証券 / トヨタ / ソフトバンク / JR 西日本 / Accenture(4 か月で 17 ユースケース)など**計 21 件**を出典 URL つきで収録
- 事例は「**同業種・同類型で公開実績がある**」ことの証明に使い、**アーキテクチャ選定の根拠には使わない**(その役割は公式リファレンス)

<div class="refs">詳細(正確な表現+出典 URL): <a href="../survey/proposal/html/05-case-studies.html">proposal/05-case-studies</a> — <span class="path">docs/survey/proposal/05-case-studies.md</span></div>

<!-- 効果数値は必ず出典の表現のまま引用する(「約」「目標」を落とさない)。「Foundry 事例が少なく見える」のは主に名義変遷の問題。二次記事は収録していないので、そのまま提案書に載せられる。 -->

---

<!-- header: "§7 クロージング" -->

# 情報の鮮度の保ち方

<div class="msg">この情報は腐る — ウォッチすべき一次情報は 3 つだけ</div>

<div class="cards c3">
<div class="card"><div class="t">What's new in Microsoft Foundry</div>月次の新機能・ステータス変更<br><span class="sub">features の月次更新のトリガー</span></div>
<div class="card"><div class="t">Feature readiness at GA</div>GA / プレビューの<b>最重要ページ</b><br><span class="sub">公式ページ間で表記が食い違ったらここを正とする</span></div>
<div class="card"><div class="t">Model retirement schedule</div>モデルのリタイア日<br><span class="sub">提案書のモデル固定リスクをここで確認</span></div>
</div>

- 更新サイクル: **features 月次 / architecture 四半期 / proposal 随時**。**Ignite(11 月)・Build(5 月)直後は必ず更新**
- このスライド自体も survey の大型更新に合わせて改訂する(更新手順は明文化済み・生成 AI への依頼手順つき)

<div class="refs">詳細(更新運用ガイド・ウォッチリストの URL): <a href="../survey/features/html/index.html">features/index</a> — <span class="path">docs/survey/features/README.md</span></div>

<!-- 資料の信頼性は更新運用で決まる。誰でも更新できるよう手順は features README に明文化してあり、生成 AI に更新作業を依頼する手順まで書いてある。 -->

---

# まとめ

<div class="msg">3 つの判断能力を、次の案件で「この 3 手」から使い始める</div>

<div class="cards c3">
<div class="card"><div class="t">① 決める順序</div><b>G1〜G5</b> を後戻りコストの大きい順に閉じる</div>
<div class="card"><div class="t">② 当たりの付け方</div>要件の言葉 → <b>A1〜E6 パターン</b>+<b>3 軸</b>(定義方法 / フレームワーク / 統合度)</div>
<div class="card"><div class="t">③ 見積もりの現実</div>「<b>やってくれないこと 12</b>」+<b>廃止期限</b>+実測のハマりどころ</div>
</div>

<div class="flow">
<div class="st"><span class="t">1 ヒアリング</span><br>proposal/01 のシートで要件採取(太字の地雷質問だけでも)</div>
<span class="arr">→</span>
<div class="st"><span class="t">2 ゲートで絞る</span><br>G1 → G5 の順に閉じ、A1〜E6 の 1〜2 パターンへ</div>
<span class="arr">→</span>
<div class="st"><span class="t">3 裏取り</span><br>features で GA / プレビュー確認+期限表と衝突チェック</div>
</div>

<div class="refs">最初の 1 手のテンプレート: <a href="../survey/proposal/html/01-hearing-sheet.html">proposal/01-hearing-sheet</a> / 要件の逆引きは付録 A6 — <span class="path">docs/survey/proposal/01-hearing-sheet.md</span></div>

<!-- 3 手のうち 1 つでも次の案件で実行されたら、この勉強会は成功。質疑では「いま抱えている案件をこの型に当てるとどうなるか」を歓迎する。 -->

---

# 2 層目への入口 / Q&A

<div class="msg">2 層目はビルド済み — リポジトリを clone してブラウザで開くだけ</div>

| 資料 | 何に使う | 場所 |
|---|---|---|
| 機能一覧(features) | その機能は使えるのか | <span class="path">docs/survey/features/html/index.html</span> |
| 設計ガイド(architecture) | どう組むか・パターン・運用 | <span class="path">docs/survey/architecture/html/index.html</span> |
| 提案実務(proposal) | ヒアリング・コスト・規制・事例 | <span class="path">docs/survey/proposal/html/index.html</span> |
| 技術選定ガイド | 実装で実証した判断基準 | <span class="path">docs/tech-selection-guide.md</span> |
| 学習計画(3 軸の原典) | 選定の全体像 | <span class="path">docs/learning-plan.md</span> |
| 移植ラボ(実装例 14 本) | 動くコード・テスト・IaC | <span class="path">labs/maf-ports/README.md</span> |

- 以降は付録: **A1** パターン完全版 / **A2** やってくれないこと全 12 項 / **A3** 期限全体表 / **A4** Copilot Studio 境界 / **A5** 16 レイヤー表 / **A6** 要件逆引き / **A7** 用語集

<div class="refs"><a href="../survey/features/html/index.html">features</a> / <a href="../survey/architecture/html/index.html">architecture</a> / <a href="../survey/proposal/html/index.html">proposal</a> / <a href="../tech-selection-guide.md">tech-selection-guide</a> / <a href="../learning-plan.md">learning-plan</a> / <a href="../../labs/maf-ports/README.md">labs/maf-ports</a></div>

<!-- 資料はここで終わり。以降は発表では飛ばす付録で、後日参照用の完全版テーブルと用語集を収録している。 -->

---

<!-- header: "付録" -->
<!-- _class: xdense -->

# 付録 A1: ユースケース別パターン完全版(A1〜E6)

詳細: <a href="../survey/architecture/html/index.html">architecture/index</a> — <span class="path">docs/survey/architecture/README.md</span>

| ID | パターン | オーケストレーション | RAG / ナレッジ | 主な決め手 |
|---|---|---|---|---|
| A1 | 部門内 FAQ チャット | Prompt agent | File Search | 速度優先。権限制御なし |
| A2 | 全社ナレッジ検索(本番) | Prompt / Hosted agent | **AI Search 自前索引** | ユーザーごとに見える文書が違う |
| A3 | 既存 AI Search 資産の活用 | Prompt agent | AI Search ツール直結 | 索引設計を自分で持ち続けたい |
| A4 | M365 / SharePoint 主データ源 | Prompt agent | SharePoint ツール(OBO) | 権限透過。M365 Copilot ライセンス前提 |
| A5 | 複数ソース横断・高精度 | 任意(MCP 経由) | **Foundry IQ** | 複数エージェントでナレッジ共有 |
| B1 | 単一エージェント+基幹 API | Prompt agent + Toolbox | 補助的 | 参照系中心 |
| B2 | 承認付き業務自動化(HITL) | **MAF hosted agent** | 調査工程で使用 | 「担当者が承認してから実行」 |
| B3 | 長時間・確実な再開 | MAF + Durable Extension + DTS | 任意 | 数時間〜数日停止して再開 |
| B4 | マルチエージェント(専門分化) | MAF workflows / A2A | 領域別 | 領域ごとに権限を分けたい |
| B5 | 業務フローエンジン主導 | Logic Apps / Copilot Studio | 任意 | 業務部門がビジュアルで保守 |
| C1 | 一般顧客向けチャット | 任意 | 任意 | 不特定多数(公開 + WAF + APIM) |
| C2 | マルチテナント SaaS | Hosted agent(プロトコル 2.0.0) | テナント別索引 | 複数顧客に販売(APIM 必須) |
| C3 | 大規模・複数部門への払い出し | 任意 | 任意 | 部門別按分・キャパシティ(APIM 必須) |
| D1 | 規制業種・閉域 | Hosted agent or 自前 | AI Search 自前索引一択 | BYO VNet。閉域・監査・データ主権 |
| D2 | ソブリン(Azure Government) | Prompt agent 対応 | File Search / AI Search | hosted agent・MCP・A2A 非対応 |
| D3 | エッジ・オンプレ | Foundry 非依存 | 自前 | Foundry Local / Azure Local 版 / 切断コンテナ |
| E1 | 音声エージェント | Voice Live API | 任意 | リアルタイム音声対話(SIP 非対応) |
| E2 | 文書処理・IDP | 非同期パイプライン | DI / Content Understanding | 帳票・契約書の構造化抽出 |
| E3 | 大量バッチ処理 | ジョブ実行基盤 | 不要 | Batch で 50% 割引 |
| E4 | マルチモーダル生成 | 非同期ジョブ | 不要 | 画像・動画生成(閉域不可) |
| E5 | M365 / Teams 連携 | Prompt / Hosted agent | Work IQ 等 | 業務ツール内で使わせる |
| E6 | ファインチューニング運用 | MLOps パイプライン | 併用推奨 | 挙動・文体をモデル側で変える |

---

<!-- _class: dense -->

# 付録 A2: Foundry がやってくれないこと(全 12 項)

| # | やってくれないこと | 誰が埋めるか |
|---|---|---|
| 1 | リージョン間の自動フェイルオーバー・DR(復旧は再構築) | アプリ層ルーティング + Cosmos 継続バックアップ + 再構築パイプライン |
| 2 | 会話へのユーザー単位の認可(BOLA) | アプリ側で所有権をリクエストごとに検証 |
| 3 | エージェントの blue-green / canary | APIM 等のルーティング層 |
| 4 | モデルデプロイのラウンドロビン・サーキットブレーカー | APIM のバックエンドプール + circuit breaker |
| 5 | 部門・テナント別のトークン計測と課金按分 | APIM `llm-emit-token-metric` |
| 6 | コストのハードリミット | 予算アラート + 自作の自動化 |
| 7 | プロジェクト内のエージェント単位のアクセス制御 | アプリの認証認可層 / hosted agent の Entra Agent ID |
| 8 | `max_output_tokens` / `truncation` によるトークン制御 | 自前オーケストレーション |
| 9 | 閉域での Traces / Memory / File Search / Work IQ / 画像生成 等 | 自前実装または機能除外 |
| 10 | Claude モデルへのコンテンツフィルター | APIM `llm-content-safety` かアプリ層で Content Safety |
| 11 | 音声モデルへのガードレール | テキスト化後の経路で Content Safety |
| 12 | capabilityHost の更新(変更は削除・再作成) | IaC を「作り直し前提」で設計 |

- 加えて**コンテンツフィルターはフェイルオープン** — 規制業種は `finish_reason` / `content_filter_results` の検証を必須実装に

<div class="refs">詳細: <a href="../survey/architecture/html/index.html">architecture/index(全案件共通の前提の節)</a> — <span class="path">docs/survey/architecture/README.md</span></div>

---

<!-- _class: xdense -->

# 付録 A3: 重要期限の全体表(features 側)

詳細: <a href="../survey/features/html/index.html">features/index</a> — <span class="path">docs/survey/features/README.md</span>

| 期限 | 対象 | 影響・移行先 |
|---|---|---|
| 2026-08-20 | Hosted agents 初期プレビュー基盤 | サポート終了。新基盤へ再デプロイ必須 |
| 2026-08-26 | Assistants API(Azure OpenAI) | 廃止。Responses API(Agents v2)へ |
| 2026-08-26 | `azure-ai-inference` SDK | 廃止(beta のまま GA せず終了)。OpenAI SDK + v1 API へ |
| **2026-08-31** | NTT Data `tsuzumi-7b`(Legacy) | 廃止。後継 `tsuzumi2` へ。**日本語特化モデル案件で効く** |
| 2026-10-01 前後 | gpt-4o / o1 / o3 / o4-mini 等の旧モデル群 | リタイア |
| **2026-10-14** | `gpt-4.1-nano` | リタイア(gpt-4.1 / mini より約半年早い。混同しない) |
| 2026-10-14 | Azure OpenAI On Your Data | 廃止。Foundry Agent Service + Foundry IQ へ |
| 2026-12-01 | ビジュアル Workflows | 廃止。MAF / Logic Apps / A2A へ |
| 2027-03-31 | Agents (classic)(v1、Threads / Runs) | 廃止。Agents v2 へ(状態データは自動移行されない) |
| 2027-04-20 | prompt flow | 廃止。新規開発に非推奨。MAF へ |
| 2028-09-25 | Azure AI Vision Image Analysis 4.0 / 3.2 | 廃止。DI / Content Understanding / Foundry Models へ |
| 日付未公表 | Agent Applications / コンテナプロトコル 1.0.0 | 廃止予告済み(1.0.0 は 2026-07-31 からブロック開始と公表) |
| 予告 15 日のみ | Fireworks 系モデル(`FW-*`) | 標準 60 日でなく **15 日前通知**。本番の必須経路に置かない |

---

# 付録 A4: Copilot Studio との境界線(一次情報で引ける)

- **Copilot Studio → Foundry(プロコード)への乗り換えシグナル 3 つ**(公式ドキュメントで裏づけ):
  - **30〜40 アクション超**でオーケストレーターのツール選択精度が落ちる(公式明記)
  - **多段のエージェント階層が組めない**(connected agents を持つエージェントは他の connected agent になれない)
  - **決定的ワークフローが業務クリティカル** — CAF が「Foundry / MAF の workflows を使え」と実装先を名指し
- 選定の決め手は機能でなく「**誰が作り・誰が保守し・どこまで制御が要るか**」(CAF デシジョンツリー)
- **両者は排他ではない** — 入口・M365 チャネル・業務部門の保守は Copilot Studio、複雑な処理は Foundry hosted agent(connected agent として呼ぶ)が公式推奨の分業構成。**SI の受託範囲を「Copilot Studio で簡単に作れないエージェントの開発」とする契約の切り方が公式構成と一致**(ただし接続はプレビュー)

<div class="refs">詳細: <a href="../survey/architecture/html/11-decision-frameworks.html">architecture/11-decision-frameworks</a> — <span class="path">docs/survey/architecture/11-decision-frameworks.md</span></div>

---

<!-- _class: dense -->

# 付録 A5: 16 レイヤー × M / H / S 完全版(Foundry 機能 vs 自前実装)

| # | レイヤー | M(フルマネージド) | H(ハイブリッド) | S(自前) | 迷ったら |
|---|---|---|---|---|---|
| L1 | モデル提供 | Foundry モデルデプロイ | + APIM ゲートウェイ | 他クラウド / セルフホスト | M |
| L2 | オーケストレーション | Prompt agent | Hosted agent(MAF・LangGraph) | 自アプリ + Responses API | H |
| L3 | 会話状態 | Conversations | BYO Cosmos DB | 自前 DB | M→S |
| L4 | 長期記憶 | Foundry Memory(プレビュー) | Memory + 自前フィルタ | 自前サマライズ + ベクトル検索 | S(本番) |
| L5 | ナレッジ / RAG | File Search / Foundry IQ | AI Search + 自前索引 | 自前パイプライン | H |
| L6 | ツール実行 | ツールカタログ / MCP | Toolbox + 自前 MCP | アプリ内 function calling | H |
| L7 | コード実行 | Code Interpreter | Custom CI | ACA dynamic sessions 直 | M |
| L8 | ガードレール | Guardrails 既定 | カスタム | Content Safety API 自前呼び | M+S 併用 |
| L9 | ID・認可 | Foundry RBAC + Entra | OBO / Agent identity | 自前認可基盤 | M |
| L10 | ネットワーク | パブリック + Private Link | BYO VNet 注入 | 自前 VNet | 要件次第 |
| L11 | ゲートウェイ | クォータのみ | **APIM AI ゲートウェイ** | 自前プロキシ | H |
| L12 | 可観測性 | Foundry Tracing | OTel 自前計装 → App Insights | 自前ログ基盤 | M+H |
| L13 | 評価 | Foundry Evaluations | evals API を CI から | 自前ハーネス | H |
| L14 | UI・チャネル | Teams / M365 公開 | 自作 Web + Responses API | 既存システム組込み | 要件次第 |
| L15 | 実行基盤 | Hosted agents | Container Apps 等 | AKS / オンプレ | H |
| L16 | IaC・CI/CD | ポータル手動 | Bicep / Terraform + azd | 既存 IaC に統合 | S |

<div class="refs">詳細(各レイヤーの全選択肢と根拠): <a href="../survey/architecture/html/02-building-blocks.html">architecture/02-building-blocks</a> — <span class="path">docs/survey/architecture/02-building-blocks.md</span></div>

---

<!-- _class: dense -->

# 付録 A6: 要件の言葉の逆引き表

| 要件の言葉 | 当たりをつけるパターン |
|---|---|
| 「社内文書を検索して答える」 | **A1** で PoC → 品質が出なければ **A2** |
| 「部署によって見える文書が違う」 | **A2**(GA 要件を満たす唯一の方式) |
| 「担当者の承認を経て実行」 | **B2**(MAF hosted agent)。承認待ちが数日なら **B3** |
| 「複数のエージェントが協調する」 | **B4**。ビジュアル Workflows は選ばない(2026-12-01 廃止) |
| 「顧客向けに公開する」 | **C1**。WAF チューニングと BOLA 対策を工数に |
| 「複数のお客様に SaaS として提供」 | **C2**。APIM が事実上必須 |
| 「閉域で運用する」 | **D1**。「閉域で使えない機能一覧」から設計 |
| 「日本国内でデータ処理を完結」 | Regional Standard(Japan East)。APAC Data Zone は不可 |
| 「音声で対話したい」 | **E1**(Voice Live)。SIP 非対応に注意 |
| 「請求書を読み取って」 | **E2**。定型は DI、非定型は Content Understanding |
| 「月間 N 万件を処理」 | **E3**(Batch 50% 引き)+ PTU サイジング |
| 「既存システムに組み込む」 | オーケストレーションは自前(L2 の S)。Foundry の運用機能は使えなくなる |
| 「ロックイン回避」 | Foundry はモデル供給元として使い、抽象レイヤーを自前で持つ |

<div class="refs">詳細: <a href="../survey/architecture/html/index.html">architecture/index(選定早見表)</a> — <span class="path">docs/survey/architecture/README.md</span></div>

---

<!-- _class: xdense -->

# 付録 A7: 用語集(本資料で使う略語)

<div class="cols">
<div>

| 略語 | 意味 |
|---|---|
| GA | General Availability(一般提供)。SLA つきの正式リリース |
| RAG | Retrieval-Augmented Generation。文書を検索して根拠つきで回答させる方式 |
| HITL | Human-in-the-Loop。処理の途中に人の承認を挟む |
| MAF | Microsoft Agent Framework。コードでエージェントを組む公式フレームワーク |
| MCP | Model Context Protocol。エージェントとツールの標準接続規格 |
| A2A | Agent-to-Agent。エージェント間連携プロトコル |
| BOLA | Broken Object Level Authorization。ID 指定で他人のリソースに触れる認可不備 |
| FT | Fine-tuning。モデルの追加学習 |
| IDP | Intelligent Document Processing。帳票・文書の構造化抽出 |
| DI / CU | Document Intelligence(定型帳票)/ Content Understanding(非定型文書) |
| PTU | Provisioned Throughput Unit。スループットの予約購入 |
| OBO | On-Behalf-Of。ユーザー本人の権限での代理アクセス |
| LRO | Long-Running Operation。非同期の長時間処理 |
| SIP | Session Initiation Protocol。電話網接続の標準プロトコル |

</div>
<div>

| 略語 | 意味 |
|---|---|
| WAF(2 義) | Web Application Firewall(境界防御)/ Well-Architected Framework(Azure 設計原則集)。本文では都度明記 |
| APIM | Azure API Management。API ゲートウェイ |
| VNet / BYO VNet | 仮想ネットワーク / 自前 VNet の持ち込み(閉域構成) |
| PE | Private Endpoint。閉域接続の受け口 |
| CMK | Customer-Managed Key。顧客管理キーによる暗号化 |
| RBAC | Role-Based Access Control。ロールベースのアクセス制御 |
| MI | Managed Identity。Azure リソースに付与する実行 ID |
| IaC | Infrastructure as Code。インフラ構成のコード化(Bicep / Terraform) |
| CAF | Cloud Adoption Framework。Microsoft のクラウド導入方法論 |
| AAC | Azure Architecture Center。公式アーキテクチャ集 |
| ALZ | Azure Landing Zones。全社共通の Azure 基盤標準 |
| DPA | Data Protection Addendum。Microsoft のデータ保護補遺(契約文書) |
| DTS | Durable Task Scheduler。永続実行のスケジューラ |
| DR | Disaster Recovery。災害復旧 |

</div>
</div>
