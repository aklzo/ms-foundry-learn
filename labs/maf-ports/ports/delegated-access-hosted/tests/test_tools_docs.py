"""文書検索のセキュリティトリミング(フィルターの組み立て・インメモリ実装・AI Search 実装・同梱データ)。"""

from __future__ import annotations

import pytest

from delegated_access_maf.contracts import BASELINE_DOC_ROLE, ROLE_DOCS_FINANCE
from delegated_access_maf.tools_server.docs_search import (
    AzureSearchDocs,
    InMemoryDocs,
    build_security_filter,
    effective_doc_roles,
    load_markdown_docs,
    parse_markdown_doc,
)
from delegated_access_maf.tools_server.settings import DEFAULT_DOCS_DIR

from .tools_support import principal

# --- 同梱データ -------------------------------------------------------------------------------


def test_bundled_docs_mix_both_labels_and_hide_credit_limits_from_employees():
    docs = load_markdown_docs(DEFAULT_DOCS_DIR)
    assert 8 <= len(docs) <= 10
    labels = {r for d in docs for r in d.allowed_roles}
    assert labels == {BASELINE_DOC_ROLE, ROLE_DOCS_FINANCE}
    # 与信限度額は経理向け文書にだけ書かれている(絞り込みが目に見える題材)
    for d in docs:
        if "与信限度額" in d.content:
            assert d.allowed_roles == (ROLE_DOCS_FINANCE,), d.id
    assert any("与信限度額" in d.content for d in docs)


def test_front_matter_is_required_and_parsed():
    doc = parse_markdown_doc(
        "---\nid: x\ntitle: T\nallowed_roles: [Employee, Docs.Finance]\n---\n# 見出し\n本文\n",
        source="x.md",
    )
    assert (doc.id, doc.title, doc.allowed_roles) == ("x", "T", ("Employee", "Docs.Finance"))
    assert doc.content.startswith("# 見出し")
    with pytest.raises(ValueError, match="front matter"):
        parse_markdown_doc("# no front matter", source="y.md")
    with pytest.raises(ValueError, match="allowed_roles"):
        parse_markdown_doc("---\nid: z\n---\nbody", source="z.md")  # 付け忘れを全員公開にしない


# --- フィルターの組み立て ---------------------------------------------------------------------


def test_effective_roles_come_only_from_the_principal():
    assert effective_doc_roles(principal()) == {"Employee"}
    assert effective_doc_roles(principal(roles=("Docs.Finance", "Suppliers.Write"))) == {
        "Employee",
        "Docs.Finance",
        "Suppliers.Write",
    }
    # app-only は社員ではない: ロールを持っていても何も見せない
    assert effective_doc_roles(principal(roles=("Docs.Finance",), is_user=False)) == frozenset()


def test_filter_uses_search_in_with_comma_delimiter():
    f = build_security_filter(principal(roles=("Docs.Finance",)))
    assert f == "allowed_roles/any(r: search.in(r, 'Docs.Finance,Employee', ','))"
    assert build_security_filter(principal(is_user=False)) is None


def test_filter_neutralises_delimiters_and_quotes():
    # , を含むロールは 2 つのロールに化けるので捨てる。' は OData のエスケープ('')
    f = build_security_filter(principal(roles=("X,Docs.Finance", "O'Brien")))
    assert f == "allowed_roles/any(r: search.in(r, 'Employee,O''Brien', ','))"
    assert "Docs.Finance" not in f


# --- インメモリ実装 ---------------------------------------------------------------------------


@pytest.fixture
def docs() -> InMemoryDocs:
    return InMemoryDocs.from_dir(DEFAULT_DOCS_DIR)


async def test_trimming_happens_before_ranking_and_top(docs):
    employee = principal()
    finance = principal(roles=("Docs.Finance",))
    top_finance = await docs.search("与信限度額の設定基準", principal=finance, top=1)
    assert [h.id for h in top_finance] == ["fin-credit-limit"]
    many = await docs.search("与信限度額の設定基準", principal=employee, top=10)
    assert all(not h.id.startswith("fin-") for h in many)


async def test_app_only_sees_nothing(docs):
    assert await docs.search("経費", principal=principal(is_user=False)) == []


async def test_top_is_clamped(docs):
    hits = await docs.search("規程", principal=principal(roles=("Docs.Finance",)), top=100)
    assert 1 <= len(hits) <= 10
    assert len(await docs.search("規程", principal=principal(), top=0)) == 1


# --- AI Search 実装(SDK と同じ形の fake クライアント)-------------------------------------------


class _Results:
    def __init__(self, rows):
        self._rows = list(rows)

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for row in self._rows:
            yield row


class FakeSearchClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls: list[dict] = []
        self.closed = False

    async def search(self, **kwargs):
        self.calls.append(kwargs)
        return _Results(self.rows)

    async def close(self):
        self.closed = True


async def test_azure_search_sends_bm25_query_with_security_filter():
    client = FakeSearchClient(
        [
            {
                "id": "fin-credit-limit",
                "title": "与信",
                "content": "本文",
                "source": "a.md",
                "@search.score": 3.2,
            }
        ]
    )
    search = AzureSearchDocs(client)
    hits = await search.search("与信限度額", principal=principal(roles=("Docs.Finance",)), top=4)
    (call,) = client.calls
    assert call == {
        "search_text": "与信限度額",
        "filter": "allowed_roles/any(r: search.in(r, 'Docs.Finance,Employee', ','))",
        "select": ["id", "title", "content", "source"],  # allowed_roles は取得しない
        "top": 4,
    }
    assert [(h.id, h.score) for h in hits] == [("fin-credit-limit", 3.2)]
    await search.aclose()
    assert client.closed


async def test_azure_search_is_not_called_without_visible_roles():
    client = FakeSearchClient([])
    assert await AzureSearchDocs(client).search("x", principal=principal(is_user=False)) == []
    assert client.calls == []
