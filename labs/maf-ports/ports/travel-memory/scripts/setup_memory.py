"""Foundry Memory ストアの作成(ライブ専用・データプレーン)。

元アプリの ``Memory.from_config({"vector_store": {"provider": "qdrant", ...}})``
(ローカル Qdrant にコレクションを持つ)に対応する事前バッチ。Memory ストア
は ARM/Bicep では書けない(プロジェクトのデータプレーン API)ため、
corrective-rag のインデックス作成と同じ「2 段デプロイ」構成にする:

1. infra/main.bicep — 共有基盤の existing 参照のみ(固有 ARM リソースなし)
2. 本スクリプト — Memory ストア作成(azure-ai-projects SDK)

ストア構成(公式 how-to の既定に沿う):

- chat_model / embedding_model: 記憶の抽出・統合・検索に使うモデルデプロイ名。
  共有基盤の gpt-5.4-mini と、corrective-rag ポートがデプロイ済みの
  text-embedding-3-small を指す(どちらもデプロイ済みであること)
- user_profile / chat_summary / procedural の 3 種を有効化
- default_ttl_seconds=0(無期限。mem0 版に TTL がないことに合わせる)

実行(要 ``az login``。Memory API は Entra ID 認証のみ):

    uv run python scripts/setup_memory.py             # 作成(存在すればスキップ)
    uv run python scripts/setup_memory.py --recreate  # 削除して作り直す
    uv run python scripts/setup_memory.py --delete    # 削除のみ

注意: Memory は **パブリックプレビュー**(README 冒頭の注意を参照)。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PORT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORT_ROOT / "src"))

from travel_memory_maf.config import TravelMemorySettings

#: 既定の埋め込みデプロイ名(ports/corrective-rag/infra/main.bicep が共有
#: Foundry アカウントへ追加済み)
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


def main() -> None:
    parser = argparse.ArgumentParser(description="travel-memory の Memory ストア作成")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="既存ストアを削除してから作り直す(保存済み記憶は全 scope 消える)",
    )
    parser.add_argument("--delete", action="store_true", help="ストアを削除して終了")
    parser.add_argument(
        "--chat-model",
        default=None,
        help="記憶処理に使うチャットモデルのデプロイ名(既定: FOUNDRY_MODEL)",
    )
    parser.add_argument(
        "--embedding-model",
        default=os.environ.get("MEMORY_STORE_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        help=f"埋め込みモデルのデプロイ名(既定: {DEFAULT_EMBEDDING_MODEL})",
    )
    args = parser.parse_args()

    settings = TravelMemorySettings.from_env()
    chat_model = args.chat_model or settings.model

    from azure.ai.projects import AIProjectClient
    from azure.core.exceptions import ResourceNotFoundError
    from azure.identity import DefaultAzureCredential

    client = AIProjectClient(
        endpoint=settings.project_endpoint, credential=DefaultAzureCredential()
    )
    stores = client.beta.memory_stores

    if args.recreate or args.delete:
        try:
            stores.delete(settings.memory_store)
            print(f"deleted memory store: {settings.memory_store}")
        except ResourceNotFoundError:
            print("no existing memory store to delete")
        if args.delete:
            return

    try:
        existing = stores.get(settings.memory_store)
        print(f"memory store already exists: {existing.name} (id={existing.id})")
        print(f"  definition: {existing.definition}")
        return
    except ResourceNotFoundError:
        pass

    from azure.ai.projects.models import MemoryStoreDefaultDefinition, MemoryStoreDefaultOptions

    definition = MemoryStoreDefaultDefinition(
        chat_model=chat_model,
        embedding_model=args.embedding_model,
        options=MemoryStoreDefaultOptions(
            user_profile_enabled=True,
            chat_summary_enabled=True,
            procedural_memory_enabled=True,
            default_ttl_seconds=0,  # 無期限(mem0 版に TTL がないことに合わせる)
        ),
    )
    store = stores.create(
        name=settings.memory_store,
        definition=definition,
        description="travel-memory port: 旅行相談チャットの長期記憶(mem0 置換)",
    )
    print(f"created memory store: {store.name} (id={store.id})")
    print(f"  chat_model={chat_model} embedding_model={args.embedding_model}")


if __name__ == "__main__":
    main()
