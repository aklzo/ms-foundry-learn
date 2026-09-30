#!/usr/bin/env bash
# MCP ツールサーバーのイメージを ACR でビルドし、infra/main.bicep を toolsImage 付きで再デプロイする
# (Container Apps 2 つ = 方式 B の ca-dah-tools-srv / 方式 A の APIM 裏 ca-dah-tools-gw、と APIM)。
# **既定は dry-run**(実行するコマンドを表示するだけ)。--apply で実行する。
#
#   scripts/deploy_tools_server.sh --resource-group rg-maf-ports --base-name mafports \
#       --apim-publisher-email you@example.com            # dry-run
#   ... --apply                                           # 実行(az login 済み)
#
# 手順:
#   0. APIM → apim モードのツールサーバーの共有シークレットを用意する(既存の Named Value
#      dah-gateway-secret を引き継ぐ。無ければ生成)。値は 0600 の一時パラメーターファイルで渡し、表示しない
#   1. 本テンプレートのデプロイ(名前 dah-infra)が無ければ、toolsImage なしで「器」を作る
#      (ACR・MI・Container Apps〈quickstart イメージ〉・APIM・AI Search)
#   2. az acr build(ACR Tasks)でイメージをビルド。ACR Tasks が使えないサブスクリプション
#      (無料クレジット等)は --local-build で docker build + push
#   3. toolsImage=<acr>/dah-tools:<tag> で main.bicep を再デプロイ(Bicep を唯一の正にする。
#      az containerapp update で直接いじらない — 次の Bicep デプロイで戻るため)
#   4. 2 つのツールサーバーの /healthz を確認し、TOOLS_BASE_URL(方式 A / B)を表示
#
# 前提: infra/main.bicep の toolsApiClientId に渡す TOOLS_API_CLIENT_ID(scripts/setup_entra.py の出力)。
# ビルドコンテキストはポートのルート(docker/tools/Dockerfile)。.venv 等を送らないよう .dockerignore が要る。
set -euo pipefail

PORT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOYMENT_NAME="dah-infra"
IMAGE_REPO="dah-tools"
HEALTH_PATH="/healthz"

APPLY=0
LOCAL_BUILD=0
RESOURCE_GROUP=""
BASE_NAME=""
PUBLISHER_EMAIL=""
SEARCH_SKU="free"
MIN_REPLICAS="0"
TAG="$(date +%Y%m%d-%H%M%S)"
CLIENT_ID="${TOOLS_API_CLIENT_ID:-}"

usage() {
  sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | grep '^#' | sed 's/^# \{0,1\}//'
  cat <<'EOF'

options:
  --resource-group <rg>          共有基盤の RG(必須)
  --base-name <name>             共有基盤の baseName(必須)
  --apim-publisher-email <mail>  APIM の発行者メール(必須)
  --tools-api-client-id <id>     既定は環境変数 TOOLS_API_CLIENT_ID
  --search-sku free|basic        既定 free(1 サブスクリプション 1 つまで)
  --min-replicas 0|1             既定 0(スケールゼロ)
  --tag <tag>                    イメージタグ(既定は日時)
  --local-build                  az acr build の代わりに docker build + push
  --apply                        実行する(既定は dry-run)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --resource-group) RESOURCE_GROUP="$2"; shift 2 ;;
    --base-name) BASE_NAME="$2"; shift 2 ;;
    --apim-publisher-email) PUBLISHER_EMAIL="$2"; shift 2 ;;
    --tools-api-client-id) CLIENT_ID="$2"; shift 2 ;;
    --search-sku) SEARCH_SKU="$2"; shift 2 ;;
    --min-replicas) MIN_REPLICAS="$2"; shift 2 ;;
    --tag) TAG="$2"; shift 2 ;;
    --local-build) LOCAL_BUILD=1; shift ;;
    --apply) APPLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown option $1" >&2; usage >&2; exit 2 ;;
  esac
done

missing=()
[[ -n "$RESOURCE_GROUP" ]] || missing+=("--resource-group")
[[ -n "$BASE_NAME" ]] || missing+=("--base-name")
[[ -n "$PUBLISHER_EMAIL" ]] || missing+=("--apim-publisher-email")
if [[ -z "$CLIENT_ID" ]]; then
  if [[ $APPLY -eq 1 ]]; then missing+=("--tools-api-client-id(または TOOLS_API_CLIENT_ID)"); fi
  CLIENT_ID="<TOOLS_API_CLIENT_ID>"
