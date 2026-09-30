"""ツールサーバーの起動口(uvicorn)。

    uv run python -m delegated_access_maf.tools_server.main           # ローカル(ポートの .env を読む)
    docker run -p 8080:8080 --env-file .env <image>                   # docker/tools/Dockerfile

- 待ち受け: ``0.0.0.0:$PORT``(既定 8080)。ヘルスチェックは ``GET /healthz``(認証なし)
- ``ENFORCEMENT_MODE``: ``server``(方式 B: このサーバーが最終判定)/ ``apim``(方式 A: APIM の
  後ろに置く。宛先・スコープ・ロールは APIM、ここは署名と期限だけ再検証)。``apim`` では
  ``APIM_GATEWAY_SECRET``(APIM の秘密 Named Value ``dah-gateway-secret`` と同じ値)が必須で、
  空なら起動しない。APIM が付ける ``x-apim-gateway-secret`` がない要求(迂回)は 403
- 文書検索: ``SEARCH_ENDPOINT`` があれば Azure AI Search(``SEARCH_API_KEY`` がなければ
  マネージド ID)。なければ同梱の ``data/docs`` をメモリで検索する(ローカル確認用。警告を出す)
- 取引先マスタ: ``SUPPLIERS_DATA``(既定は同梱の ``data/suppliers.json``。再起動で初期値に戻る)
"""

from __future__ import annotations

import logging
import os

import httpx
import uvicorn
from starlette.applications import Starlette

from .app import create_app, describe, make_validator
from .docs_search import AzureSearchDocs, DocsSearch, InMemoryDocs
from .settings import PORT_ROOT, ToolsServerSettings
from .suppliers import SupplierStore

logger = logging.getLogger("delegated_access_maf.tools_server")


def build_docs_search(settings: ToolsServerSettings) -> DocsSearch:
    if settings.search_endpoint:
        return AzureSearchDocs.create(
            endpoint=settings.search_endpoint,
            index=settings.search_index,
            api_key=settings.search_api_key,
        )
    logger.warning(
        "SEARCH_ENDPOINT が未設定のため、同梱の文書(%s)をメモリで検索します(ローカル確認用)",
        settings.docs_dir,
    )
    return InMemoryDocs.from_dir(settings.docs_dir)


def build_app(settings: ToolsServerSettings) -> Starlette:
    # JWKS 取得用。プロセスと同じ寿命(uvicorn の終了で破棄)
    http_client = httpx.AsyncClient(timeout=httpx.Timeout(10.0), follow_redirects=False)
    app = create_app(
        settings,
        validator=make_validator(settings, http_client=http_client),
        docs=build_docs_search(settings),
        suppliers=SupplierStore.from_json(settings.suppliers_data),
    )
    logger.info("tools server %s", describe(app))
    return app


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # ローカル実行ではポート直下の .env を読む(コンテナでは環境変数を直接渡す)
    env_file = PORT_ROOT / ".env"
    if env_file.is_file():
        from dotenv import load_dotenv

        load_dotenv(env_file, override=False)
    settings = ToolsServerSettings.from_env()
    uvicorn.run(
        build_app(settings),
        host="0.0.0.0",
        port=settings.port,
        # Container Apps / APIM の前段が付ける X-Forwarded-* を信頼する(ログの接続元表示のため)
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
