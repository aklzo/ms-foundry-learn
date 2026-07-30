# awesome-llm-apps 棚卸しと移植ロードマップ

> **調査日:** 2026-07-31 / 対象: `~/oss/awesome-llm-apps`(README + 主要コードを実読、フレームワークは import 文で実確認)
> 総数 156 プロジェクト(requirements.txt 基準)。フレームワーク分布: streamlit 73 / langchain 54 / openai 53 / agno 44 / google-adk 21 / openai-agents 12 / mem0 7 / langgraph 4 / crewai 4 / autogen 3

## 選定基準

1. **MAF/Foundry の境界を体感できる**(協調パターン・ツール・状態管理がある。1ショット LLM ラッパーは除外)
2. **パターン重複を避ける**(同型は代表1本)
3. **依存が生きている**(Ollama 前提・死んだ SaaS 依存・UI が本体のものは除外)
4. **Foundry 機能カバレッジ**(Web search / Code Interpreter / Memory / AI Search / MCP / Voice / 評価 / トレースを第1〜2弾で一巡)

## Wave 1(第1弾・移植順)

| # | プロジェクト | 元FW | 検証するパターン | 使う Foundry 機能 | 難易度 |
| --- | --- | --- | --- | --- | --- |
| 1 | starter/ai_startup_trend_analysis_agent | Agno | **逐次ワークフロー最小形**(収集→要約→分析) | Web 検索ツール、トレース、評価 | 低 |
| 2 | starter/mixture_of_agents | 素SDK | **並列ファンアウト+アグリゲータ** | 並列 Workflow、評価(回答品質比較) | 低 |
| 3 | starter/openai_research_agent | OpenAI Agents SDK | **handoff / トリアージ型**+構造化出力 | Web 検索、構造化出力、トレース、評価 | 中 |
| 4 | rag/corrective_rag | LangChain+LangGraph | **補正ループ(CRAG)**: 採点→書換→Web フォールバック | **Azure AI Search**(Bicep 固有リソース初登場)、採点→評価器、ノード別トレース | 中 |
| 5 | memory/ai_travel_agent_memory | OpenAI+mem0 | **長期記憶**(mem0→Foundry Memory の 1:1) | **Foundry Memory(プレビュー)**、トレース | 低 |
| 6 | mcp/github_mcp_agent | Agno | **リモート MCP 接続**(PAT 認証) | **MCP ツール(GA)**、トレース | 低 |
| 7 | advanced/agent_teams/ai_game_design_agent_team | AutoGen/AG2(旧Swarm) | **ハンドオフ・リング+共有 state+動的プロンプト**(MAF 表現力の試金石) | GroupChat/Handoff 相当、トレース、評価 | 中 |

- 1〜3 は追加インフラ不要(共有基盤のみ)。4 で AI Search、5 で Memory(プレビュー)、6 で MCP が初登場し、Bicep とテストの型を段階的に拡張する。
- Wave 1 で Sequential / Parallel / Handoff / 補正ループ / RAG / Memory / MCP を一巡。**Code Interpreter・Voice・Foundry IQ・Routines は Wave 2 に回す。**

## Wave 2(候補ショートリスト)

| プロジェクト | 検証するもの |
| --- | --- |
| advanced/agent_teams/ai_vc_due_diligence_agent_team | 7段 Sequential+state 受渡+**Code Interpreter** 直マップ(ADK 比較) |
| advanced/agent_teams/ai_legal_agent_team | Team 委譲+RAG(Qdrant→AI Search/File Search)+groundedness 評価 |
| rag/rag_database_routing | 複数ナレッジソース振り分け→**Foundry IQ** 検証 |
| voice/insurance_claim_live_agent_team | **Voice Live API**+状態管理+決定論ルール(SI 実務に最も近い) |
| always_on/always_on_hn_briefing_agent | 常時稼働型→**Routines / ホステッドエージェント**+運用監視 |
| game/ai_chess_agent | nested chat 対戦型(希少パターン)+対局トレース |
| advanced/agent_teams/ai_services_agency | 通信グラフ制約(Agency Swarm)→MAF グラフ表現力の境界測定 |
| advanced_llm/gpt_oss_critique_improvement_loop | 生成→批評→改訂ループ+**AI judge 評価**(最小コスト) |
| advanced/agent_teams/multimodal_coding_agent_team | E2B→**Code Interpreter** 置換+vision 入力 |
| starter/ai_data_analysis_agent | DuckDB 分析→**Code Interpreter** 置換の分かりやすい教材 |

