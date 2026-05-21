import sqlite3
from pathlib import Path

import pytest

from citation_graph import zotero


def _make_fake_zotero(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT, libraryID INTEGER);
        CREATE TABLE itemData (itemID INTEGER, fieldID INTEGER, valueID INTEGER);
        CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT);
        CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value TEXT);
        CREATE TABLE deletedItems (itemID INTEGER PRIMARY KEY);
    """)
    # Items: 3 normal, 1 deleted, 1 without DOI
    conn.executemany(
        "INSERT INTO items(itemID, key, libraryID) VALUES(?, ?, 1)",
        [(1, "AAAA1111"), (2, "BBBB2222"), (3, "CCCC3333"), (4, "DDDD4444"), (5, "EEEE5555")],
    )
    conn.execute("INSERT INTO fields(fieldID, fieldName) VALUES(58, 'DOI')")
    conn.execute("INSERT INTO fields(fieldID, fieldName) VALUES(99, 'title')")
    conn.executemany(
        "INSERT INTO itemDataValues(valueID, value) VALUES(?, ?)",
        [(10, "10.1234/foo"), (11, "10.5678/BAR"), (12, "10.9/del"), (13, "Some title")],
    )
    conn.executemany(
        "INSERT INTO itemData(itemID, fieldID, valueID) VALUES(?, ?, ?)",
        [(1, 58, 10), (2, 58, 11), (3, 58, 12), (5, 99, 13)],
    )
    conn.execute("INSERT INTO deletedItems(itemID) VALUES(3)")
    conn.commit()
    conn.close()


def test_iter_dois_returns_non_deleted(tmp_path):
    z = tmp_path / "zotero.sqlite"
    _make_fake_zotero(z)
    rows = list(zotero.iter_items_with_dois(z))
    keys = {k for k, _ in rows}
    assert keys == {"AAAA1111", "BBBB2222"}


def test_iter_dois_normalises_lowercase(tmp_path):
    z = tmp_path / "zotero.sqlite"
    _make_fake_zotero(z)
    rows = dict(zotero.iter_items_with_dois(z))
    assert rows["BBBB2222"] == "10.5678/bar"


def test_iter_dois_strips_url_prefix(tmp_path):
    z = tmp_path / "zotero.sqlite"
    _make_fake_zotero(z)
    # Patch one DOI to include the https://doi.org/ prefix
    conn = sqlite3.connect(str(z))
    conn.execute("UPDATE itemDataValues SET value='https://doi.org/10.1234/FOO' WHERE valueID=10")
    conn.commit()
    conn.close()
    rows = dict(zotero.iter_items_with_dois(z))
    assert rows["AAAA1111"] == "10.1234/foo"


def test_missing_zotero_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        list(zotero.iter_items_with_dois(tmp_path / "no.sqlite"))
