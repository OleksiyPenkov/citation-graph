"""Query primitives over the citation graph."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class GhostHit:
    openalex_id: str
    title: str | None
    year: int | None
    venue: str | None
    cited_by_count: int | None
    library_citers: int


def missing_high_value(
    conn: sqlite3.Connection,
    *,
    min_citers: int = 3,
    limit: int = 50,
) -> list[GhostHit]:
    """Ghost nodes (not in library) cited by >= min_citers library items."""
    cur = conn.execute(
        """
        SELECT n.openalex_id, n.title, n.year, n.venue, n.cited_by_count,
               COUNT(DISTINCT lib.zotero_key) AS k
        FROM nodes n
        JOIN edges e          ON e.cited_id = n.openalex_id
        JOIN nodes lib        ON lib.openalex_id = e.citing_id
        WHERE n.zotero_key IS NULL
          AND lib.zotero_key IS NOT NULL
        GROUP BY n.openalex_id
        HAVING k >= ?
        ORDER BY k DESC, n.cited_by_count DESC NULLS LAST
        LIMIT ?
        """,
        (min_citers, limit),
    )
    return [GhostHit(*row) for row in cur.fetchall()]


def _resolve_zotero_key(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute(
        "SELECT openalex_id FROM nodes WHERE zotero_key=?", (key,)
    ).fetchone()
    if not row:
        raise LookupError(f"No graph node for zotero_key={key}")
    return row[0]


def bridges(
    conn: sqlite3.Connection,
    key_a: str,
    key_b: str,
    *,
    max_depth: int = 4,
) -> list[str]:
    """Shortest directed citation path between two Zotero items as a list of openalex_ids.

    Returns [] if no path within max_depth.
    """
    src = _resolve_zotero_key(conn, key_a)
    dst = _resolve_zotero_key(conn, key_b)
    if src == dst:
        return [src]

    # BFS in Python — graph is small enough; SQL recursive CTE is harder to
    # cap by depth portably.
    frontier: list[tuple[str, list[str]]] = [(src, [src])]
    seen = {src}
    while frontier:
        next_frontier: list[tuple[str, list[str]]] = []
        for node, path in frontier:
            if len(path) > max_depth:
                continue
            cur = conn.execute(
                "SELECT cited_id FROM edges WHERE citing_id=?", (node,)
            )
            for (nb,) in cur:
                if nb == dst:
                    return path + [nb]
                if nb in seen:
                    continue
                seen.add(nb)
                if len(path) < max_depth:
                    next_frontier.append((nb, path + [nb]))
        frontier = next_frontier
    return []
