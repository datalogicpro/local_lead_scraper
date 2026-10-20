"""Tests for the scraper. Nothing here talks to Google or touches your real leads.db."""

import logging
import runpy
import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest

import scraper

SCRIPT = Path(scraper.__file__)


class FakeResponse:
    """Stands in for the reply from requests.post."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        return self.data


@pytest.fixture
def call_log(db: sqlite3.Connection) -> sqlite3.Connection:
    scraper.create_call_log(db)
    return db


@pytest.fixture
def in_tmp_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run in an empty folder, so leads.db is made there and not in the project."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Act as if there is no key, even when a real .env file exists."""
    monkeypatch.setattr(scraper, "load_dotenv", lambda: None)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)


def use_up_todays_calls(conn: sqlite3.Connection) -> None:
    for _ in range(scraper.DAILY_CALL_LIMIT):
        conn.execute(
            "INSERT INTO api_calls (called_on) VALUES (?)", (date.today().isoformat(),)
        )
    conn.commit()


def test_call_limit_allows_calls_under_the_limit(call_log: sqlite3.Connection) -> None:
    scraper.check_call_limit(call_log)  # should not raise


def test_call_limit_stops_the_script_at_the_limit(
    call_log: sqlite3.Connection,
) -> None:
    use_up_todays_calls(call_log)

    with pytest.raises(RuntimeError, match="Daily call limit reached"):
        scraper.check_call_limit(call_log)


def test_load_sample_reads_the_sample_reply() -> None:
    data = scraper.load_sample()

    assert len(data["places"]) == 7


def test_sample_runs_twice_without_duplicates(db: sqlite3.Connection) -> None:
    data = scraper.load_sample()

    # The numbers in the README's "Results on the sample data" table
    assert scraper.save_places(db, data) == {"inserted": 6, "updated": 1, "skipped": 0}
    assert scraper.save_places(db, data) == {"inserted": 0, "updated": 7, "skipped": 0}


def test_bad_places_are_skipped_and_the_rest_are_saved(
    db: sqlite3.Connection, caplog: pytest.LogCaptureFixture
) -> None:
    data = {
        "places": [
            {"displayName": {"text": "No Id Plumbing"}},
            {"id": "P1", "displayName": {"text": "Good Plumbing"}},
        ]
    }

    counts = scraper.save_places(db, data)

    assert counts == {"inserted": 1, "updated": 0, "skipped": 1}
    assert "Skipped a place: place has no id" in caplog.text


def test_fetch_live_needs_an_api_key(
    call_log: sqlite3.Connection, no_api_key: None
) -> None:
    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY is missing"):
        scraper.fetch_live(call_log, "plumbers in Miami, FL")

    assert scraper.calls_today(call_log) == 0


def test_fetch_live_counts_the_call_and_sends_the_search(
    call_log: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> FakeResponse:
        sent.update(kwargs, url=url)
        return FakeResponse({"places": []})

    monkeypatch.setattr(scraper, "load_dotenv", lambda: None)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr(scraper.requests, "post", fake_post)

    data = scraper.fetch_live(call_log, "plumbers in Miami, FL")

    assert data == {"places": []}
    assert scraper.calls_today(call_log) == 1
    assert sent["url"] == scraper.SEARCH_URL
    assert sent["headers"]["X-Goog-Api-Key"] == "test-key"
    assert sent["json"]["textQuery"] == "plumbers in Miami, FL"


def test_fetch_live_makes_no_call_at_the_limit(
    call_log: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_post(url: str, **kwargs: Any) -> FakeResponse:
        raise AssertionError("no call should be made")

    monkeypatch.setattr(scraper, "load_dotenv", lambda: None)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr(scraper.requests, "post", fail_post)
    use_up_todays_calls(call_log)

    with pytest.raises(RuntimeError, match="Daily call limit reached"):
        scraper.fetch_live(call_log, "plumbers in Miami, FL")


def test_main_saves_the_sample(
    in_tmp_folder: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        exit_code = scraper.main([])

    assert exit_code == 0
    assert (in_tmp_folder / "leads.db").exists()
    assert "inserted=6 updated=1 skipped=0 | 6 leads in the database" in caplog.text


def test_main_reports_errors(
    in_tmp_folder: Path, no_api_key: None, caplog: pytest.LogCaptureFixture
) -> None:
    exit_code = scraper.main(["--live", "plumbers in Miami, FL"])

    assert exit_code == 1
    assert "GOOGLE_API_KEY is missing" in caplog.text


def test_runs_as_script(in_tmp_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["scraper.py"])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(SCRIPT), run_name="__main__")

    assert exit_info.value.code == 0
