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
