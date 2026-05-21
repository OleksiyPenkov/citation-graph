import json
import sqlite3
from pathlib import Path

import httpx
from click.testing import CliRunner

from citation_graph import cli, db


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
        conn.execute("INSERT INTO items VALUES(?, ?, 1)", (i, key))
        conn.execute("INSERT INTO itemDataValues VALUES(?, ?)", (i, doi))
        conn.execute("INSERT INTO itemData VALUES(?, 58, ?)", (i, i))
    conn.commit(); conn.close()


def test_missing_command_outputs_json(tmp_path, monkeypatch):
    gpath = tmp_path / "g.sqlite"
    conn = db.open_db(gpath)
    # 2 library nodes both citing one ghost.
    db.upsert_node(conn, openalex_id="L1", doi=None, zotero_key="L1", title="L1",
                   year=None, venue=None, cited_by_count=0, raw_json="{}")
    db.upsert_node(conn, openalex_id="L2", doi=None, zotero_key="L2", title="L2",
                   year=None, venue=None, cited_by_count=0, raw_json="{}")
    db.upsert_node(conn, openalex_id="G1", doi=None, zotero_key=None, title="Ghost",
                   year=2020, venue=None, cited_by_count=99, raw_json="{}")
    db.upsert_edge(conn, "L1", "G1")
    db.upsert_edge(conn, "L2", "G1")
    conn.commit(); conn.close()

    runner = CliRunner()
    result = runner.invoke(cli.main, [
        "--db", str(gpath), "missing", "--k", "2", "--json",
    ])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload[0]["openalex_id"] == "G1"
    assert payload[0]["library_citers"] == 2


def test_sync_command_runs(tmp_path, monkeypatch):
    zpath = tmp_path / "z.sqlite"
    _make_fake_zotero(zpath, {"AAAA": "10.1/a"})
    gpath = tmp_path / "g.sqlite"

    def handler(req):
        if req.url.path.startswith("/works/doi:"):
            return httpx.Response(200, json={
                "id": "https://openalex.org/W1",
                "doi": "https://doi.org/10.1/a",
                "display_name": "Hello",
                "publication_year": 2020,
                "host_venue": {"display_name": "JAP"},
                "cited_by_count": 5,
                "referenced_works": [],
            })
        return httpx.Response(404)
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(cli, "_build_transport", lambda: transport)

    runner = CliRunner()
    result = runner.invoke(cli.main, [
        "--db", str(gpath), "sync",
        "--zotero", str(zpath),
        "--mailto", "t@x.com",
    ])
    assert result.exit_code == 0, result.output
    assert "items_processed=1" in result.output
