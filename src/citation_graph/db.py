"""SQLite schema and helpers for the citation graph."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "1"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    openalex_id     TEXT PRIMARY KEY,
    doi             TEXT,
    zotero_key      TEXT UNIQUE,
    title           TEXT,
    year            INTEGER,
    venue           TEXT,
    cited_by_count  INTEGER,
    fetched_at      TEXT NOT NULL,
    raw_json        TEXT
);
CREATE INDEX IF NOT EXISTS idx_nodes_doi ON nodes(doi);
CREATE INDEX IF NOT EXISTS idx_nodes_zotero ON nodes(zotero_key);

CREATE TABLE IF NOT EXISTS edges (
    citing_id  TEXT NOT NULL,
    cited_id   TEXT NOT NULL,
    PRIMARY KEY (citing_id, cited_id),
    FOREIGN KEY (citing_id) REFERENCES nodes(openalex_id),
    FOREIGN KEY (cited_id)  REFERENCES nodes(openalex_id)
);
CREATE INDEX IF NOT EXISTS idx_edges_cited ON edges(cited_id);

CREATE TABLE IF NOT EXISTS meta (
    key    TEXT PRIMARY KEY,
    value  TEXT
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def open_db(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
        (SCHEMA_VERSION,),
    )
    conn.commit()
    return conn


def upsert_node(
    conn: sqlite3.Connection,
    *,
    openalex_id: str,
    doi: Optional[str],
    title: Optional[str],
    year: Optional[int],
    venue: Optional[str],
    cited_by_count: Optional[int],
    zotero_key: Optional[str],
    raw_json: Optional[str],
    fetched_at: Optional[str] = None,
) -> None:
    fetched_at = fetched_at or now_iso()
    conn.execute(
        """
        INSERT INTO nodes(openalex_id, doi, zotero_key, title, year, venue,
                          cited_by_count, fetched_at, raw_json)
        VALUES(:oa, :doi, :zk, :title, :year, :venue, :cbc, :fa, :raw)
        ON CONFLICT(openalex_id) DO UPDATE SET
            doi            = COALESCE(excluded.doi, nodes.doi),
            zotero_key     = COALESCE(excluded.zotero_key, nodes.zotero_key),
            title          = COALESCE(excluded.title, nodes.title),
            year           = COALESCE(excluded.year, nodes.year),
            venue          = COALESCE(excluded.venue, nodes.venue),
            cited_by_count = COALESCE(excluded.cited_by_count, nodes.cited_by_count),
            fetched_at     = excluded.fetched_at,
            raw_json       = COALESCE(excluded.raw_json, nodes.raw_json)
        """,
        dict(oa=openalex_id, doi=doi, zk=zotero_key, title=title, year=year,
             venue=venue, cbc=cited_by_count, fa=fetched_at, raw=raw_json),
    )


def upsert_edge(conn: sqlite3.Connection, citing_id: str, cited_id: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO edges(citing_id, cited_id) VALUES(?, ?)",
        (citing_id, cited_id),
    )


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def get_meta(conn: sqlite3.Connection, key: str) -> Optional[str]:
    cur = conn.execute("SELECT value FROM meta WHERE key=?", (key,))
    row = cur.fetchone()
    return row[0] if row else None
