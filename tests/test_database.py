"""Tests for the database functions."""

import sqlite3
from pathlib import Path

from cleaning import Lead
from database import connect, create_table, upsert_lead


def make_lead(
    phone: str | None = "(954) 555-0100",
    website: str | None = "https://test.example.com",
) -> Lead:
    return {
        "place_id": "TEST_1",
        "name": "Test Plumbing",
        "address": "1 Test St",
        "phone": phone,
        "website": website,
    }


def count_leads(conn: sqlite3.Connection) -> int:
    count: int = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    return count


def test_connect_creates_the_database_file(tmp_path: Path) -> None:
    db_file = tmp_path / "leads.db"

    conn = connect(str(db_file))
    create_table(conn)
    conn.close()

    assert db_file.exists()


def test_upsert_inserts_a_new_lead(db: sqlite3.Connection) -> None:
    assert upsert_lead(db, make_lead()) == "inserted"
    assert count_leads(db) == 1


def test_upsert_same_place_updates_instead_of_duplicating(
    db: sqlite3.Connection,
) -> None:
    upsert_lead(db, make_lead())

    assert upsert_lead(db, make_lead()) == "updated"
    assert count_leads(db) == 1


def test_upsert_saves_a_changed_website(db: sqlite3.Connection) -> None:
    upsert_lead(db, make_lead(website="https://old.example.com"))
    upsert_lead(db, make_lead(website="https://new.example.com"))

    row = db.execute("SELECT website FROM leads").fetchone()
    assert row["website"] == "https://new.example.com"


def test_blank_value_does_not_erase_a_saved_phone(db: sqlite3.Connection) -> None:
    upsert_lead(db, make_lead(phone="(954) 555-0100"))
    upsert_lead(db, make_lead(phone=None))

    row = db.execute("SELECT phone FROM leads").fetchone()
    assert row["phone"] == "(954) 555-0100"
