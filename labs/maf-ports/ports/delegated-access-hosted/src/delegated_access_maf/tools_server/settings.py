"""MCP ツールサーバーの設定(環境変数)。

変数名はポート全体で 1 つの命名体系に揃える(``.env.example`` 参照):

- 共通: ``ENTRA_TENANT_ID`` / ``TOOLS_API_CLIENT_ID``(ツール API トークンの ``aud``)
- ツールサーバー: ``ENFORCEMENT_MODE``(``server`` | ``apim``)/ ``SEARCH_ENDPOINT`` /
  ``SEARCH_INDEX``(既定 ``internal-docs``)/ ``SEARCH_API_KEY``(任意。なければマネージド ID)/
  ``SUPPLIERS_DATA``(取引先マスタの JSON。既定は同梱の ``data/suppliers.json``)
- 方式 A(``apim``)専用: ``APIM_GATEWAY_SECRET``(APIM の秘密 Named Value ``dah-gateway-secret`` と
  同じ値。APIM を経由したことの証明に使う。``apim`` で空なら起動しない)
- 待ち受け: ``PORT``(既定 8080。Container Apps の targetPort と合わせる)

秘密(``SEARCH_API_KEY`` / ``APIM_GATEWAY_SECRET``)は ``repr`` に出さない(起動ログ・例外に載せない)。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast, get_args

from ..contracts import EnforcementMode

#: ポートのルート(src/delegated_access_maf/tools_server/settings.py から 3 つ上)。
#: コンテナでも同じ配置(/app/src + /app/data)にしてあるので同梱データの既定パスが共通になる
PORT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PORT_ROOT / "data"
DEFAULT_DOCS_DIR = DATA_DIR / "docs"
DEFAULT_SUPPLIERS_DATA = DATA_DIR / "suppliers.json"
#: APIM ポリシー(方式 A)。オフラインではエミュレーターがこの XML をそのまま読む
DEFAULT_POLICIES_DIR = PORT_ROOT / "infra" / "apim" / "policies"

DEFAULT_SEARCH_INDEX = "internal-docs"
DEFAULT_PORT = 8080


class SettingsError(ValueError):
    """必須の環境変数がない・値が不正。"""


@dataclass(frozen=True)
class ToolsServerSettings:
    tenant_id: str
    tools_client_id: str
    enforcement_mode: EnforcementMode = "server"
    search_endpoint: str | None = None
    search_index: str = DEFAULT_SEARCH_INDEX
    search_api_key: str | None = field(default=None, repr=False)
    suppliers_data: Path = DEFAULT_SUPPLIERS_DATA
    docs_dir: Path = DEFAULT_DOCS_DIR
    port: int = DEFAULT_PORT
    apim_gateway_secret: str | None = field(default=None, repr=False)

    def require_gateway_secret(self, mode: EnforcementMode | None = None) -> None:
        """``apim`` 方式なのにゲートウェイの秘密がなければ起動させない(迂回を黙って許さない)。"""
        if (mode or self.enforcement_mode) == "apim" and not self.apim_gateway_secret:
            raise SettingsError(
                "ENFORCEMENT_MODE=apim には APIM_GATEWAY_SECRET が必要です"
                "(APIM の Named Value dah-gateway-secret と同じ値)"
            )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> ToolsServerSettings:
        env = os.environ if env is None else env

        def required(name: str) -> str:
            value = (env.get(name) or "").strip()
            if not value:
                raise SettingsError(f"環境変数 {name} が未設定です")
            return value

        mode = (env.get("ENFORCEMENT_MODE") or "server").strip().lower()
        if mode not in get_args(EnforcementMode):
            raise SettingsError(f"ENFORCEMENT_MODE は server か apim です(指定値: {mode!r})")
        settings = cls(
            tenant_id=required("ENTRA_TENANT_ID"),
            tools_client_id=required("TOOLS_API_CLIENT_ID"),
            enforcement_mode=cast(EnforcementMode, mode),
            search_endpoint=(env.get("SEARCH_ENDPOINT") or "").strip() or None,
            search_index=(env.get("SEARCH_INDEX") or "").strip() or DEFAULT_SEARCH_INDEX,
            search_api_key=(env.get("SEARCH_API_KEY") or "").strip() or None,
            suppliers_data=Path(env.get("SUPPLIERS_DATA") or DEFAULT_SUPPLIERS_DATA),
            port=int(env.get("PORT") or DEFAULT_PORT),
            apim_gateway_secret=(env.get("APIM_GATEWAY_SECRET") or "").strip() or None,
        )
        settings.require_gateway_secret()
        return settings
