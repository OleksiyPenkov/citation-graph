"""MCP server exposing citation-graph queries as tools."""
from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import db, puller, queries
from .openalex import OpenAlexClient

DEFAULT_DB = os.environ.get("CITATION_GRAPH_DB",
                             r"D:\Database\Zotero\citation_graph.sqlite")
DEFAULT_ZOTERO = os.environ.get("ZOTERO_SQLITE",
                                 r"D:\Database\Zotero\zotero.sqlite")
DEFAULT_MAILTO = os.environ.get("OPENALEX_MAILTO", "citation-graph-user@example.com")


def _tool_sync(db_path: str | None = None,
               zotero_path: str | None = None,
               refresh_age_days: int = 30,
               full: bool = False) -> dict[str, Any]:
    conn = db.open_db(Path(db_path or DEFAULT_DB))
    client = OpenAlexClient(mailto=DEFAULT_MAILTO)
    try:
        stats = puller.sync(conn, client, zotero_path or DEFAULT_ZOTERO,
                            refresh_age_days=refresh_age_days, force_full=full)
    finally:
        client.close()
        conn.close()
    return asdict(stats)


def _tool_missing(db_path: str | None = None, k: int = 3, limit: int = 20):
    conn = db.open_db(Path(db_path or DEFAULT_DB))
    try:
        return [asdict(h) for h in queries.missing_high_value(
            conn, min_citers=k, limit=limit)]
    finally:
        conn.close()


def _tool_bridges(db_path: str | None = None, *, key_a: str, key_b: str,
                  max_depth: int = 4) -> list[str]:
    conn = db.open_db(Path(db_path or DEFAULT_DB))
    try:
        return queries.bridges(conn, key_a, key_b, max_depth=max_depth)
    finally:
        conn.close()


def _tool_neighborhood(db_path: str | None = None, *, zotero_key: str,
                       depth: int = 1):
    conn = db.open_db(Path(db_path or DEFAULT_DB))
    try:
        return [asdict(n) for n in queries.neighborhood(
            conn, zotero_key, depth=depth)]
    finally:
        conn.close()


def _tool_clusters(db_path: str | None = None) -> list[list[str]]:
    conn = db.open_db(Path(db_path or DEFAULT_DB))
    try:
        return queries.clusters(conn)
    finally:
        conn.close()


server = FastMCP("citation-graph")


@server.tool()
def citation_graph_sync(refresh_age_days: int = 30, full: bool = False) -> dict:
    """Sync new Zotero items into the citation graph."""
    return _tool_sync(refresh_age_days=refresh_age_days, full=full)


@server.tool()
def citation_graph_missing(k: int = 3, limit: int = 20) -> list[dict]:
    """Find non-library papers cited by k+ items in your library."""
    return _tool_missing(k=k, limit=limit)


@server.tool()
def citation_graph_bridges(key_a: str, key_b: str, max_depth: int = 4) -> list[str]:
    """Shortest citation path between two Zotero items (as openalex_ids)."""
    return _tool_bridges(key_a=key_a, key_b=key_b, max_depth=max_depth)


@server.tool()
def citation_graph_neighborhood(zotero_key: str, depth: int = 1) -> list[dict]:
    """Papers within N citation hops of a Zotero item."""
    return _tool_neighborhood(zotero_key=zotero_key, depth=depth)


@server.tool()
def citation_graph_clusters() -> list[list[str]]:
    """Connected components in the library-only citation subgraph."""
    return _tool_clusters()


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
