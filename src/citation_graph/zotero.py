"""Read-only enumeration of DOIs in a local Zotero SQLite library."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator, Tuple

_QUERY = """
SELECT i.key, idv.value
FROM items i
JOIN itemData id      ON id.itemID  = i.itemID
JOIN fields f         ON id.fieldID = f.fieldID
JOIN itemDataValues idv ON id.valueID = idv.valueID
WHERE f.fieldName = 'DOI'
  AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
"""


def _normalise_doi(raw: str) -> str:
    doi = raw.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix):]
            break
    return doi.lower()


def iter_items_with_dois(zotero_sqlite: Path | str) -> Iterator[Tuple[str, str]]:
    """Yield (zotero_key, normalised_doi) for every non-deleted item with a DOI."""
    path = Path(zotero_sqlite)
    if not path.exists():
        raise FileNotFoundError(path)
    # Read-only, immutable so Zotero can stay open.
    uri = f"file:{path.as_posix()}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    try:
        for key, raw_doi in conn.execute(_QUERY):
            if not raw_doi:
                continue
            yield key, _normalise_doi(raw_doi)
    finally:
        conn.close()
