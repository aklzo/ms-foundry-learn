"""部品間の契約 — ヘッダー名・Entra のスコープとロール・MCP エンドポイント・ツール名。

このポートは 4 つの部品がトークンとヘッダーだけでつながる。どれか 1 つが名前を変えると
黙って「権限なし」になるため、名前はすべてここに集約し、各部品はこのモジュールから import する。

    利用者(CLI)──① ユーザートークン(aud = バックエンド API)──▶ 中間層バックエンド
    中間層 ──② OBO 交換(MSAL・機密クライアント)──▶ Entra ID ──▶ ツール API 宛ての委任トークン
    中間層 ──③ Authorization(Foundry 用のワークロードトークン)
              + x-client-tools-access-token(②の委任トークン)
              + x-ms-user-identity(①から取り出した利用者の oid)──▶ hosted agent(Foundry が転送)
    hosted agent ──④ Authorization: Bearer <②の委任トークン>──▶ APIM / MCP サーバー(最終判定)

公式手順: https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/use-on-behalf-of-flow
(2026-09-28 版。Foundry はトークンを交換も更新もせず、``x-client-*`` をコンテナへ転送するだけ)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# --- ヘッダー(③)-----------------------------------------------------------------

#: 中間層が OBO で得たツール API 宛ての委任トークン。``x-client-`` 接頭辞のヘッダーだけが
#: Foundry からコンテナへ転送される。値は ``Bearer`` なしの生トークン(公式手順どおり)。
#: コンテナ側の ResponseContext.client_headers ではキーが小文字になる。
TOOLS_TOKEN_HEADER = "x-client-tools-access-token"

#: 利用者の Entra オブジェクト ID(トークンではない)。Foundry がこれで利用者を識別し、
#: 会話履歴をユーザー単位に分離する。送るには中間層のワークロード ID に
#: カスタムの data action(UserIdentityImpersonation/action)が必要。
USER_IDENTITY_HEADER = "x-ms-user-identity"

#: 方式 A(apim)で「APIM を経由した」ことの証明。APIM が秘密の Named Value(dah-gateway-secret)を
#: バックエンド向けに付け、ツールサーバーは環境変数 APIM_GATEWAY_SECRET と定数時間で比較する。
#: 値は秘密(ログ・トレースに出さない)。エージェントや利用者は送らない(APIM が上書きする)。
APIM_GATEWAY_SECRET_HEADER = "x-apim-gateway-secret"

#: 送信側で必ずマスクするヘッダー(ログ・トレース・例外メッセージに出さない)
SENSITIVE_HEADERS = frozenset({"authorization", TOOLS_TOKEN_HEADER, APIM_GATEWAY_SECRET_HEADER})

# --- Entra ID(アプリ登録 2 つ)--------------------------------------------------------

#: 中間層バックエンドの API(利用者の CLI がこの宛先でトークンを取る)
BACKEND_API_SCOPE_NAME = "access_as_user"

#: MCP サーバー群をまとめて表す 1 つのリソース API(OBO の交換先)。
#: 3 つの MCP サーバーは同じ宛先のトークンを受け付けるので、OBO 交換は 1 回で済む。
TOOLS_API_SCOPE_NAME = "Tools.Access"

#: ツール API のアプリロール(利用者に割り当てる)。委任トークンの ``roles`` クレームに入る。
ROLE_SUPPLIERS_WRITE = "Suppliers.Write"   # 取引先の支払条件を更新できる(基幹 API の更新系)
ROLE_DOCS_FINANCE = "Docs.Finance"         # 経理向けの社内文書を検索できる

#: 認証済みの全社員に暗黙に与える文書ロール(AI Search の文書に付けるラベル)。
#: Entra 側には作らない — MCP サーバーが「有効なトークン = 社員」とみなして付与する。
BASELINE_DOC_ROLE = "Employee"

# --- MCP サーバー(④)-----------------------------------------------------------------

EnforcementMode = Literal["server", "apim"]
"""最終判定の置き場所。

- ``server``: 各 MCP サーバーが JWT(署名・発行者・宛先・期限・スコープ)とロールを自分で判定する
- ``apim``: APIM の validate-jwt ポリシーが宛先・スコープ・ロールを判定し、MCP サーバーは
  署名と期限だけを再検証する(文書の権限絞り込みに使うロールを読むため)
"""


@dataclass(frozen=True)
class McpServerSpec:
    """MCP サーバー 1 つ分の契約。``required_roles`` が空なら認証済みの全社員が使える。"""

    name: str
    path: str
    required_roles: frozenset[str]
    tools: tuple[str, ...]
    description: str


DOCS = McpServerSpec(
    name="docs",
    path="/docs/mcp",
    required_roles=frozenset(),
    tools=("search_documents",),
    description="社内文書の検索。文書ごとの閲覧権限は AI Search のセキュリティフィルターで絞る",
)
SUPPLIERS = McpServerSpec(
    name="suppliers",
    path="/suppliers/mcp",
    required_roles=frozenset(),
    tools=("list_suppliers", "get_supplier"),
    description="基幹 API(取引先マスタ)の参照",
)
SUPPLIER_ADMIN = McpServerSpec(
    name="supplier-admin",
    path="/supplier-admin/mcp",
    required_roles=frozenset({ROLE_SUPPLIERS_WRITE}),
    tools=("update_payment_terms",),
    description="基幹 API(取引先マスタ)の更新。Suppliers.Write ロールの利用者だけ",
)

MCP_SERVERS: tuple[McpServerSpec, ...] = (DOCS, SUPPLIERS, SUPPLIER_ADMIN)

# --- エラーの取り決め -----------------------------------------------------------------

#: エージェントが利用者に返す定型文(権限不足でツールが使えなかったとき)。
#: app-only(エージェント自身の権限)への切り替えはしない — 公式手順の「黙って app-only に
#: 切り替えるな」に従い、失敗はそのまま利用者と中間層へ返す。
MSG_FORBIDDEN = "この操作を行う権限がありません。必要であれば管理者に権限の付与を依頼してください。"
MSG_REAUTH = "サインインの有効期限が切れたか、追加の認証が必要です。もう一度サインインしてください。"
