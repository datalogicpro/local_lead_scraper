"""Tests for the cleaning functions."""

import pytest

from cleaning import clean_name, clean_phone, clean_website, parse_place


def test_clean_name_trims_extra_spaces() -> None:
    assert clean_name("  Harbor  Drain Experts ") == "Harbor Drain Experts"


def test_clean_name_blank_becomes_none() -> None:
    assert clean_name("   ") is None
    assert clean_name(None) is None


@pytest.mark.parametrize(
    "raw",
    ["(954) 555-0101", "954.555.0101", "954 555 0101", "+1 954-555-0101", "9545550101"],
)
def test_clean_phone_handles_common_formats(raw: str) -> None:
    assert clean_phone(raw) == "(954) 555-0101"


def test_clean_phone_bad_or_missing_becomes_none() -> None:
    assert clean_phone(None) is None
    assert clean_phone("") is None
    assert clean_phone("555-0101") is None


def test_clean_website_removes_tracking_and_trailing_slash() -> None:
    raw = "HTTP://HarborDrainExperts.example.com/?utm_source=google"
    assert clean_website(raw) == "http://harbordrainexperts.example.com"


def test_clean_website_keeps_the_page_path() -> None:
    raw = "https://a1leakdetection.example.com/contact/"
    assert clean_website(raw) == "https://a1leakdetection.example.com/contact"


def test_clean_website_missing_or_invalid_becomes_none() -> None:
    assert clean_website(None) is None
    assert clean_website("not a website") is None


def test_parse_place_builds_a_clean_record() -> None:
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


def test_parse_place_without_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="no id"):
        parse_place({"displayName": {"text": "No Id Plumbing"}})


def test_parse_place_without_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="P1 has no name"):
        parse_place({"id": "P1"})


def test_parse_place_treats_values_that_are_not_text_as_missing() -> None:
    place = {
        "id": "P1",
        "displayName": {"text": "Good Plumbing"},
        "formattedAddress": 101,
        "nationalPhoneNumber": ["954", "555", "0101"],
        "websiteUri": None,
    }
    assert parse_place(place) == {
        "place_id": "P1",
        "name": "Good Plumbing",
        "address": None,
        "phone": None,
        "website": None,
    }


@pytest.mark.parametrize(
    "place",
    [
        {"id": 1, "displayName": {"text": "Number Id Plumbing"}},
        {"id": "P1", "displayName": "Not A Dict Plumbing"},
        {"id": "P1", "displayName": {"text": 42}},
    ],
)
def test_parse_place_rejects_ids_and_names_that_are_not_text(
    place: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        parse_place(place)
