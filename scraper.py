"""Local lead scraper: get places, clean them, and save them to a SQL database.

Usage:
    python scraper.py                                   uses sample_response.json (zero real calls)
    python scraper.py --live "plumbers in Fort Lauderdale, FL"  makes ONE real call to Google Places API
"""

import argparse
import json
import logging
import os
import sys
from datetime import date

import requests
from dotenv import load_dotenv

from cleaning import parse_place
from database import connect, create_table, upsert_lead

SAMPLE_FILE = "sample_response.json"
SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.nationalPhoneNumber,places.websiteUri"
)
PAGE_SIZE = 20

# Hard safety limit: the most real Google calls this script will ever make in one day.
DAILY_CALL_LIMIT = 10

log = logging.getLogger("lead_scraper")


def create_call_log(conn):
    """Create the table that counts real Google calls."""
    conn.execute("CREATE TABLE IF NOT EXISTS api_calls (called_on TEXT NOT NULL)")
    conn.commit()


def calls_today(conn):
    """How many real Google calls have been made today."""
    row = conn.execute(
        "SELECT COUNT(*) FROM api_calls WHERE called_on = ?",
        (date.today().isoformat(),),
    ).fetchone()
    return row[0]


def check_call_limit(conn):
    """Stop the script if today's call limit has been reached."""
    used = calls_today(conn)
    if used >= DAILY_CALL_LIMIT:
        raise RuntimeError(
            f"Daily call limit reached ({used} of {DAILY_CALL_LIMIT}). No call was made."
        )


def load_sample():
    """Read the saved fake reply. This costs nothing."""
    with open(SAMPLE_FILE, encoding="utf-8") as f:
        return json.load(f)


def fetch_live(conn, search_text):
    """Make ONE real call to Google Places (New) and return its reply."""
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is missing. Add it to the .env file.")

    check_call_limit(conn)

    # Count the call BEFORE making it, so a failed call still counts.
    conn.execute(
        "INSERT INTO api_calls (called_on) VALUES (?)", (date.today().isoformat(),)
    )
    conn.commit()
    log.info("Making real Google call %s of %s allowed today", calls_today(conn), DAILY_CALL_LIMIT)

    response = requests.post(
        SEARCH_URL,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        },
        json={"textQuery": search_text, "pageSize": PAGE_SIZE},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def save_places(conn, data):
    """Clean every place in the reply and save it. Bad places are logged and skipped."""
    counts = {"inserted": 0, "updated": 0, "skipped": 0}
    for place in data.get("places", []):
        try:
            lead = parse_place(place)
        except ValueError as error:
            log.warning("Skipped a place: %s", error)
            counts["skipped"] += 1
            continue
        counts[upsert_lead(conn, lead)] += 1
    return counts


def main():
    parser = argparse.ArgumentParser(description="Collect local business leads into a database.")
    parser.add_argument(
        "--live",
        metavar="SEARCH",
        help='make a REAL Google call, for example: --live "plumbers in Fort Lauderdale, FL"',
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    conn = connect()
    create_table(conn)
    create_call_log(conn)

    try:
        data = fetch_live(conn, args.live) if args.live else load_sample()
    except (RuntimeError, requests.RequestException, OSError, json.JSONDecodeError) as error:
        log.error("Could not get data: %s", error)
        sys.exit(1)

    counts = save_places(conn, data)
    total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    log.info(
        "Done. inserted=%s updated=%s skipped=%s | %s leads in the database",
        counts["inserted"], counts["updated"], counts["skipped"], total,
    )


if __name__ == "__main__":
    main()