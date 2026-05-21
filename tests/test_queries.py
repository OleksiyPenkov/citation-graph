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


def test_bridges_finds_direct_edge(graph):
    conn, add_node, add_edge = graph
    add_node("L1", zotero_key="L1")
    add_node("L2", zotero_key="L2")
    add_edge("L1", "L2")
    path = queries.bridges(conn, "L1", "L2")
    assert path == ["L1", "L2"]


def test_bridges_finds_two_hop(graph):
    conn, add_node, add_edge = graph
    add_node("L1", zotero_key="L1")
    add_node("L2", zotero_key="L2")
    add_node("M")
    add_edge("L1", "M")
    add_edge("M", "L2")
    assert queries.bridges(conn, "L1", "L2") == ["L1", "M", "L2"]


def test_bridges_no_path_returns_empty(graph):
    conn, add_node, add_edge = graph
    add_node("L1", zotero_key="L1")
    add_node("L2", zotero_key="L2")
    assert queries.bridges(conn, "L1", "L2") == []


def test_bridges_respects_max_depth(graph):
    conn, add_node, add_edge = graph
    add_node("L1", zotero_key="L1")
    add_node("L2", zotero_key="L2")
    chain = ["L1", "A", "B", "C", "D", "L2"]
    for n in chain[1:-1]:
        add_node(n)
    for a, b in zip(chain, chain[1:]):
        add_edge(a, b)
    # 5 hops > default depth 4
    assert queries.bridges(conn, "L1", "L2", max_depth=4) == []
    assert queries.bridges(conn, "L1", "L2", max_depth=5) == chain


def test_bridges_unknown_key_raises(graph):
    conn, *_ = graph
    import pytest
    with pytest.raises(LookupError):
        queries.bridges(conn, "NOPE", "ALSO_NOPE")


def test_neighborhood_depth_one(graph):
    conn, add_node, add_edge = graph
    add_node("L1", zotero_key="L1")
    add_node("A"); add_node("B")
    add_node("C", zotero_key="C")
    add_edge("L1", "A")        # outgoing
    add_edge("B", "L1")        # incoming
    add_edge("L1", "C")        # outgoing to library
    nb = queries.neighborhood(conn, "L1", depth=1)
    ids = {n.openalex_id for n in nb}
    assert ids == {"A", "B", "C"}
    in_lib = {n.openalex_id for n in nb if n.in_library}
    assert in_lib == {"C"}


def test_neighborhood_depth_two(graph):
    conn, add_node, add_edge = graph
    add_node("L1", zotero_key="L1")
    add_node("A"); add_node("B")
    add_edge("L1", "A")
    add_edge("A", "B")
    nb1 = queries.neighborhood(conn, "L1", depth=1)
    assert {n.openalex_id for n in nb1} == {"A"}
    nb2 = queries.neighborhood(conn, "L1", depth=2)
    assert {n.openalex_id for n in nb2} == {"A", "B"}
