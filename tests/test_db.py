import sqlite3
from pathlib import Path

import pytest

from citation_graph import db


def test_init_creates_schema(tmp_path):
    db_path = tmp_path / "graph.sqlite"
    conn = db.open_db(db_path)
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    assert "nodes" in tables
    assert "edges" in tables
    assert "meta" in tables


def test_init_sets_schema_version(tmp_path):
    db_path = tmp_path / "graph.sqlite"
    conn = db.open_db(db_path)
    cur = conn.execute("SELECT value FROM meta WHERE key='schema_version'")
    assert cur.fetchone()[0] == "1"


def test_reopen_does_not_recreate(tmp_path):
    db_path = tmp_path / "graph.sqlite"
    conn1 = db.open_db(db_path)
    conn1.execute(
        "INSERT INTO nodes(openalex_id, fetched_at) VALUES ('W1', '2026-05-21')"
    )
    conn1.commit()
    conn1.close()

    conn2 = db.open_db(db_path)
    cur = conn2.execute("SELECT openalex_id FROM nodes")
    assert cur.fetchone()[0] == "W1"


def test_upsert_node_inserts(tmp_path):
    conn = db.open_db(tmp_path / "g.sqlite")
    db.upsert_node(conn, openalex_id="W1", doi="10.1/x", title="T", year=2020,
                   venue="V", cited_by_count=5, zotero_key=None, raw_json="{}")
    cur = conn.execute("SELECT title, cited_by_count FROM nodes WHERE openalex_id='W1'")
    assert cur.fetchone() == ("T", 5)


def test_upsert_node_updates_on_conflict(tmp_path):
    conn = db.open_db(tmp_path / "g.sqlite")
    db.upsert_node(conn, openalex_id="W1", doi=None, title="Old", year=None,
                   venue=None, cited_by_count=0, zotero_key=None, raw_json="{}")
    db.upsert_node(conn, openalex_id="W1", doi="10.1/x", title="New", year=2021,
                   venue="V", cited_by_count=10, zotero_key="ABCD1234", raw_json="{}")
    cur = conn.execute("SELECT title, cited_by_count, zotero_key FROM nodes WHERE openalex_id='W1'")
    assert cur.fetchone() == ("New", 10, "ABCD1234")


def test_upsert_edge_is_idempotent(tmp_path):
    conn = db.open_db(tmp_path / "g.sqlite")
    db.upsert_node(conn, openalex_id="W1", doi=None, title=None, year=None,
                   venue=None, cited_by_count=0, zotero_key=None, raw_json="{}")
    db.upsert_node(conn, openalex_id="W2", doi=None, title=None, year=None,
                   venue=None, cited_by_count=0, zotero_key=None, raw_json="{}")
    db.upsert_edge(conn, "W1", "W2")
    db.upsert_edge(conn, "W1", "W2")
    cur = conn.execute("SELECT COUNT(*) FROM edges")
    assert cur.fetchone()[0] == 1
