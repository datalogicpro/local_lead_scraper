"""Tests for the lead scraper. Run them with:  pytest

Nothing here talks to Google or touches your real leads.db file.
The database tests use a temporary database that lives only in memory.
"""

from datetime import date

import pytest

import scraper
from cleaning import clean_name, clean_phone, clean_website, parse_place
from database import connect, create_table, upsert_lead


def make_db():
    """A fresh, empty database that exists only while the test runs."""
    conn = connect(":memory:")
    create_table(conn)
    return conn


def make_lead(**changes):
    lead = {
        "place_id": "TEST_1",
        "name": "Test Plumbing",
        "address": "1 Test St",
        "phone": "(954) 555-0100",
        "website": "https://test.example.com",
    }
    lead.update(changes)
    return lead


# ---------- cleaning ----------

def test_clean_name_trims_extra_spaces():
    assert clean_name("  Harbor  Drain Experts ") == "Harbor Drain Experts"


def test_clean_name_blank_becomes_none():
    assert clean_name("   ") is None
    assert clean_name(None) is None


def test_clean_phone_handles_common_formats():
    for raw in ["(954) 555-0101", "954.555.0101", "954 555 0101", "+1 954-555-0101", "9545550101"]:
        assert clean_phone(raw) == "(954) 555-0101"


def test_clean_phone_bad_or_missing_becomes_none():
    assert clean_phone(None) is None
    assert clean_phone("") is None
    assert clean_phone("555-0101") is None


def test_clean_website_removes_tracking_and_trailing_slash():
    raw = "HTTP://HarborDrainExperts.example.com/?utm_source=google"
    assert clean_website(raw) == "http://harbordrainexperts.example.com"


def test_clean_website_keeps_the_page_path():
    raw = "https://a1leakdetection.example.com/contact/"
    assert clean_website(raw) == "https://a1leakdetection.example.com/contact"


def test_clean_website_missing_or_invalid_becomes_none():
    assert clean_website(None) is None
    assert clean_website("not a website") is None


def test_parse_place_builds_a_clean_record():
    place = {
        "id": "P1",
        "displayName": {"text": "  Coastal  Pro Plumbing "},
        "formattedAddress": "101 Example St",
        "nationalPhoneNumber": "954.555.0101",
        "websiteUri": "HTTPS://Coastal.example.com/",
    }
    assert parse_place(place) == {
        "place_id": "P1",
        "name": "Coastal Pro Plumbing",
        "address": "101 Example St",
        "phone": "(954) 555-0101",
        "website": "https://coastal.example.com",
    }


def test_parse_place_without_id_is_rejected():
    with pytest.raises(ValueError):
        parse_place({"displayName": {"text": "No Id Plumbing"}})


def test_parse_place_without_name_is_rejected():
    with pytest.raises(ValueError):
        parse_place({"id": "P1"})


# ---------- database ----------

def test_upsert_inserts_a_new_lead():
    conn = make_db()
    assert upsert_lead(conn, make_lead()) == "inserted"
    assert conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == 1


def test_upsert_same_place_updates_instead_of_duplicating():
    conn = make_db()
    upsert_lead(conn, make_lead())
    assert upsert_lead(conn, make_lead()) == "updated"
    assert conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == 1


def test_upsert_saves_a_changed_website():
    conn = make_db()
    upsert_lead(conn, make_lead(website="https://old.example.com"))
    upsert_lead(conn, make_lead(website="https://new.example.com"))
    row = conn.execute("SELECT website FROM leads WHERE place_id = 'TEST_1'").fetchone()
    assert row["website"] == "https://new.example.com"


def test_blank_value_does_not_erase_a_saved_phone():
    conn = make_db()
    upsert_lead(conn, make_lead(phone="(954) 555-0100"))
    upsert_lead(conn, make_lead(phone=None))
    row = conn.execute("SELECT phone FROM leads WHERE place_id = 'TEST_1'").fetchone()
    assert row["phone"] == "(954) 555-0100"


# ---------- safety limit and error handling ----------

def test_call_limit_allows_calls_under_the_limit():
    conn = make_db()
    scraper.create_call_log(conn)
    scraper.check_call_limit(conn)  # should not raise


def test_call_limit_stops_the_script_at_the_limit():
    conn = make_db()
    scraper.create_call_log(conn)
    for _ in range(scraper.DAILY_CALL_LIMIT):
        conn.execute("INSERT INTO api_calls (called_on) VALUES (?)", (date.today().isoformat(),))
    conn.commit()
    with pytest.raises(RuntimeError):
        scraper.check_call_limit(conn)


def test_bad_places_are_skipped_and_the_rest_are_saved():
    conn = make_db()
    data = {
        "places": [
            {"displayName": {"text": "No Id Plumbing"}},
            {"id": "P1", "displayName": {"text": "Good Plumbing"}},
        ]
    }
    counts = scraper.save_places(conn, data)
    assert counts == {"inserted": 1, "updated": 0, "skipped": 1}