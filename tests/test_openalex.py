import json

import httpx
import pytest

from citation_graph import openalex


def _work(oa_id: str, doi: str | None = None, refs: list[str] | None = None,
          title: str = "T", year: int = 2020, venue: str = "V", cbc: int = 1) -> dict:
    return {
        "id": f"https://openalex.org/{oa_id}",
        "doi": f"https://doi.org/{doi}" if doi else None,
        "display_name": title,
        "publication_year": year,
        "host_venue": {"display_name": venue},
        "cited_by_count": cbc,
        "referenced_works": [f"https://openalex.org/{r}" for r in (refs or [])],
    }


def _transport(handler):
    return httpx.MockTransport(handler)


def test_fetch_work_by_doi_parses(monkeypatch):
    def handler(req):
        assert req.url.path == "/works/doi:10.1/x"
        assert req.url.params.get("mailto") == "test@example.com"
        return httpx.Response(200, json=_work("W1", doi="10.1/x", refs=["W2", "W3"],
                                              title="Hello", year=2021, venue="JAP", cbc=42))
    client = openalex.OpenAlexClient(mailto="test@example.com",
                                      transport=_transport(handler))
    w = client.fetch_work_by_doi("10.1/x")
    assert w.openalex_id == "W1"
    assert w.doi == "10.1/x"
    assert w.title == "Hello"
    assert w.year == 2021
    assert w.venue == "JAP"
    assert w.cited_by_count == 42
    assert w.referenced_works == ["W2", "W3"]


def test_fetch_work_404_returns_none():
    def handler(req):
        return httpx.Response(404, json={"error": "not found"})
    client = openalex.OpenAlexClient(mailto="t@x.com", transport=_transport(handler))
    assert client.fetch_work_by_doi("10.0/missing") is None


def test_fetch_works_batch_chunks_and_dedupes():
    calls = []

    def handler(req):
        calls.append(req.url.params.get("filter"))
        # Reply with one work per requested id.
        ids = req.url.params["filter"].split(":")[1].split("|")
        results = [_work(i) for i in ids]
        return httpx.Response(200, json={"results": results, "meta": {"count": len(results)}})

    client = openalex.OpenAlexClient(mailto="t@x.com", transport=_transport(handler),
                                      batch_size=3)
    ids = ["W1", "W2", "W3", "W4", "W4", "W5"]
    out = list(client.fetch_works_batch(ids))
    # 5 unique ids, batch size 3 → 2 calls (W1|W2|W3 then W4|W5).
    assert len(calls) == 2
    assert {w.openalex_id for w in out} == {"W1", "W2", "W3", "W4", "W5"}


def test_retry_then_succeed():
    state = {"calls": 0}

    def handler(req):
        state["calls"] += 1
        if state["calls"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=_work("W1"))

    client = openalex.OpenAlexClient(mailto="t@x.com", transport=_transport(handler),
                                      backoff_base=0.0)
    w = client.fetch_work_by_doi("10.1/x")
    assert w.openalex_id == "W1"
    assert state["calls"] == 3


def test_strip_openalex_prefix():
    assert openalex._short_id("https://openalex.org/W123") == "W123"
    assert openalex._short_id("W123") == "W123"