fi
if [[ ${#missing[@]} -gt 0 ]]; then
  echo "error: 未指定: ${missing[*]}" >&2
  exit 2
fi

# 表示してから実行(dry-run では表示だけ)
run() {
  printf '+' >&2
  printf ' %q' "$@" >&2
  printf '\n' >&2
  if [[ $APPLY -eq 1 ]]; then "$@"; fi
}

# デプロイ出力を読む(dry-run ではプレースホルダー)
output() {
  if [[ $APPLY -eq 1 ]]; then
    az deployment group show -g "$RESOURCE_GROUP" -n "$DEPLOYMENT_NAME" \
      --query "properties.outputs.$1.value" -o tsv
  else
    echo "<$1>"
  fi
}

SECRET_FILE=""
SECRET_PARAM=""
cleanup() { if [[ -n "$SECRET_FILE" ]]; then rm -f "$SECRET_FILE"; fi; }
trap cleanup EXIT

# ゲートウェイ共有シークレット: 既存の Named Value を引き継ぐ(毎回変えると新リビジョンと切替の隙間ができる)
prepare_gateway_secret() {
  if [[ $APPLY -ne 1 ]]; then
    SECRET_PARAM="@<一時ファイル: apimGatewaySecret = 既存値の引き継ぎ or 新規生成。値は表示しない>"
    return
  fi
  local apim secret=""
  apim="$(az deployment group show -g "$RESOURCE_GROUP" -n "$DEPLOYMENT_NAME" \
    --query properties.outputs.apimName.value -o tsv 2>/dev/null || true)"
  if [[ -n "$apim" ]]; then
    secret="$(az apim nv show-secret -g "$RESOURCE_GROUP" -n "$apim" \
      --named-value-id dah-gateway-secret --query value -o tsv 2>/dev/null || true)"
  fi
  if [[ -n "$secret" ]]; then
    echo "  既存のゲートウェイ共有シークレットを引き継ぐ" >&2
  else
    echo "  ゲートウェイ共有シークレットを新規生成する" >&2
    secret="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  fi
  SECRET_FILE="$(mktemp)"
  chmod 600 "$SECRET_FILE"
  printf '{"$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#", "contentVersion": "1.0.0.0", "parameters": {"apimGatewaySecret": {"value": "%s"}}}\n' \
    "$secret" > "$SECRET_FILE"
  SECRET_PARAM="@$SECRET_FILE"
}

deploy_bicep() {
  run az deployment group create -g "$RESOURCE_GROUP" -n "$DEPLOYMENT_NAME" \
    -f "$PORT_ROOT/infra/main.bicep" \
    -p "$SECRET_PARAM" \
    -p baseName="$BASE_NAME" toolsApiClientId="$CLIENT_ID" apimPublisherEmail="$PUBLISHER_EMAIL" \
       searchSku="$SEARCH_SKU" toolsMinReplicas="$MIN_REPLICAS" toolsImage="$1" \
    -o none
}

[[ $APPLY -eq 1 ]] || echo "[dry-run] 以下のコマンドを表示するだけ(--apply で実行)" >&2

echo "# 0. ゲートウェイ共有シークレット" >&2
prepare_gateway_secret

echo "# 1. 器(ACR 等)の確認" >&2
if [[ $APPLY -eq 1 ]] && az deployment group show -g "$RESOURCE_GROUP" -n "$DEPLOYMENT_NAME" -o none 2>/dev/null; then
  echo "  既存のデプロイ $DEPLOYMENT_NAME を使う" >&2
else
  echo "  (デプロイ $DEPLOYMENT_NAME が無ければ)toolsImage なしで器を作る" >&2
  deploy_bicep ""
fi

ACR_NAME="$(output acrName)"
LOGIN_SERVER="$(output acrLoginServer)"
IMAGE="$LOGIN_SERVER/$IMAGE_REPO:$TAG"

echo "# 2. イメージのビルド → $IMAGE" >&2
if [[ ! -f "$PORT_ROOT/docker/tools/Dockerfile" ]]; then
  echo "error: $PORT_ROOT/docker/tools/Dockerfile が無い" >&2
  exit 2
fi
if [[ $LOCAL_BUILD -eq 1 ]]; then
  run docker build -f "$PORT_ROOT/docker/tools/Dockerfile" -t "$IMAGE" "$PORT_ROOT"
  run az acr login -n "$ACR_NAME"
  run docker push "$IMAGE"
else
  run az acr build -r "$ACR_NAME" -t "$IMAGE_REPO:$TAG" -f "$PORT_ROOT/docker/tools/Dockerfile" "$PORT_ROOT"
fi

echo "# 3. toolsImage 付きで再デプロイ(Container Apps 2 つ + APIM)" >&2
deploy_bicep "$IMAGE"

SERVER_URL="$(output toolsServerUrl)"
GATEWAY_BACKEND_URL="$(output toolsGatewayBackendUrl)"
APIM_URL="$(output apimGatewayUrl)"

echo "# 4. ヘルスチェック(スケールゼロからの起動に数十秒かかることがある)" >&2
for url in "$SERVER_URL" "$GATEWAY_BACKEND_URL"; do
  run curl -fsS --retry 5 --retry-delay 10 --retry-all-errors --max-time 60 "$url$HEALTH_PATH"
done

cat <<EOF
# --- scripts/deploy_tools_server.sh の出力 ---
# 方式 A(APIM で判定): scripts/deploy_hosted_agent.py --mode apim --tools-base-url に渡す
TOOLS_BASE_URL_APIM=$APIM_URL
# 方式 B(MCP サーバーで判定): scripts/deploy_hosted_agent.py --mode server --tools-base-url に渡す
TOOLS_BASE_URL_SERVER=$SERVER_URL
# APIM 裏のツールサーバーの直 URL(迂回テスト用。エージェントには渡さない)
TOOLS_GATEWAY_BACKEND_URL=$GATEWAY_BACKEND_URL
EOF
