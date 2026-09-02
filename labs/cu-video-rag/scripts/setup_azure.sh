#!/usr/bin/env bash
# デプロイ済みリソースから .env を生成し、CU defaults にモデルデプロイを紐づける。
# 前提: az deployment group create -g rg-cu-video-rag -f infra/main.bicep 済み
set -euo pipefail
cd "$(dirname "$0")/.."

RG="${RG:-rg-cu-video-rag}"
DEP="${DEP:-cuvrag}"

out() { az deployment group show -g "$RG" -n "$DEP" --query "properties.outputs.$1.value" -o tsv; }

FOUNDRY_NAME=$(out foundryName)
FOUNDRY_ENDPOINT=$(out foundryEndpoint)
AOAI_ENDPOINT=$(out aoaiEndpoint)
STORAGE_NAME=$(out storageName)
SEARCH_NAME=$(out searchName)
SEARCH_ENDPOINT=$(out searchEndpoint)

AI_KEY=$(az cognitiveservices account keys list -n "$FOUNDRY_NAME" -g "$RG" --query key1 -o tsv)
SEARCH_ADMIN_KEY=$(az search admin-key show --service-name "$SEARCH_NAME" -g "$RG" --query primaryKey -o tsv)
STORAGE_KEY=$(az storage account keys list -n "$STORAGE_NAME" -g "$RG" --query "[0].value" -o tsv)

cat > .env << EOF
RG=$RG
REGION=japaneast
FOUNDRY_NAME=$FOUNDRY_NAME
FOUNDRY_ENDPOINT=$FOUNDRY_ENDPOINT
AOAI_ENDPOINT=$AOAI_ENDPOINT
AI_KEY=$AI_KEY
STORAGE_NAME=$STORAGE_NAME
STORAGE_KEY=$STORAGE_KEY
SEARCH_ENDPOINT=$SEARCH_ENDPOINT
SEARCH_ADMIN_KEY=$SEARCH_ADMIN_KEY
COMPLETION_MODEL=gpt-5.4-mini
COMPLETION_DEPLOYMENT=gpt-5.4-mini
EMBED_MODEL=text-embedding-3-small
EMBED_DEPLOYMENT=text-embedding-3-small
JUDGE_DEPLOYMENT=gpt-4.1-mini
EOF
echo "wrote .env (endpoint=$FOUNDRY_ENDPOINT)"

# CU defaults にモデルデプロイを紐づけ(GA 版で試し、失敗時の応答を表示して判断する)
uv run python scripts/run_pipeline.py defaults
