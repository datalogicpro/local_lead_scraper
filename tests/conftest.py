"""Shared test setup."""

import sqlite3
from collections.abc import Iterator

import pytest

from database import connect, create_table


@pytest.fixture
def db() -> Iterator[sqlite3.Connection]:
    """A fresh, empty database that lives only in memory while the test runs."""
    conn = connect(":memory:")
    create_table(conn)
    yield conn
    conn.close()
