#!/usr/bin/env bash
# データセット生成後の全評価を一括実行(analyze はスキップ式なので再実行=再開)。
set -euo pipefail
cd "$(dirname "$0")/.."
RUN="uv run python scripts/run_pipeline.py"

echo "=== upload ===" && $RUN upload
echo "=== analyze prebuilt ===" && $RUN analyze --analyzer prebuilt-videoSearch --tag prebuilt --parallel 4
echo "=== analyze custom ===" && $RUN analyze --analyzer videoSearchJa --tag custom --parallel 4
echo "=== cer ===" && $RUN cer --tag prebuilt | tail -5
echo "=== index ===" && for c in A B C D; do $RUN index --config $c; done
sleep 20  # インデックス反映待ち
echo "=== retrieval eval ===" && $RUN eval --configs A,B,C,D
echo "=== rag answers (A, C) ===" && $RUN rag-answer --config A && $RUN rag-answer --config C
echo "=== ragas (A, C) ===" && $RUN ragas --config A && $RUN ragas --config C
echo "ALL_DONE"
