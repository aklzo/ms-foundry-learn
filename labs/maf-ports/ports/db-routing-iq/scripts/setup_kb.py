"""Foundry IQ knowledge base のセットアップ(ライブ専用)。

元アプリの「Streamlit 上で PDF アップロード → チャンク分割 → Qdrant 3
コレクションへ投入」に対応する事前バッチ。作成順:

    1. 検索インデックス ×3(products / support / finance)
    2. data/<domain>/*.md をチャンク化して投入
    3. searchIndex knowledge source ×3(インデックスを包む)
    4. knowledge base ×1(3 ソース+LLM クエリプランニング low)

knowledge source / knowledge base はデータプレーン API のため Bicep では
作れない(infra/main.bicep はサービスのみ。2 段デプロイの定型 —
tech-selection-guide §2-2)。REST(api-version 2026-05-01-preview)+httpx
で直接呼ぶ。ペイロードは src/db_routing_iq_maf/kb_setup.py の純関数が組み立て
(オフラインテスト済)、本スクリプトは HTTP を貼るだけの薄い実行層。

実行(要 labs/maf-ports/.env — FOUNDRY_* + AZURE_SEARCH_*):

    uv run python scripts/setup_kb.py
    uv run python scripts/setup_kb.py --recreate   # KB→KS→インデックスを削除して作り直す

冪等: 既定は create_or_update(PUT)+同一キーの mergeOrUpload。--recreate は
参照依存の逆順(KB → KS → インデックス)で削除してから作り直す。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

PORT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PORT_ROOT / "data"
sys.path.insert(0, str(PORT_ROOT / "src"))

from db_routing_iq_maf.config import SEARCH_API_VERSION, DbRoutingIqSettings
from db_routing_iq_maf.kb_setup import (
    DOMAINS,
    build_documents,
    build_index_payload,
    build_knowledge_base_payload,
    build_knowledge_source_payload,
)


class SetupClient:
    """AI Search データプレーン REST の薄いラッパ(api-key 認証)。"""

    def __init__(self, endpoint: str, api_key: str) -> None:
        self._http = httpx.Client(
            base_url=endpoint.removesuffix("/"),
            headers={"api-key": api_key, "Content-Type": "application/json"},
            params={"api-version": SEARCH_API_VERSION},
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    def close(self) -> None:
        self._http.close()

    def put(self, path: str, payload: dict) -> None:
        response = self._http.put(path, json=payload)
        if response.status_code not in (200, 201, 204):
            _fail(f"PUT {path}", response)

    def post(self, path: str, payload: dict) -> httpx.Response:
        response = self._http.post(path, json=payload)
        if response.status_code not in (200, 201, 207):
            _fail(f"POST {path}", response)
        return response

    def delete(self, path: str) -> bool:
        """削除する。存在しなければ False(元アプリ同様、無ければ無視)。"""
        response = self._http.delete(path)
        if response.status_code == 404:
            return False
        if response.status_code not in (200, 204):
            _fail(f"DELETE {path}", response)
        return True


def _fail(operation: str, response: httpx.Response) -> None:
    print(f"error: {operation} -> HTTP {response.status_code}", file=sys.stderr)
    print(response.text, file=sys.stderr)  # preview API のエラー詳細をそのまま出す
    sys.exit(1)


def load_domain_files(domain: str) -> dict[str, str]:
    files = {
        path.stem: path.read_text(encoding="utf-8")
        for path in sorted((DATA_DIR / domain).glob("*.md"))
    }
    if not files:
        print(f"error: no .md files in {DATA_DIR / domain}", file=sys.stderr)
        sys.exit(1)
    return files


def recreate_cleanup(client: SetupClient, kb_name: str) -> None:
    """参照依存の逆順で削除(KB が KS を参照、KS がインデックスを参照)。"""
    if client.delete(f"/knowledgebases/{kb_name}"):
        print(f"deleted knowledge base: {kb_name}")
    for config in DOMAINS:
        if client.delete(f"/knowledgesources/{config.knowledge_source_name}"):
            print(f"deleted knowledge source: {config.knowledge_source_name}")
    for config in DOMAINS:
        if client.delete(f"/indexes/{config.index_name}"):
            print(f"deleted index: {config.index_name}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="db-routing-iq の knowledge base 作成+サンプル文書投入"
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="KB → knowledge source → インデックスの順に削除してから作り直す",
    )
    args = parser.parse_args()

    settings = DbRoutingIqSettings.from_env()
    client = SetupClient(settings.search_endpoint, settings.search_api_key)
    try:
        if args.recreate:
            recreate_cleanup(client, settings.kb_name)

        # --- 1. インデックス+2. 文書投入(ドメインごと)---
        for config in DOMAINS:
            client.put(f"/indexes/{config.index_name}", build_index_payload(config))
            documents = build_documents(config, load_domain_files(config.domain))
            response = client.post(
                f"/indexes/{config.index_name}/docs/index",
                {"value": [{"@search.action": "mergeOrUpload", **doc} for doc in documents]},
            )
            results = response.json().get("value", [])
            failed = [r for r in results if not r.get("status")]
            if failed:
                print(f"error: {len(failed)} documents failed in {config.index_name}", file=sys.stderr)
                sys.exit(1)
            print(f"index ready: {config.index_name} ({len(documents)} chunks)")

        # --- 3. knowledge source ×3 ---
        for config in DOMAINS:
            client.put(
                f"/knowledgesources/{config.knowledge_source_name}",
                build_knowledge_source_payload(config),
            )
            print(f"knowledge source ready: {config.knowledge_source_name}")

        # --- 4. knowledge base ---
        client.put(
            f"/knowledgebases/{settings.kb_name}",
            build_knowledge_base_payload(
                settings.kb_name,
                aoai_resource_uri=settings.foundry_openai_resource_uri,
                aoai_api_key=settings.api_key,
                model_deployment=settings.model,
            ),
        )
        print(f"knowledge base ready: {settings.kb_name}")
        print(f"MCP endpoint: {settings.kb_mcp_url}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
