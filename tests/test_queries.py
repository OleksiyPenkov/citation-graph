from citation_graph import queries


def test_missing_high_value_ranks_by_library_citations(graph):
    conn, add_node, add_edge = graph
    # 3 library items
    for k in ("L1", "L2", "L3"):
        add_node(k, zotero_key=k)
    # 2 ghosts: G1 cited by all 3 library items, G2 by only 1
    add_node("G1", cbc=100)
    add_node("G2", cbc=999)
    for k in ("L1", "L2", "L3"):
        add_edge(k, "G1")
    add_edge("L1", "G2")

    results = queries.missing_high_value(conn, min_citers=2, limit=10)
    assert [r.openalex_id for r in results] == ["G1"]
    assert results[0].library_citers == 3


def test_missing_high_value_respects_min_citers(graph):
    conn, add_node, add_edge = graph
    add_node("L1", zotero_key="L1")
    add_node("L2", zotero_key="L2")
    add_node("G1")
    add_edge("L1", "G1")

    assert queries.missing_high_value(conn, min_citers=2) == []
    assert len(queries.missing_high_value(conn, min_citers=1)) == 1


def test_missing_high_value_excludes_library_items(graph):
    conn, add_node, add_edge = graph
    add_node("L1", zotero_key="L1")
    add_node("L2", zotero_key="L2")
    add_node("L3", zotero_key="L3")
    # L3 is in the library but cited by L1 and L2 — should NOT appear.
    add_edge("L1", "L3")
    add_edge("L2", "L3")

    assert queries.missing_high_value(conn, min_citers=2) == []