## 対象外の方針(全カテゴリ共通)

- **Ollama/ローカル LLM 前提**(rag 7本、memory 2本ほか): ローカル性が主題のため Foundry 化で意義消失
- **UI が本体**(generative_ui_agents 全7本、Electron/Next.js 系): CopilotKit+AG-UI 依存。バックエンド MAF 化は Wave 3 以降の検討事項
- **死んだ/重い SaaS 依存**: MultiOn(終了)、Contextual AI(競合 PaaS)、FIRE-1 等
- **FT チュートリアル・最適化ツール類**: エージェントでない
- **crash_course 2種**(ADK/OpenAI SDK 各10章超): 個別移植せず、必要なら「MAF 版クラッシュコース」を別途書く素材

---

## カテゴリ別詳細

### A. starter_ai_agents(16)

| プロジェクト | 目的 | FW | パターン | 難易度 | Foundry マッピング | 価値 |
|---|---|---|---|---|---|---|
| ai_startup_trend_analysis_agent | ニュース収集→要約→トレンド分析 | Agno | 直列3段 | 低 | Sequential Workflow+Web search | **高** |
| mixture_of_agents | 複数LLM並列回答→集約 | 素SDK | 並列+アグリゲータ | 低 | 並列 Workflow+評価 | **高** |
| openai_research_agent | トリアージ→調査→レポート | OpenAI Agents SDK | handoff 型 | 中 | Web search+構造化出力+トレース | **高** |
| ai_data_analysis_agent | CSV/Excel を SQL で自然言語分析 | Agno | single+tools | 中 | **Code Interpreter がほぼ完全代替** | 高(Wave2) |
| ai_data_visualisation_agent | 生成コードをサンドボックス実行 | 素SDK | code-gen+実行 | 中 | Code Interpreter(E2B 置換) | 高(Wave2) |
| ai_life_insurance_advisor_agent | 保険必要額算定+商品リサーチ | Agno | 計算と LLM の分離 | 中 | Code Interpreter+Web search | 高(Wave2) |
| ai_travel_agent / ai_blog_to_podcast / ai_breakup_recovery / ai_medical_imaging / xai_finance / ai_meme_generator(browser-use) | — | — | — | — | 同型重複・外部キー多・browser-use 依存等 | 中 |
| ai_music_generator / ai_reasoning / multimodal_ai_agent / web_scraping(ScrapeGraphAI) | — | — | — | — | 1ショット・FW 固有 | 低 |

### B. advanced_ai_agents(53)

**multi_agent_apps/agent_teams(17)— 主要抜粋:**

| プロジェクト | 目的 | FW | パターン | 難易度 | Foundry マッピング | 価値 |
|---|---|---|---|---|---|---|
| ai_game_design_agent_team | ゲーム企画4役分担 | AG2(旧Swarm) | **ハンドオフ・リング+共有 context** | 中 | Handoff/GroupChat+トレース | **高** |
| ai_legal_agent_team | 法務レビュー+判例調査 | agno Team+Knowledge | Team 委譲+RAG | 中 | AI Search/File Search+groundedness 評価 | **高** |
| ai_vc_due_diligence_agent_team | 投資DD(7段+code exec+画像) | Google ADK | Sequential 7段+state | 中 | **Code Interpreter 直マップ**+Bing grounding | **高** |
| ai_seo_audit_team | SEO監査(MCP 統合) | Google ADK | Sequential+agent-as-tool+MCP | 中 | MCP そのまま活用 | 高 |
| ai_services_agency | 5役エージェンシー(通信グラフ) | Agency Swarm | **有向グラフ通信制約** | 中 | MAF グラフ表現力の試験台 | 高 |
| ai_mental_wellbeing_agent | メンタル評価→行動計画 | AG2(旧Swarm) | handoff 循環+共有 state | 中 | Handoff+安全性評価器 | 高 |
| multi_agent_researcher | HN 調査→記事生成 | agno Team | Team 委譲(最小) | 低 | Web search+トレース | 中 |
| multimodal_coding_agent_team | 問題画像→コード生成→実行 | agno+E2B | 逐次3体+vision | 中 | **E2B→Code Interpreter 置換** | 中 |
| devpulse_ai / trust_gated_agent_team / product_launch_intelligence / ai_financial_coach / ai_finance_agent_team / ag2_adaptive_research_team / ai_recruitment_agent_team / ai_sales_intelligence 他 | — | — | — | — | LLM採点→評価器、監査トレース、route 型等それぞれ一芸 | 中 |
| ai_travel_planner_agent_team(フルスタック SaaS)/ ai_news_and_podcast(Celery 4プロセス)/ ai_home_renovation・multimodal_uiux(ADK artifact 依存)/ ai_negotiation(AG-UI 依存)等 | — | — | — | 高 | インフラ・UI 過剰 | 低〜中 |

