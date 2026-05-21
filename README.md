# citation-graph

Local citation graph over the Zotero library, backed by OpenAlex.
No Docker, no LLM — just SQLite next to `zotero.sqlite`.

## Install

```bash
cd D:\MultilayerLab\citation-graph
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
```

## Usage

### Build / refresh the graph

```bash
citation-graph sync
# default: D:\Database\Zotero\zotero.sqlite -> D:\Database\Zotero\citation_graph.sqlite
```

Re-running is incremental — items fetched within the last 30 days are
skipped unless `--full` is passed.

### Queries

```bash
citation-graph missing --k 3 --limit 20
citation-graph bridges <zotero_key_a> <zotero_key_b>
citation-graph neighborhood <zotero_key> --depth 2
citation-graph clusters
```

Add `--json` for machine output.

### Reverse citations (opt-in, expensive)

```bash
citation-graph pull-citations <zotero_key>
```

Walks every paper citing the given item — minutes for heavily-cited items.

## MCP server

Register at user scope:

```bash
claude mcp add citation-graph --scope user -- ".venv\Scripts\citation-graph-mcp"
```

Tools exposed: `citation_graph_sync`, `citation_graph_missing`,
`citation_graph_bridges`, `citation_graph_neighborhood`,
`citation_graph_clusters`.

## Configuration

Environment variables (all optional):

- `CITATION_GRAPH_DB` — graph DB path
- `ZOTERO_SQLITE` — source Zotero DB path
- `OPENALEX_MAILTO` — polite-pool email (default: `alex.penkov@gmail.com`)

## How it works

1. Read DOIs from the local Zotero SQLite (read-only, immutable).
2. For each DOI, fetch the OpenAlex `Work` via `/works/doi:<DOI>`.
3. Store the library work as a node with `zotero_key`. Store each item in
   `referenced_works` as a ghost node (`zotero_key = NULL`) and an edge.
4. Batch-enrich ghosts via `/works?filter=openalex_id:a|b|c`.

The graph is a directed citation DAG. Library nodes and ghost nodes share
the same table, distinguished by `zotero_key IS NULL`.

## Limits

- Coverage gap on preprint-only and non-OpenAlex venues.
- Single-user, single-library — no Zotero group libraries.
- Bridge query capped at 4 hops by default. Beyond that, paths stop being
  meaningful.
