"""社内文書の検索(セキュリティトリミング付き)。

文書ごとの閲覧権限は AI Search の公式パターン「セキュリティフィルター」で絞る:
インデックスに ``allowed_roles``(Collection(Edm.String)・filterable・retrievable=false)を持たせ、
毎回のクエリに ``allowed_roles/any(r: search.in(r, '<ロール>', ','))`` を付ける。
https://learn.microsoft.com/en-us/azure/search/search-security-trimming-for-azure-search

フィルターに入れる値は **検証済みトークンの roles と暗黙の Employee だけ**。ツール引数・
モデル出力・リクエストヘッダーからは一切作らない(モデルが「経理として検索」と言っても変わらない)。
app-only(利用者なし)の呼び出し元には何も見せない。

実装は 2 つで意味は同じ:

- ``AzureSearchDocs``: azure-search-documents の BM25 全文検索(埋め込みなし=コストゼロ)
- ``InMemoryDocs``: ``data/docs/*.md`` をメモリに載せた疑似検索(オフラインテスト・ローカル実行)。
  絞り込みを先に、順位付けと top 件の切り出しを後に行う点も AI Search と同じ
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..contracts import BASELINE_DOC_ROLE
from ..jwt_validation import Principal

#: 検索結果 1 件あたりの本文の上限(モデルへの入力を抑える)
MAX_CONTENT_CHARS = 800
MAX_TOP = 10


@dataclass(frozen=True)
class DocRecord:
    """インデックスに入れる 1 文書(``allowed_roles`` は検索結果には出さない)。"""

    id: str
    title: str
    content: str
    source: str
    allowed_roles: tuple[str, ...]


@dataclass(frozen=True)
class DocHit:
    id: str
    title: str
    source: str
    content: str
    score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "content": self.content[:MAX_CONTENT_CHARS],
        }


class DocsSearch(Protocol):
    """``search_documents`` ツールが使う最小面。"""

    async def search(self, query: str, *, principal: Principal, top: int = 3) -> list[DocHit]: ...


# --- セキュリティフィルター -------------------------------------------------------------


def effective_doc_roles(principal: Principal) -> frozenset[str]:
    """文書の閲覧に使うロール = 検証済みトークンの roles + 暗黙の Employee。

    - app-only(``is_user=False``)は社員ではないので空集合(何も見えない)
    - ``,`` を含むロールは捨てる: search.in の区切り文字なので、``"X,Docs.Finance"`` のような
      値が 2 つのロールに化けて権限昇格になるのを防ぐ(Entra のアプリロール値は , を許す)
    """
    if not principal.is_user:
        return frozenset()
    roles = {r for r in principal.roles if r and "," not in r}
    roles.add(BASELINE_DOC_ROLE)
    return frozenset(roles)


def build_security_filter(principal: Principal) -> str | None:
    """AI Search の OData フィルター。見せる文書がない呼び出し元は ``None``(検索しない)。"""
    roles = sorted(effective_doc_roles(principal))
    if not roles:
        return None
    joined = ",".join(roles).replace("'", "''")  # OData の文字列リテラルは ' を '' でエスケープ
    return f"allowed_roles/any(r: search.in(r, '{joined}', ','))"


def _clamp_top(top: int) -> int:
    return max(1, min(int(top), MAX_TOP))


# --- 文書データ(data/docs/*.md)---------------------------------------------------------

_FRONT_MATTER = re.compile(r"\A---\s*\n(?P<meta>.*?)\n---\s*\n(?P<body>.*)\Z", re.DOTALL)


def parse_markdown_doc(text: str, *, source: str) -> DocRecord:
    """先頭のフロントマター(``key: value`` 行)付き Markdown を 1 文書にする。

    ``allowed_roles`` は ``[Employee, Docs.Finance]`` またはカンマ区切り。必須(付け忘れた文書を
    全員に見せる事故を防ぐため、ない場合は例外)。
    """
    m = _FRONT_MATTER.match(text)
    if not m:
        raise ValueError(f"{source}: front matter (--- ... ---) is required")
    meta: dict[str, str] = {}
    for line in m.group("meta").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise ValueError(f"{source}: invalid front matter line {line!r}")
        meta[key.strip()] = value.strip()
    raw_roles = meta.get("allowed_roles", "").strip().strip("[]")
    roles = tuple(r.strip().strip("'\"") for r in raw_roles.split(",") if r.strip())
    if not roles:
        raise ValueError(f"{source}: allowed_roles is required")
    body = m.group("body").strip()
    title = meta.get("title") or body.splitlines()[0].lstrip("# ").strip()
    return DocRecord(
        id=meta.get("id") or Path(source).stem,
        title=title,
        content=body,
        source=source,
        allowed_roles=roles,
    )


def load_markdown_docs(directory: Path) -> list[DocRecord]:
    files = sorted(directory.glob("*.md"))
    if not files:
        raise FileNotFoundError(f"no .md files in {directory}")
    docs = [parse_markdown_doc(p.read_text(encoding="utf-8"), source=p.name) for p in files]
    ids = [d.id for d in docs]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate document ids in {directory}")
    return docs


# --- インメモリ実装 ---------------------------------------------------------------------

_NON_WORD = re.compile(r"[\s\W_]+", re.UNICODE)


def _bigrams(text: str) -> set[str]:
    """日本語は分かち書きがないので文字 2-gram で近似する(英数字は小文字化)。"""
    s = _NON_WORD.sub("", text.lower())
    if len(s) < 2:
        return {s} if s else set()
    return {s[i : i + 2] for i in range(len(s) - 1)}


class InMemoryDocs:
    """``AzureSearchDocs`` と同じ意味の疑似検索(絞り込み → 順位付け → top)。"""

    def __init__(self, docs: Iterable[DocRecord]) -> None:
        self._docs = list(docs)
        self._grams = {d.id: (_bigrams(d.title), _bigrams(d.content)) for d in self._docs}
        self.queries: list[tuple[str, frozenset[str]]] = []  # テスト用: (クエリ, 使ったロール)

    @classmethod
    def from_dir(cls, directory: Path) -> InMemoryDocs:
        return cls(load_markdown_docs(directory))

    @property
    def documents(self) -> list[DocRecord]:
        return list(self._docs)

    async def search(self, query: str, *, principal: Principal, top: int = 3) -> list[DocHit]:
        roles = effective_doc_roles(principal)
        self.queries.append((query, roles))
        if not roles:
            return []
        visible = [d for d in self._docs if roles.intersection(d.allowed_roles)]
        q = _bigrams(query)
        scored: list[tuple[float, DocRecord]] = []
        for d in visible:
            title_g, content_g = self._grams[d.id]
            score = 2.0 * len(q & title_g) + len(q & content_g)
            if score > 0:
                scored.append((score, d))
        scored.sort(key=lambda x: (-x[0], x[1].id))
        return [
            DocHit(id=d.id, title=d.title, source=d.source, content=d.content, score=s)
            for s, d in scored[: _clamp_top(top)]
        ]


# --- Azure AI Search 実装 ---------------------------------------------------------------


class AzureSearchDocs:
    """azure-search-documents(async)の BM25 全文検索 + セキュリティフィルター。

    ``client`` は ``azure.search.documents.aio.SearchClient`` 互換(``search(...)`` が
    非同期イテレーターを返す)。テストでは同じ形の fake を渡す。
    """

    SELECT = ("id", "title", "content", "source")

    def __init__(self, client: Any, *, credential: Any | None = None) -> None:
        self._client = client
        self._credential = credential

    @classmethod
    def create(cls, *, endpoint: str, index: str, api_key: str | None) -> AzureSearchDocs:
        """キーがあればキー認証、なければマネージド ID(Search Index Data Reader が必要)。"""
        from azure.search.documents.aio import SearchClient

        credential: Any
        if api_key:
            from azure.core.credentials import AzureKeyCredential

            credential = AzureKeyCredential(api_key)
            owned = None
        else:
            from azure.identity.aio import DefaultAzureCredential

            credential = owned = DefaultAzureCredential()
        client = SearchClient(endpoint=endpoint, index_name=index, credential=credential)
        return cls(client, credential=owned)

    async def search(self, query: str, *, principal: Principal, top: int = 3) -> list[DocHit]:
        security_filter = build_security_filter(principal)
        if security_filter is None:
            return []
        results = await self._client.search(
            search_text=query,
            filter=security_filter,
            select=list(self.SELECT),
            top=_clamp_top(top),
        )
        hits: list[DocHit] = []
        async for row in results:
            hits.append(
                DocHit(
                    id=str(row.get("id", "")),
                    title=str(row.get("title", "")),
                    source=str(row.get("source", "")),
                    content=str(row.get("content", "")),
                    score=row.get("@search.score"),
                )
            )
        return hits

    async def aclose(self) -> None:
        await self._client.close()
        if self._credential is not None:
            await self._credential.close()
