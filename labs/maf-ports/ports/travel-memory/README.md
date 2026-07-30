# travel-memory — 記憶付き旅行相談チャット + Foundry Memory(Port 5)

> **⚠️ Foundry Memory はパブリックプレビュー**(Memory Store API も同様)。
> プレビュー期間中は**課金体系が変更される可能性**が明記されており(課金対象はストアに構成した chat/embedding モデルの利用分)、**VNet 統合は非対応**。対応リージョンは 19(**Japan East を含む** — 共有基盤はそのまま使える)。クォータ: 100 scopes/store・10,000 memories/scope・search/update 各 1,000 req/min。詳細は [docs/survey/features/03-agent-service.md](../../../../docs/survey/features/03-agent-service.md) と [What is Memory?](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/what-is-memory)。

元: [`advanced_llm_apps/llm_apps_with_memory_tutorials/ai_travel_agent_memory`](https://github.com/Shubhamsaboo/awesome-llm-apps/tree/main/advanced_llm_apps/llm_apps_with_memory_tutorials/ai_travel_agent_memory)(OpenAI + mem0 0.1.29 + Qdrant + Streamlit、101 行)

## 元の構成(5行)

- Streamlit のチャット UI。サイドバーでユーザー名(`user_id`)を入力し、記憶はこの単位で分離。「View My Memory」で `memory.get_all(user_id)` の一覧表示
- 記憶層は mem0 `Memory.from_config()`(ベクトルストアはローカル Qdrant :6333)。埋め込み・事実抽出は mem0 が内部で OpenAI API を呼ぶ
- 毎ターン: `memory.search(query=prompt, user_id)` → ヒットを `"Relevant past information:\n- ..."` に整形 → `f"{context}\nHuman: {prompt}\nAI:"` を組み立て
- gpt-4o に system prompt("You are a travel assistant with access to past conversations.")+上記プロンプトで生成。空応答は ValueError
- 応答後に `memory.add(prompt, user_id, metadata={"role":"user"})` と `memory.add(answer, ..., {"role":"assistant"})` の 2 回で会話を記憶へ追加(= 検索 → 注入 → 応答 → 追加の順序)

## mem0 → Foundry Memory 対応表(本ポートの核心)

| mem0(元) | Foundry Memory(移植後) | 備考 |
| --- | --- | --- |
| `Memory.from_config({qdrant})`(コレクション自動作成) | `beta.memory_stores.create(name, MemoryStoreDefaultDefinition(chat_model, embedding_model, options))` — [scripts/setup_memory.py](./scripts/setup_memory.py) | mem0 は「ローカル Qdrant+呼び出し側の OpenAI キー」を自前で束ねる。Foundry は**モデルデプロイ名 2 つを指すだけ**のフルマネージド(gpt-5.4-mini + text-embedding-3-small)。ストア作成はデータプレーン API(ARM 外) |
| `memory.add(text, user_id=u, metadata={"role": r})` | `begin_update_memories(name, scope=u, items=[{"role": r, "type": "message", "content": text}], previous_update_id=…, update_delay=0)` | **最大の差**: mem0 は同期(戻ったら検索可能)、Foundry は **LRO**(抽出・統合が非同期、既定 `update_delay=300` 秒の debounce)。毎ターン add は `update_delay=0` + scope ごとの `previous_update_id` チェーンで再現(学び 1) |
| `memory.search(query, user_id=u)` | `search_memories(name, scope=u, items=[{"role":"user","type":"message","content":query}], options=MemorySearchOptions(max_memories=5))` | クエリは文字列でなく**会話アイテム**(Responses API の message 形式)。`previous_search_id` による増分検索もある(本ポートは元アプリ同様、毎回フル検索) |
| `memory.get_all(user_id=u)` | `list_memories(name, scope=u)`(ページング) | 元アプリの「View My Memory」→ CLI の `--memories` / `/memories` |
| `memory.delete_all(user_id=u)` | `delete_scope(name, scope=u)` | ライブスモークのテスト scope 掃除に使用 |
| `user_id`(mem0 側の論理キー) | `scope`(ストアの一級概念) | 1:1 対応。低レベル API では**毎リクエスト明示必須**。エージェントツール経由なら `{{$userId}}` で Entra ID から自動解決(学び 2) |
| 抽出された事実(無型のテキスト) | `user_profile` / `chat_summary` / `procedural` の **3 種に型付け**+統合・矛盾解消 | 検索結果の `kind` で区別可能。抽出方針は `user_profile_details` で自然言語指示できる |

## SDK か REST か → **SDK(azure-ai-projects 2.4.0)を採用**

事前調査の結果(いずれも installed package の grep で確認):

- **azure-ai-projects 2.x に memory API はある**: `client.beta.memory_stores`(`BetaMemoryStoresOperations`)が store の create/get/list/delete、`search_memories`、`begin_update_memories`(LRO)、`list_memories`、item CRUD(`create_memory` 等)、`delete_scope` まで全面カバー。async 版(`azure.ai.projects.aio`)もある。公式 how-to も `pip install "azure-ai-projects>=2.3.0"` を前提にしている。ラボ既存 venv には未導入だったため本ポートの依存に追加した
- **MAF 側にも統合が既にある**: `agent_framework.foundry` の lazy re-export に `FoundryMemoryProvider`(agent-framework-foundry 1.10.1、`ContextProvider` 実装)。`before_run` で search・`after_run` で `begin_update_memories`(fire-and-forget、`update_delay` 既定 300)を行う。**本ポートでは採用しない**(下の設計判断)

REST 直叩き(httpx + `api-version=2025-11-15-preview` + Entra トークン)にしなかった理由:

1. SDK が **LRO のポーリング**(`Operation-Location` ヘッダー追跡、`update_id` の取り出し)を肩代わりする。REST だと `POST …/memory_stores/{name}:update_memories` → `GET …/updates/{update_id}` のポーリングを自前実装することになる
2. SDK が**プレビュー opt-in ヘッダーを自動付与**する。SDK の api-version は `v1` で、preview 機能は `Foundry-Features: MEMORY_STORES_V1_PREVIEW` ヘッダーで有効化される(`beta` サブクライアントを使うだけで付く)。REST 文書の `2025-11-15-preview` は同じ面の別表現で、**この表裏を手で合わせるのがプレビュー API の一番壊れやすい部分**(学び 4)
3. 認証は REST でもどのみち azure-identity(`DefaultAzureCredential`、audience `https://ai.azure.com/`)が要るので、依存削減にならない

REST パス(参考。ライブデバッグ時に curl で叩ける):`POST {project}/memory_stores?api-version=2025-11-15-preview`(作成)/ `POST …/memory_stores/{name}:search_memories`(検索)/ `POST …/memory_stores/{name}:update_memories` → `GET …/memory_stores/{name}/updates/{update_id}`(追加+LRO)/ `POST …/memory_stores/{name}:delete_scope`。

## 移植後の構成

```
ユーザー発言 ─▶ MemoryStore.search(query, user_id)      ─▶ "Relevant past information:\n- ..."
                (Foundry: search_memories, scope=user_id)    をプロンプト先頭に注入
             ─▶ travel_agent(MAF Agent, gpt-5.4-mini)     ─▶ 応答
             ─▶ MemoryStore.add(発言, role=user)          ─▶ 次ターン以降の検索でヒット
                MemoryStore.add(応答, role=assistant)
                (Foundry: begin_update_memories ×2、update_delay=0、update_id チェーン)
```

- `MemoryStore` は Protocol([src/travel_memory_maf/memory.py](./src/travel_memory_maf/memory.py))。実装は **FoundryMemoryStore**(実 API・ライブ用)と **InMemoryFakeStore**(オフラインテスト用。単語重なりの scripted 意味検索+user_id 分離)の 2 つ — corrective-rag の retriever 注入と同型
- ターンのロジックは [chat.py](./src/travel_memory_maf/chat.py) の `run_turn()` に分離し、「検索 → 注入 → 応答 → 追加」の順序・プロンプト書式(1 文字単位)・空応答 ValueError・「記憶 0 件でもヘッダー注入」という元アプリの挙動をテストで固定
- Streamlit → CLI(`--user` 必須、対話ループ+`--once` 単発+`--memories` 一覧+`--wait` LRO 完了待ち)

## 設計判断

### FoundryMemoryProvider(MAF の ContextProvider)を使わず、明示的な search/add にした

MAF には Foundry Memory の公式統合 `FoundryMemoryProvider` が既にあり、`Agent(..., context_providers=[provider])` の 1 行で「before_run で検索・注入、after_run で保存」が付く。それでも本ポートは元アプリと同じ**明示ループ**を選んだ:

1. Port 5 の主題は「mem0 の add/search が Foundry Memory の何に対応するか」の 1:1 置換であり、ContextProvider に隠すと対応関係(と LRO・debounce の存在)が見えなくなる
2. FoundryMemoryProvider の after_run は `update_delay=300`(5 分 debounce)の fire-and-forget で、「毎ターン即時 add」の元アプリと意味論が異なる。注入位置・書式も Provider 側の既定("## Memories" ヘッダー)になり、元アプリのプロンプト書式を保存できない
3. 明示ループは Protocol 注入でネットワークなしの順序検証ができる(オフラインテスト 23 件)

本番 SI では逆に Provider が第一候補になる(既存エージェントへの後付けが 1 行、検索の increment 管理も内蔵)— この対比自体が学び 3。

### update_delay=0 + update_id チェーン(mem0 の同期 add の近似)

Foundry の `update_delay` 既定 300 秒は「会話が続く間は更新をキャンセル&リセットし、会話終わりにまとめて抽出」というサービス側の想定。元アプリは毎ターン add なので `update_delay=0` で即時トリガーし、`previous_update_id` を scope ごとにチェーンして増分更新にする(公式 how-to の「update after each turn and chain updates」パターン)。既定は fire-and-forget、`--wait` / `wait_for_update=True` で LRO 完了まで待てる(ライブスモークはこちら。1 ターン 1 分程度かかることがある)。

### Memory ストアは Bicep 外(2 段デプロイ)

Memory ストアはプロジェクトの**データプレーン API** で作るため ARM/Bicep では書けない。corrective-rag の AI Search インデックスと同じく **Bicep(existing 参照のみ)+ [scripts/setup_memory.py](./scripts/setup_memory.py)** の 2 段構成にした。ストア構成に使うモデルはデプロイ済みのものを指すだけ: チャット gpt-5.4-mini(共有基盤)+埋め込み text-embedding-3-small(corrective-rag ポートが追加済み)。よって本ポートの main.bicep に新規 ARM リソースはない。

### 認証は「モデル=API キー、Memory=Entra ID」の二本立て

チャットモデルは他ポートと同じ OpenAI v1 エンドポイント+API キー。Memory Store API は **Entra ID のみ**(`DefaultAzureCredential`、要 `az login`)。同一プロジェクトに 2 種類の認証が混在するのはラボ構成の割り切り(本番はモデル側もキーレスに寄せるのが定石)。

## 実行

```bash
uv sync --extra dev
uv run pytest                      # オフライン(ネットワーク不要・23 件)

# --- ライブ(要 共有基盤 + az login + ../../.env)---
az deployment group create -g rg-maf-ports -f infra/main.bicep -p baseName=mafports
#   (existing 参照のみ。新規リソースなし — 出力の endpoint 確認用)

uv run python scripts/setup_memory.py     # Memory ストア作成(1 回。データプレーン)

uv run travel-memory-maf --user alice --wait --once "長距離便は必ず窓側席、機内食はベジタリアンです"
uv run travel-memory-maf --user alice --once "東京からロンドンの航空券、何をリクエストすべき?"
uv run travel-memory-maf --user alice --memories       # 抽出された記憶の確認
uv run travel-memory-maf --user alice                  # 対話モード(/memories, /quit)

uv sync --extra dev --extra live && uv run pytest -m live   # ライブスモーク
```

インフラ: 共有基盤のみ(existing 参照)。Memory ストアは従量(構成した chat/embedding モデルの利用分)でアイドルコストなし。撤去は `setup_memory.py --delete` またはリソースグループごと削除。

## 評価

[tests/eval_dataset.jsonl](./tests/eval_dataset.jsonl)(5 ケース)は全て**多ターンシナリオ**で、「前ターンの嗜好を後のターンが反映するか」を見る: 基本(座席+機内食)/ 推薦カテゴリの変化(低予算宿)/ 安全性(甲殻類アレルギー — 記憶欠落が実害になる例)/ **scope 分離**(同じ質問を別 user_id で流して漏れがないこと)/ **嗜好の更新**(ビーチ → 山への転向。Foundry の統合・矛盾解消が効くかの観察点)。実行は `--wait` でターン間の抽出完了を保証し、ターンごとの `TurnResult.prompt`(注入済み全文)を Foundry の Relevance / Task adherence 評価器に渡せる形にしてある。

## 検証結果(2026-07-31)

- オフラインテスト 23 passed / ruff clean / `az bicep build` OK(生成 json は削除)
- ライブスモーク・実ストア作成は未実施(呼び出し元で実施)。手順: `az login` → infra デプロイ(確認のみ)→ `setup_memory.py` → `--wait --once` を 2 ターン → `pytest -m live`。トレース到達の確認クエリ:

```bash
az monitor app-insights query --app appi-mafports -g rg-maf-ports \
  --analytics-query "dependencies | where timestamp > ago(30m) | summarize count() by name"
```

## 検証結果(2026-07-31 ライブ)

- `setup_memory.py` で Memory ストア作成成功(gpt-5.4-mini + text-embedding-3-small、Japan East プロジェクト)
- ライブスモーク **1 passed(139s)**: 嗜好を伝える(LRO 完了待ち)→ 別質問で嗜好が文脈注入されることを確認 → `delete_scope` で掃除
- **躓きと解決(重要)**: 初回は `search_memories` が 401 ResourceError(Memory サービスがストア構成の埋め込みモデルをプロジェクト MI で呼ぶが、**Bicep 作成のプロジェクトには model データプレーン権限が自動付与されない**)。`Cognitive Services OpenAI User` をプロジェクト/アカウント MI に割り当てて解決 — **shared.bicep に反映済み**。RBAC 伝播はノード間で不均一(今回は約5〜7分。片方のプローブが通った後もテストが数分 401 を返し続けた)

## 学び(MAF/Foundry vs 元構成)

1. **mem0 の `add` は同期、Foundry の add 相当は「LRO + debounce」— この意味論の差が移植の本丸だった。**mem0 は `add()` から戻れば次の `search` でヒットする。Foundry の `begin_update_memories` は抽出・統合を非同期ジョブ(約 1 分)で行い、しかも既定 `update_delay=300` 秒は「会話が続く間は処理を遅延し、まとめて抽出」というチャットアプリ前提の debounce。元アプリの「毎ターン即時 add」は `update_delay=0` + `previous_update_id` チェーンで再現できたが、**「add した事実がいつ search に見えるか」という結果整合性はコードでは消せない**。テスト設計(ライブスモークは `wait_for_update=True`)にも CLI 設計(既定 fire-and-forget + `--wait`)にも波及した。SI 的には「記憶の鮮度がターン単位で必要か、セッション単位でよいか」が Foundry Memory 適合性の最初の質問になる。
2. **`user_id` → `scope` は 1:1 だが、scope はライブラリの引数からサービスの一級概念に格上げされる。**mem0 の user_id はベクトル DB のメタデータフィルタにすぎない。Foundry の scope はクォータの単位(100 scopes/store・10,000 memories/scope)であり、`delete_scope` で GDPR 的な「このユーザーの記憶を全部消す」が 1 API になり、エージェントツール経由なら `{{$userId}}` で **Entra ID(または `x-memory-user-id` ヘッダー)から自動解決**される。低レベル API では毎リクエスト明示必須(自動解決なし)という非対称も要注意。マルチテナント SaaS の記憶分離を自前フィルタで作り込む必要がなくなるのは、mem0 構成に対する明確な優位。
3. **記憶の「事実抽出」がブラックボックスからサービス仕様になった — 引き換えにノブは減る。**mem0 も LLM で事実抽出するが、何がどう抽出されるかはライブラリ実装依存。Foundry は user_profile / chat_summary / procedural の **3 種に型付け**し、統合・矛盾解消(新しいアレルギー情報が古い情報を上書きする等)を仕様として明記、`user_profile_details` で抽出方針を自然言語指示できる。一方で埋め込みのチャンクや検索アルゴリズムには一切触れない(Qdrant 直と違い、インデックスも距離関数も見えない)。「記憶の品質をどう評価・チューニングするか」の答えが「ストア定義とプロンプト(抽出指示)」に集約される — corrective-rag(検索のレバーが全部見える)と正反対の設計思想で、両方触ると RAG とマネージド記憶の使い分けが立体的になる。
4. **プレビュー API の「バージョン」は 1 枚岩ではない — SDK の `v1` + `Foundry-Features` ヘッダーと REST の `2025-11-15-preview` が同じ面の表裏。**azure-ai-projects 2.4.0 は api-version `v1` で呼びつつ、`client.beta.*` サブクライアントが `Foundry-Features: MEMORY_STORES_V1_PREVIEW` ヘッダーを自動付与して preview 機能を有効化する(`allow_preview=True` は `beta` では暗黙)。REST 文書は `api-version=2025-11-15-preview` を使う。この対応を知らずに「SDK は古い v1 を使っている」と誤読すると REST に流れて LRO ポーリングを自前実装する羽目になる。**SDK 採用の決め手はまさにここ**(LRO の `Operation-Location` 追跡と feature ヘッダーを SDK が処理)で、プレビュー機能は「SDK があるなら SDK」の原則を強く支持する結果になった。
5. **MAF には Foundry Memory の公式 ContextProvider(`FoundryMemoryProvider`)が既にあり、「明示ループ」と「ミドルウェア注入」の 2 択になる。**installed grep で `agent_framework.foundry` → agent-framework-foundry 1.10.1 の `FoundryMemoryProvider` を確認(before_run: 初回に静的 user_profile 検索+ターン毎に increment 検索、after_run: fire-and-forget 更新)。本ポートは移植の忠実性とテスト可能性から明示ループを選んだが、既存 MAF エージェントに長期記憶を後付けするだけなら Provider が 1 行で済む。**「記憶をアプリのロジックとして書くか、エージェント基盤の関心事として注入するか」**はフレームワーク選定の分岐点で、LangGraph(checkpointer/store)にも同じ構図がある — mem0 のようなライブラリ手組みか、MAF+Foundry のようなプラットフォーム統合かの判断材料として、このポートの両実装(chat.py vs FoundryMemoryProvider)は良い比較教材になる。
