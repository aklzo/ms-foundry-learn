#!/usr/bin/env bash
# 全 probe を順に実行し、結果を logs/ に保存する。
# 前提: .env 設定済み + az login 済み(README「実行の前提」)。
set -u
cd "$(dirname "$0")"
mkdir -p logs
for dir in probes/*/; do
  name="$(basename "$dir")"
  [ -f "$dir/probe.py" ] || continue
  echo "=== $name ==="
  uv run python "$dir/probe.py" 2>&1 | tee "logs/${name}.log"
  echo
done
