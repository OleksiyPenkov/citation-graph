import json
import sqlite3
from pathlib import Path

import httpx

from citation_graph import db, puller
from citation_graph.openalex import OpenAlexClient


def _make_fake_zotero(path: Path, dois: dict[str, str]) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT, libraryID INTEGER);
        CREATE TABLE itemData (itemID INTEGER, fieldID INTEGER, valueID INTEGER);
        CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT);
        CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value TEXT);
        CREATE TABLE deletedItems (itemID INTEGER PRIMARY KEY);
        INSERT INTO fields(fieldID, fieldName) VALUES(58, 'DOI');
    """)
    for i, (key, doi) in enumerate(dois.items(), start=1):
        conn.execute("INSERT INTO items(itemID, key, libraryID) VALUES(?, ?, 1)", (i, key))
        conn.execute("INSERT INTO itemDataValues(valueID, value) VALUES(?, ?)", (i, doi))
        conn.execute("INSERT INTO itemData(itemID, fieldID, valueID) VALUES(?, 58, ?)", (i, i))
    conn.commit()
    conn.close()


def _fake_openalex(work_by_doi: dict[str, dict], works_by_id: dict[str, dict]):
    def handler(req):
        path = req.url.path
        if path.startswith("/works/doi:"):
            doi = path[len("/works/doi:"):]
            if doi in work_by_doi:
                return httpx.Response(200, json=work_by_doi[doi])
            return httpx.Response(404, json={"error": "not found"})
        if path == "/works":
            filt = req.url.params.get("filter", "")
            assert filt.startswith("openalex_id:")
            ids = filt[len("openalex_id:"):].split("|")
            results = [works_by_id[i] for i in ids if i in works_by_id]
            return httpx.Response(200, json={"results": results,
                                              "meta": {"count": len(results)}})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def _work_payload(oa_id, doi=None, refs=None, title=None, year=None, venue=None, cbc=0):
    return {
        "id": f"https://openalex.org/{oa_id}",
        "doi": f"https://doi.org/{doi}" if doi else None,
        "display_name": title or oa_id,
        "publication_year": year,
        "host_venue": {"display_name": venue},
        "cited_by_count": cbc,
        "referenced_works": [f"https://openalex.org/{r}" for r in (refs or [])],
    }


def test_sync_creates_library_node_and_ghost_nodes(tmp_path):
    zpath = tmp_path / "z.sqlite"
    _make_fake_zotero(zpath, {"AAAA1111": "10.1/a"})

    work_by_doi = {"10.1/a": _work_payload("W1", doi="10.1/a", refs=["W2", "W3"])}
    works_by_id = {
        "W2": _work_payload("W2", title="Ref two", year=2010, venue="V2", cbc=5),
        "W3": _work_payload("W3", title="Ref three", year=2011, venue="V3", cbc=7),
    }
    transport = _fake_openalex(work_by_doi, works_by_id)

    gpath = tmp_path / "g.sqlite"
    conn = db.open_db(gpath)
    client = OpenAlexClient(mailto="t@x.com", transport=transport, backoff_base=0.0)

    stats = puller.sync(conn, client, zpath, refresh_age_days=30)

    rows = dict(conn.execute("SELECT openalex_id, zotero_key FROM nodes").fetchall())
    assert rows["W1"] == "AAAA1111"
    assert rows["W2"] is None
    assert rows["W3"] is None

    edges = set(conn.execute("SELECT citing_id, cited_id FROM edges").fetchall())
    assert edges == {("W1", "W2"), ("W1", "W3")}

    assert stats.items_processed == 1
    assert stats.nodes_upserted >= 3
    assert stats.edges_upserted == 2


def test_sync_skips_recent(tmp_path):
    zpath = tmp_path / "z.sqlite"
    _make_fake_zotero(zpath, {"AAAA1111": "10.1/a"})

    work_by_doi = {"10.1/a": _work_payload("W1", doi="10.1/a", refs=[])}
    transport = _fake_openalex(work_by_doi, {})

    gpath = tmp_path / "g.sqlite"
    conn = db.open_db(gpath)
    client = OpenAlexClient(mailto="t@x.com", transport=transport, backoff_base=0.0)

    puller.sync(conn, client, zpath, refresh_age_days=30)
    second = puller.sync(conn, client, zpath, refresh_age_days=30)
    assert second.items_skipped_fresh == 1


def test_sync_records_missing_doi_as_sentinel(tmp_path):
    zpath = tmp_path / "z.sqlite"
    _make_fake_zotero(zpath, {"AAAA1111": "10.0/missing"})

    transport = _fake_openalex({}, {})
    gpath = tmp_path / "g.sqlite"
    conn = db.open_db(gpath)
    client = OpenAlexClient(mailto="t@x.com", transport=transport, backoff_base=0.0)

    stats = puller.sync(conn, client, zpath)
    assert stats.items_not_found == 1
    row = conn.execute(
        "SELECT title FROM nodes WHERE openalex_id LIKE 'NOTFOUND:%'"
    ).fetchone()
    assert row is not None
    assert row[0] == "[OpenAlex: not found]"
