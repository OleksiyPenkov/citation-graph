"""Sync Zotero items into the citation graph via OpenAlex."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db, zotero
from .openalex import OpenAlexClient, Work


@dataclass
class SyncStats:
    items_processed: int = 0
    items_skipped_fresh: int = 0
    items_not_found: int = 0
    nodes_upserted: int = 0
    edges_upserted: int = 0
    enrichment_batches: int = 0


def _is_fresh(fetched_at: str | None, max_age: timedelta) -> bool:
    if not fetched_at:
        return False
    try:
        ts = datetime.fromisoformat(fetched_at)
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts) < max_age


def _write_work(conn: sqlite3.Connection, work: Work, *, zotero_key: str | None) -> None:
    db.upsert_node(
        conn,
        openalex_id=work.openalex_id,
        doi=work.doi,
        zotero_key=zotero_key,
        title=work.title,
        year=work.year,
        venue=work.venue,
        cited_by_count=work.cited_by_count,
        raw_json=work.raw_json,
    )


def _clear_notfound_sentinel(conn: sqlite3.Connection, zotero_key: str) -> None:
    """Delete any NOTFOUND sentinel row for this zotero_key so the real node can own it."""
    conn.execute(
        "DELETE FROM nodes WHERE zotero_key = ? AND openalex_id LIKE 'NOTFOUND:%'",
        (zotero_key,),
    )


def _write_not_found(conn: sqlite3.Connection, doi: str, zotero_key: str) -> None:
    sentinel = f"NOTFOUND:{doi}"
    _clear_notfound_sentinel(conn, zotero_key)
    db.upsert_node(
        conn,
        openalex_id=sentinel,
        doi=doi,
        zotero_key=zotero_key,
        title="[OpenAlex: not found]",
        year=None,
        venue=None,
        cited_by_count=None,
        raw_json=None,
    )


def sync(
    conn: sqlite3.Connection,
    client: OpenAlexClient,
    zotero_sqlite: Path | str,
    *,
    refresh_age_days: int = 30,
    force_full: bool = False,
) -> SyncStats:
    """Walk Zotero DOIs, fetch from OpenAlex, write nodes + edges."""
    stats = SyncStats()
    max_age = timedelta(days=refresh_age_days)

    ghost_ids: set[str] = set()

    for zotero_key, doi in zotero.iter_items_with_dois(zotero_sqlite):
        stats.items_processed += 1

        # Has this item been fetched recently?
        if not force_full:
            row = conn.execute(
                "SELECT openalex_id, fetched_at FROM nodes WHERE zotero_key=?",
                (zotero_key,),
            ).fetchone()
            if row and _is_fresh(row[1], max_age):
                stats.items_skipped_fresh += 1
                continue

        work = client.fetch_work_by_doi(doi)
        if work is None:
            _write_not_found(conn, doi, zotero_key)
            stats.items_not_found += 1
            continue

        _clear_notfound_sentinel(conn, zotero_key)
        _write_work(conn, work, zotero_key=zotero_key)
        stats.nodes_upserted += 1

        for ref_id in work.referenced_works:
            # Skeleton row (ghost) — enriched in batch below.
            db.upsert_node(
                conn,
                openalex_id=ref_id,
                doi=None,
                zotero_key=None,
                title=None,
                year=None,
                venue=None,
                cited_by_count=None,
                raw_json=None,
            )
            db.upsert_edge(conn, work.openalex_id, ref_id)
            stats.edges_upserted += 1

            # Only enrich nodes we don't already have content for.
            existing = conn.execute(
                "SELECT title FROM nodes WHERE openalex_id=?", (ref_id,)
            ).fetchone()
            if not existing or existing[0] is None:
                ghost_ids.add(ref_id)

        conn.commit()

    # Batch-enrich ghost nodes.
    if ghost_ids:
        for enriched in client.fetch_works_batch(sorted(ghost_ids)):
            _write_work(conn, enriched, zotero_key=None)
            stats.nodes_upserted += 1
            stats.enrichment_batches += 1
        conn.commit()

    db.set_meta(conn, "last_full_sync_at", db.now_iso())
    conn.commit()
    return stats


def pull_citations_of(
    conn: sqlite3.Connection,
    client: OpenAlexClient,
    zotero_key: str,
) -> SyncStats:
    """Walk OpenAlex /works?filter=cites:<id> for the given library item."""
    stats = SyncStats()
    row = conn.execute(
        "SELECT openalex_id FROM nodes WHERE zotero_key=?", (zotero_key,)
    ).fetchone()
    if not row:
        raise LookupError(f"No graph node for zotero_key={zotero_key}; run sync first.")
    target_id = row[0]

    for citer in client.iter_cited_by(target_id):
        _write_work(conn, citer, zotero_key=None)
        stats.nodes_upserted += 1
        db.upsert_edge(conn, citer.openalex_id, target_id)
        stats.edges_upserted += 1
        # Persist incrementally — these passes can be long.
        if stats.edges_upserted % 100 == 0:
            conn.commit()
    conn.commit()
    return stats
