# Port 15 delegated-access-hosted: MCP ツールサーバー(docs / suppliers / supplier-admin)
#
# ビルド(コンテキストはポートのルート。.dockerignore で .env・.cache・.venv を送らない):
#   docker build -f docker/tools/Dockerfile -t dah-tools .
#   az acr build -r <acr> -f docker/tools/Dockerfile -t dah-tools:<tag> .   # scripts/deploy_tools_server.sh
# 実行:
#   docker run --rm -p 8080:8080 -e ENTRA_TENANT_ID=... -e TOOLS_API_CLIENT_ID=... \
#     -e ENFORCEMENT_MODE=server dah-tools
#
# - 待ち受け 0.0.0.0:$PORT(既定 8080)、ヘルスチェック GET /healthz(認証なし)
# - MCP: POST /docs/mcp, /suppliers/mcp, /supplier-admin/mcp(ステートレス Streamable HTTP + JSON)
# - 依存は uv.lock から固定で入れる(search extra = azure-search-documents / azure-identity)。
#   ポート共通の依存(MAF 等)も入るが、ツールサーバーは import しない
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 依存だけ先に入れる(ソース変更でキャッシュを捨てない)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --extra search

# アプリ本体と同梱データ(文書のローカル検索用 data/docs と取引先マスタ data/suppliers.json)
COPY src ./src
COPY data ./data

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH=/app/src \
    SUPPLIERS_DATA=/app/data/suppliers.json \
    PORT=8080

RUN useradd --system --uid 10001 --no-create-home tools
USER 10001

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT', '8080'), timeout=3)"]

CMD ["python", "-m", "delegated_access_maf.tools_server.main"]
