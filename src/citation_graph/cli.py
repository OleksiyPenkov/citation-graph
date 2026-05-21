"""CLI entrypoint for citation-graph."""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import click
import httpx
from rich.console import Console
from rich.table import Table

from . import db, puller, queries
from .openalex import OpenAlexClient

DEFAULT_DB = Path(os.environ.get("CITATION_GRAPH_DB",
                                  r"D:\Database\Zotero\citation_graph.sqlite"))
DEFAULT_ZOTERO = Path(os.environ.get("ZOTERO_SQLITE",
                                      r"D:\Database\Zotero\zotero.sqlite"))


def _build_transport() -> Optional[httpx.BaseTransport]:
    return None  # production: real HTTP. Tests monkeypatch this.


@click.group()
@click.option("--db", "db_path", type=click.Path(path_type=Path), default=DEFAULT_DB,
              show_default=True, help="Path to the citation graph SQLite DB.")
@click.pass_context
def main(ctx: click.Context, db_path: Path) -> None:
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = db_path


@main.command()
@click.option("--zotero", "zotero_path", type=click.Path(path_type=Path),
              default=DEFAULT_ZOTERO, show_default=True)
@click.option("--mailto", default=os.environ.get("OPENALEX_MAILTO", "citation-graph-user@example.com"),
              show_default=True)
@click.option("--refresh-age-days", default=30, show_default=True, type=int)
@click.option("--full", is_flag=True, help="Ignore freshness, refetch all items.")
@click.pass_context
def sync(ctx, zotero_path: Path, mailto: str, refresh_age_days: int, full: bool):
    """Sync Zotero items into the graph via OpenAlex."""
    conn = db.open_db(ctx.obj["db_path"])
    client = OpenAlexClient(mailto=mailto, transport=_build_transport())
    try:
        stats = puller.sync(
            conn, client, zotero_path,
            refresh_age_days=refresh_age_days, force_full=full,
            on_progress=lambda msg: click.echo(msg, err=True),
        )
    finally:
        client.close()
        conn.close()
    parts = [f"{k}={v}" for k, v in asdict(stats).items()]
    click.echo(" ".join(parts))


@main.command("pull-citations")
@click.argument("zotero_key")
@click.option("--mailto", default=os.environ.get("OPENALEX_MAILTO", "citation-graph-user@example.com"))
@click.pass_context
def pull_citations(ctx, zotero_key: str, mailto: str):
    """Pull reverse citations (papers citing this Zotero item)."""
    conn = db.open_db(ctx.obj["db_path"])
    client = OpenAlexClient(mailto=mailto, transport=_build_transport())
    try:
        try:
            stats = puller.pull_citations_of(
                conn, client, zotero_key,
                on_progress=lambda msg: click.echo(msg, err=True),
            )
        except LookupError as e:
            raise click.UsageError(str(e)) from None
    finally:
        client.close()
        conn.close()
    parts = [f"{k}={v}" for k, v in asdict(stats).items()]
    click.echo(" ".join(parts))


@main.command()
@click.option("--k", "min_citers", default=3, type=int, show_default=True)
@click.option("--limit", default=20, type=int, show_default=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def missing(ctx, min_citers: int, limit: int, as_json: bool):
    """Ghost papers cited by k+ items already in your library."""
    conn = db.open_db(ctx.obj["db_path"])
    try:
        hits = queries.missing_high_value(conn, min_citers=min_citers, limit=limit)
    finally:
        conn.close()
    if as_json:
        click.echo(json.dumps([asdict(h) for h in hits], indent=2))
        return
    table = Table(title=f"Missing high-value (>= {min_citers} library citers)")
    for col in ("openalex_id", "year", "venue", "cbc", "k", "title"):
        table.add_column(col)
    for h in hits:
        table.add_row(h.openalex_id, str(h.year or ""), h.venue or "",
                      str(h.cited_by_count or ""), str(h.library_citers),
                      h.title or "")
    Console().print(table)


@main.command()
@click.argument("key_a")
@click.argument("key_b")
@click.option("--max-depth", default=4, show_default=True, type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def bridges(ctx, key_a: str, key_b: str, max_depth: int, as_json: bool):
    """Shortest citation path between two Zotero items."""
    conn = db.open_db(ctx.obj["db_path"])
    try:
        try:
            path = queries.bridges(conn, key_a, key_b, max_depth=max_depth)
        except LookupError as e:
            raise click.UsageError(str(e)) from None
    finally:
        conn.close()
    if as_json:
        click.echo(json.dumps(path))
        return
    click.echo(" -> ".join(path) if path else "(no path)")


@main.command()
@click.argument("zotero_key")
@click.option("--depth", default=1, show_default=True, type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def neighborhood(ctx, zotero_key: str, depth: int, as_json: bool):
    """Papers within N hops of a Zotero item."""
    conn = db.open_db(ctx.obj["db_path"])
    try:
        try:
            nb = queries.neighborhood(conn, zotero_key, depth=depth)
        except LookupError as e:
            raise click.UsageError(str(e)) from None
    finally:
        conn.close()
    if as_json:
        click.echo(json.dumps([asdict(n) for n in nb], indent=2))
        return
    table = Table(title=f"Neighborhood of {zotero_key} (depth {depth})")
    for col in ("openalex_id", "dist", "in_lib", "title"):
        table.add_column(col)
    for n in nb:
        table.add_row(n.openalex_id, str(n.distance),
                      "yes" if n.in_library else "", n.title or "")
    Console().print(table)


@main.command()
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def clusters(ctx, as_json: bool):
    """Connected components in the library-only subgraph."""
    conn = db.open_db(ctx.obj["db_path"])
    try:
        comps = queries.clusters(conn)
    finally:
        conn.close()
    if as_json:
        click.echo(json.dumps(comps, indent=2))
        return
    for i, c in enumerate(comps, 1):
        click.echo(f"[{i}] {len(c)} item(s): {', '.join(c)}")
