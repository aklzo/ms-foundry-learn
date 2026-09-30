"""社内文書の AI Search インデックスを作り、data/docs/*.md を投入する(ライブ専用・既定はドライラン)。

    uv run python scripts/setup_index.py                 # ドライラン: 送る要求を表示するだけ(Azure に触れない)
    uv run --extra search python scripts/setup_index.py --apply            # 実行
    uv run --extra search python scripts/setup_index.py --apply --recreate # 作り直し

インデックスは AI Search の公式パターン「セキュリティフィルター」の形:
https://learn.microsoft.com/en-us/azure/search/search-security-trimming-for-azure-search

- ``allowed_roles``: Collection(Edm.String)・filterable・**retrievable=false**(検索結果に出さない)。
  値は文書のフロントマターの ``allowed_roles``(``Employee`` / ``Docs.Finance``)
- ``title`` / ``content``: 日本語アナライザー ``ja.microsoft`` の全文検索(BM25)。埋め込みは使わない
  (モデルデプロイ不要・コストゼロ。権限絞り込みの検証にはベクトルは要らない)

冪等: インデックスは PUT(作成または更新)、文書は ``mergeOrUpload``(同じ id は上書き)。
REST を直接呼ぶのは、ドライランで表示する内容と実際に送る内容を完全に一致させるため。

環境変数: ``SEARCH_ENDPOINT``(必須)/ ``SEARCH_INDEX``(既定 internal-docs)/
``SEARCH_API_KEY``(任意。なければ ``az login`` 等の DefaultAzureCredential で Entra 認証。
その場合は実行者に Search Service Contributor + Search Index Data Contributor が必要)。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from delegated_access_maf.tools_server.docs_search import load_markdown_docs
from delegated_access_maf.tools_server.settings import DEFAULT_DOCS_DIR, DEFAULT_SEARCH_INDEX

#: AI Search の REST API バージョン(公式のセキュリティトリミング手順と同じ)
API_VERSION = "2026-04-01"
ANALYZER = "ja.microsoft"
SEARCH_SCOPE = "https://search.azure.com/.default"


def build_index_definition(index_name: str) -> dict[str, Any]:
    return {
        "name": index_name,
        "fields": [
            {"name": "id", "type": "Edm.String", "key": True, "filterable": True},
            {
                "name": "title",
                "type": "Edm.String",
                "searchable": True,
                "analyzer": ANALYZER,
            },
            {
                "name": "content",
                "type": "Edm.String",
                "searchable": True,
                "analyzer": ANALYZER,
            },
            {"name": "source", "type": "Edm.String", "filterable": True, "searchable": False},
            {
                "name": "allowed_roles",
                "type": "Collection(Edm.String)",
                "filterable": True,
                "retrievable": False,
                "searchable": False,
                "facetable": False,
            },
        ],
    }


def build_documents(docs_dir: Path = DEFAULT_DOCS_DIR) -> list[dict[str, Any]]:
    return [
        {
            "@search.action": "mergeOrUpload",
            "id": d.id,
            "title": d.title,
            "content": d.content,
            "source": d.source,
            "allowed_roles": list(d.allowed_roles),
        }
        for d in load_markdown_docs(docs_dir)
    ]


def build_requests(
    endpoint: str, index_name: str, *, recreate: bool, docs_dir: Path = DEFAULT_DOCS_DIR
) -> list[tuple[str, str, dict[str, Any] | None]]:
    base = endpoint.rstrip("/")
    requests: list[tuple[str, str, dict[str, Any] | None]] = []
    if recreate:
        requests.append(("DELETE", f"{base}/indexes/{index_name}?api-version={API_VERSION}", None))
    requests.append(
        (
            "PUT",
            f"{base}/indexes/{index_name}?api-version={API_VERSION}",
            build_index_definition(index_name),
        )
    )
    requests.append(
        (
            "POST",
            f"{base}/indexes/{index_name}/docs/index?api-version={API_VERSION}",
            {"value": build_documents(docs_dir)},
        )
    )
    return requests


def _auth_headers(api_key: str | None) -> dict[str, str]:
    if api_key:
        return {"api-key": api_key}
    from azure.identity import DefaultAzureCredential

    token = DefaultAzureCredential().get_token(SEARCH_SCOPE).token
    return {"Authorization": f"Bearer {token}"}


def _print_request(method: str, url: str, body: dict[str, Any] | None) -> None:
    print(f"{method} {url}")
    if body is None:
        return
    shown = json.loads(json.dumps(body))
    for doc in shown.get("value", []):
        if len(doc.get("content", "")) > 60:
            doc["content"] = doc["content"][:60] + "…"
    print(json.dumps(shown, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="社内文書インデックスの作成と投入(既定はドライラン)"
    )
    parser.add_argument("--apply", action="store_true", help="実際に AI Search へ送る")
    parser.add_argument(
        "--recreate", action="store_true", help="既存インデックスを削除してから作る"
    )
    args = parser.parse_args(argv)

    endpoint = os.environ.get("SEARCH_ENDPOINT") or (
        "https://<search-service>.search.windows.net" if not args.apply else ""
    )
    if not endpoint:
        print("error: SEARCH_ENDPOINT が未設定です", file=sys.stderr)
        return 2
    index_name = os.environ.get("SEARCH_INDEX") or DEFAULT_SEARCH_INDEX
    requests = build_requests(endpoint, index_name, recreate=args.recreate)

    if not args.apply:
        print("# ドライラン(--apply で実行)。送る要求:")
        for method, url, body in requests:
            _print_request(method, url, body)
        return 0

    import httpx

    headers = _auth_headers(os.environ.get("SEARCH_API_KEY") or None)
    with httpx.Client(timeout=60, headers=headers, follow_redirects=False) as client:
        for method, url, body in requests:
            response = client.request(method, url, json=body)
            if method == "DELETE" and response.status_code == 404:
                print(f"{method} {url} -> 404(既存インデックスなし)")
                continue
            print(f"{method} {url} -> {response.status_code}")
            if response.status_code >= 400:
                print(response.text, file=sys.stderr)
                return 1
            if method == "POST":
                results = response.json().get("value", [])
                ok = sum(1 for r in results if r.get("status"))
                print(f"uploaded {ok}/{len(results)} documents")
                if ok != len(results):
                    return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
