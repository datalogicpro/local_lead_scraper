"""Tests for the web page. Nothing here talks to Google."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import streamlit
from streamlit.testing.v1 import AppTest

from app import (
    UPLOAD_CHOICE,
    ReplyError,
    leads_csv,
    raw_records,
    read_reply,
    run_scraper,
    run_table,
)
from scraper import SAMPLE_FILE

APP_FILE = str(Path(__file__).parent.parent / "app.py")

# The first run imports Streamlit, which can take a while
TIMEOUT = 30


@dataclass
class FakeUpload:
    """Stands in for Streamlit's uploaded file, which AppTest can't create."""

    name: str
    data: bytes

    def getvalue(self) -> bytes:
        return self.data


def sample_reply() -> dict[str, Any]:
    return read_reply(SAMPLE_FILE.read_bytes())


def run_with_upload(upload: FakeUpload | None) -> AppTest:
    with patch.object(streamlit, "file_uploader", return_value=upload):
        app = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT).run()
        app.radio[0].set_value(UPLOAD_CHOICE).run()
    return app


def metric_values(app: AppTest) -> list[str]:
    return [metric.value for metric in app.metric]


def test_read_reply_reads_the_sample() -> None:
    reply = read_reply(SAMPLE_FILE.read_bytes())

    assert isinstance(reply["places"], list)
    assert len(reply["places"]) == 7


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"not json", "valid JSON"),
        (b"[1, 2]", '"places" list'),
        (b"{}", '"places" list'),
        (b'{"places": "none"}', '"places" list'),
        (b'{"places": ["not a place"]}', '"places" list'),
    ],
)
def test_read_reply_explains_bad_files(data: bytes, message: str) -> None:
    with pytest.raises(ReplyError, match=message):
        read_reply(data)


def test_raw_records_keep_the_messy_values() -> None:
    records = raw_records(sample_reply())

    assert len(records) == 7
    assert records[1]["name"] == "  Harbor  Drain Experts "
    assert records[1]["phone"] == "954.555.0102"
    assert records[2]["website"] is None


def test_raw_records_handle_a_name_that_is_not_text() -> None:
    records = raw_records({"places": [{"id": "P1", "displayName": "Plumbing"}]})

    assert records[0]["name"] is None


def test_run_scraper_once() -> None:
    result = run_scraper(sample_reply(), runs=1)

    assert result.runs == [{"inserted": 6, "updated": 1, "skipped": 0, "total": 6}]
    assert len(result.leads) == 6
    # Leads are sorted by name
    assert result.leads[0]["name"] == "A1 Leak Detection"


def test_run_scraper_twice_adds_no_duplicates() -> None:
    result = run_scraper(sample_reply(), runs=2)

    assert result.runs[1] == {"inserted": 0, "updated": 7, "skipped": 0, "total": 6}
    assert len(result.leads) == 6


def test_leads_csv() -> None:
    result = run_scraper(sample_reply(), runs=1)

    lines = leads_csv(result.leads).splitlines()

    assert lines[0] == "place_id,name,address,phone,website"
    assert len(lines) == 7
    assert "(954) 555-0105" in lines[1]


def test_run_table() -> None:
    result = run_scraper(sample_reply(), runs=2)

    table = run_table(result.runs)

    assert table[1] == {
        "Run": 2,
        "Inserted": 0,
        "Updated": 7,
        "Skipped": 0,
        "Leads in database": 6,
    }


def test_page_shows_the_sample() -> None:
    app = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT).run()

    assert not app.exception
    assert metric_values(app) == ["6", "1", "0", "6"]
    runs, before, after = app.dataframe
    assert len(runs.value) == 1
    assert len(before.value) == 7
    assert len(after.value) == 6


def test_run_it_again_updates_instead_of_duplicating() -> None:
    app = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT).run()

    app.button[0].click().run()

    assert not app.exception
    assert metric_values(app) == ["0", "7", "0", "6"]
    assert len(app.dataframe[0].value) == 2


def test_new_data_starts_over_at_one_run() -> None:
    upload = FakeUpload("leads.json", SAMPLE_FILE.read_bytes())
    with patch.object(streamlit, "file_uploader", return_value=upload):
        app = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT).run()
        app.button[0].click().run()
        app.radio[0].set_value(UPLOAD_CHOICE).run()

    assert not app.exception
    assert metric_values(app) == ["6", "1", "0", "6"]


def test_page_waits_for_upload() -> None:
    app = run_with_upload(None)

    assert not app.exception
    assert app.info[0].value.startswith("Upload a .json file")
    assert not app.metric


def test_page_cleans_an_uploaded_file() -> None:
    app = run_with_upload(FakeUpload("leads.json", SAMPLE_FILE.read_bytes()))

    assert not app.exception
    assert metric_values(app) == ["6", "1", "0", "6"]


def test_page_explains_a_bad_file() -> None:
    app = run_with_upload(FakeUpload("leads.json", b"not json"))

    assert not app.exception
    assert "valid JSON" in app.error[0].value
    assert not app.metric
