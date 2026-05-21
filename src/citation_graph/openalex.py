"""Minimal OpenAlex client: fetch_work_by_doi + fetch_works_batch."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Iterable, Iterator, Optional

import httpx

_BASE = "https://api.openalex.org"


@dataclass(frozen=True)
class Work:
    openalex_id: str
    doi: Optional[str]
    title: Optional[str]
    year: Optional[int]
    venue: Optional[str]
    cited_by_count: Optional[int]
    referenced_works: list[str]
    raw_json: str


def _short_id(value: str) -> str:
    """Strip the https://openalex.org/ prefix from a work id."""
    if value.startswith("https://openalex.org/"):
        return value[len("https://openalex.org/"):]
    return value


def _normalise_doi(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix):]
            break
    return doi.lower()


def _parse(payload: dict) -> Work:
    # OpenAlex deprecated `host_venue` in favour of `primary_location.source` (2024).
    # Prefer the new field; fall back for any older cached payloads.
    primary = payload.get("primary_location") or {}
    source = primary.get("source") or {}
    venue = source.get("display_name") or (payload.get("host_venue") or {}).get("display_name")
    refs = [_short_id(r) for r in payload.get("referenced_works") or []]
    return Work(
        openalex_id=_short_id(payload["id"]),
        doi=_normalise_doi(payload.get("doi")),
        title=payload.get("display_name"),
        year=payload.get("publication_year"),
        venue=venue,
        cited_by_count=payload.get("cited_by_count"),
        referenced_works=refs,
        raw_json=json.dumps(payload),
    )


class OpenAlexClient:
    def __init__(
        self,
        *,
        mailto: str,
        transport: Optional[httpx.BaseTransport] = None,
        batch_size: int = 50,
        max_retries: int = 4,
        backoff_base: float = 1.0,
    ):
        self._params = {"mailto": mailto}
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._client = httpx.Client(
            base_url=_BASE,
            transport=transport,
            timeout=20.0,
            headers={"User-Agent": f"citation-graph (mailto:{mailto})"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _get(self, path: str, params: Optional[dict] = None) -> Optional[httpx.Response]:
        merged = dict(self._params)
        if params:
            merged.update(params)
        delay = self._backoff_base
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._client.get(path, params=merged)
            except httpx.RequestError:
                if attempt == self._max_retries:
                    return None
                time.sleep(delay)
                delay *= 2
                continue
            if resp.status_code == 404:
                return resp
            if resp.status_code >= 500 and attempt < self._max_retries:
                time.sleep(delay)
                delay *= 2
                continue
            return resp
        return None

    def fetch_work_by_doi(self, doi: str) -> Optional[Work]:
        resp = self._get(f"/works/doi:{doi}")
        if resp is None or resp.status_code == 404:
            return None
        resp.raise_for_status()
        return _parse(resp.json())

    def fetch_works_batch(self, openalex_ids: Iterable[str]) -> Iterator[Work]:
        seen: set[str] = set()
        buf: list[str] = []
        for oid in openalex_ids:
            if oid in seen:
                continue
            seen.add(oid)
            buf.append(oid)
            if len(buf) >= self._batch_size:
                yield from self._batch(buf)
                buf = []
        if buf:
            yield from self._batch(buf)

    def _batch(self, ids: list[str]) -> Iterator[Work]:
        filt = f"openalex_id:{'|'.join(ids)}"
        resp = self._get("/works", params={"filter": filt, "per-page": str(len(ids))})
        if resp is None or resp.status_code != 200:
            return
        for w in resp.json().get("results", []):
            yield _parse(w)

    def iter_cited_by(self, openalex_id: str, per_page: int = 200) -> Iterator[Work]:
        cursor = "*"
        while cursor:
            resp = self._get(
                "/works",
                params={
                    "filter": f"cites:{openalex_id}",
                    "per-page": str(per_page),
                    "cursor": cursor,
                },
            )
            if resp is None or resp.status_code != 200:
                return
            data = resp.json()
            for w in data.get("results", []):
                yield _parse(w)
            cursor = (data.get("meta") or {}).get("next_cursor")
