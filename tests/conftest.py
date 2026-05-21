import sqlite3

import pytest

from citation_graph import db


@pytest.fixture
def graph(tmp_path):
    """In-process graph DB; yields (conn, helper)."""
    conn = db.open_db(tmp_path / "g.sqlite")

    def add_node(oa_id, *, zotero_key=None, title=None, year=None,
                 venue=None, cbc=0, doi=None):
        db.upsert_node(conn, openalex_id=oa_id, doi=doi, zotero_key=zotero_key,
                       title=title or oa_id, year=year, venue=venue,
                       cited_by_count=cbc, raw_json="{}")

    def add_edge(a, b):
        db.upsert_edge(conn, a, b)

    yield conn, add_node, add_edge
    conn.close()