**single_agent_apps(18):** ai_agent_governance(ポリシー割込→MAF middleware、中)、ai_customer_support_agent(mem0→Memory 検証台、中)、ai_deep_research_agent(2段直列、中)、ai_system_architect_r1(推論・生成分離、中)ほかは低〜中。windows_use / research_agent_gemini(プレビューAPI 全面依存)は対象外。

**autonomous_game_playing(3):** ai_chess_agent(**nested chat 対戦型・希少**、高)、ai_tic_tac_toe(マルチモデル比較、中)、ai_3dpygame_r1(browser-use+SaaS 依存、低)。

### C. rag_tutorials(24)+ mcp_ai_agents(6)

| プロジェクト | 目的 | FW | 難易度 | Foundry マッピング | 価値 |
|---|---|---|---|---|---|
| corrective_rag | CRAG 補正ループ | LangGraph | 中 | **MAF Workflows ショーケース**+AI Search+評価 | **高** |
| rag_database_routing | 3専門DB 振り分け | LangChain+agno | 中 | **Foundry IQ 直接対応** | **高** |
| agentic_rag_gpt5 | agentic RAG 最小形 | agno | 低 | File Search/AI Search テンプレ | 高 |
| agentic_rag_with_reasoning | 推論過程可視化 RAG | agno | 低 | トレーシングのデモ素材 | 高 |
| agentic_typed_rag_pydanticai | 型付き応答+引用検証 | pydantic-ai | 中 | 構造化出力+groundedness 評価 | 高 |
| hybrid_search_rag | ハイブリッド検索+リランク | RAGLite | 中 | AI Search 標準機能で直接対応 | 中 |
| rag-as-a-service / autonomous_rag / vision_rag / gemini_agentic_rag / ai_blog_search / rag_agent_cohere | — | — | — | — | 中 |
| Ollama 前提7本+math_agent(DSPy)+multimodal_agentic(ADK+React)+contextualai+rag_chain+failure_diagnostics | — | — | — | — | 低 |
| **github_mcp_agent** | GitHub 自然言語照会 | agno | 低 | **リモート MCP(GA)+PAT で最小工数検証** | **高** |
| browser_mcp_agent | 自然言語ブラウザ操作 | mcp-agent | 低 | Browser Automation/Playwright MCP | 高 |
| ai_travel_planner_mcp_agent_team | 複数 MCP 束ね | agno | 中 | MultiMCP+トレース | 高 |
| multi_mcp_agent_router / notion_mcp_agent | — | — | 中/低 | ルーター LLM 化 / リモート MCP | 中 |
| multi_mcp_agent(Google OAuth stdio) | — | — | 高 | OAuth 系のリモート化が壁 | 中 |

### D. advanced_llm_apps / agent_skills / generative_ui / crash_course

| プロジェクト | 目的 | 難易度 | Foundry マッピング | 価値 |
|---|---|---|---|---|
| memory/ai_travel_agent_memory | 嗜好記憶の旅行相談 | 低 | **mem0→Foundry Memory 1:1(user profile+chat summary)。Qdrant 運用消滅** | **高** |
| memory/multi_llm_memory | 複数 LLM で記憶共有 | 低 | 記憶のモデル非依存性の実証 | **高** |
| gpt_oss_critique_improvement_loop | 生成→批評→改訂 | 低 | Workflow+**AI judge 評価**+トレースの三点セット | 中 |
| memory/その他4本 | — | — | ローカル性主題・依存死亡・thread で足りる等 | 低〜中 |
| chat_with_X(7種)/ resume_job_matcher 等 | — | — | RAG 定型 | 低 |
| agent_skills(7)| SKILL.md 型 | — | advisor-orchestrator-worker は fan-out+judge の**設計パターンとして輸入価値** | 低〜中 |
| generative_ui_agents(7)| CopilotKit+AG-UI+Next.js | 中〜高 | バックエンドのみ MAF 化なら starter/financial-coach が候補(Wave 3) | 低〜中 |
| crash_course(ADK 10章 / OpenAI SDK 11章) | チュートリアル集 | — | MAF 版クラッシュコースの対にする素材 | 参考 |
