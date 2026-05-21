import json

from citation_graph import db, mcp_server


def test_missing_tool_returns_results(tmp_path):
    gpath = tmp_path / "g.sqlite"
    conn = db.open_db(gpath)
    db.upsert_node(conn, openalex_id="L1", doi=None, zotero_key="L1", title="L1",
                   year=None, venue=None, cited_by_count=0, raw_json="{}")
    db.upsert_node(conn, openalex_id="L2", doi=None, zotero_key="L2", title="L2",
                   year=None, venue=None, cited_by_count=0, raw_json="{}")
    db.upsert_node(conn, openalex_id="G1", doi=None, zotero_key=None, title="G",
                   year=2020, venue="J", cited_by_count=42, raw_json="{}")
    db.upsert_edge(conn, "L1", "G1")
    db.upsert_edge(conn, "L2", "G1")
    conn.commit(); conn.close()

    result = mcp_server._tool_missing(db_path=str(gpath), k=2, limit=10)
    assert result[0]["openalex_id"] == "G1"
    assert result[0]["library_citers"] == 2


def test_bridges_tool(tmp_path):
    gpath = tmp_path / "g.sqlite"
    conn = db.open_db(gpath)
    db.upsert_node(conn, openalex_id="L1", doi=None, zotero_key="L1", title="L1",
                   year=None, venue=None, cited_by_count=0, raw_json="{}")
    db.upsert_node(conn, openalex_id="L2", doi=None, zotero_key="L2", title="L2",
                   year=None, venue=None, cited_by_count=0, raw_json="{}")
    db.upsert_edge(conn, "L1", "L2")
    conn.commit(); conn.close()

    path = mcp_server._tool_bridges(db_path=str(gpath), key_a="L1", key_b="L2")
    assert path == ["L1", "L2"]


def test_clusters_tool(tmp_path):
    gpath = tmp_path / "g.sqlite"
    conn = db.open_db(gpath)
    for k in ("A", "B"):
        db.upsert_node(conn, openalex_id=k, doi=None, zotero_key=k, title=k,
                       year=None, venue=None, cited_by_count=0, raw_json="{}")
    db.upsert_edge(conn, "A", "B")
    conn.commit(); conn.close()

    comps = mcp_server._tool_clusters(db_path=str(gpath))
    assert comps == [["A", "B"]]
