"""Database functions for the lead scraper (SQLite)."""

import sqlite3

DB_FILE = "leads.db"


def connect(db_file=DB_FILE):
    """Open the database file, creating it if it does not exist."""
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    return conn


def create_table(conn):
    """Create the leads table if it is not there yet."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
            place_id     TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            address      TEXT,
            phone        TEXT,
            website      TEXT,
            first_seen   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def upsert_lead(conn, lead):
    """Insert a lead, or update it if its place_id is already in the table.

    A blank value in the new data never erases a value we already have.
    Returns "inserted" or "updated".
    """
    already_there = conn.execute(
        "SELECT 1 FROM leads WHERE place_id = ?", (lead["place_id"],)
    ).fetchone()

    conn.execute(
        """
        INSERT INTO leads (place_id, name, address, phone, website)
        VALUES (:place_id, :name, :address, :phone, :website)
        ON CONFLICT (place_id) DO UPDATE SET
            name         = excluded.name,
            address      = COALESCE(excluded.address, leads.address),
            phone        = COALESCE(excluded.phone, leads.phone),
            website      = COALESCE(excluded.website, leads.website),
            last_updated = CURRENT_TIMESTAMP
        """,
        lead,
    )
    conn.commit()
    return "updated" if already_there else "inserted"