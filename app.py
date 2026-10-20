"""Web page for the Local Lead Scraper.

Run it with:  uv run streamlit run app.py

The page runs the cleaning and saving steps on made-up sample data, or on a
file the visitor uploads. It never calls Google.
"""

import csv
import json
from io import StringIO
from typing import Any, NamedTuple

import streamlit as st

from database import connect, create_table
from scraper import SAMPLE_FILE, save_places

SAMPLE_CHOICE = "Try the sample data"
UPLOAD_CHOICE = "Upload my own file"
LEAD_FIELDS = ["place_id", "name", "address", "phone", "website"]
LEADS_FILE = "leads.csv"
FORMAT_MESSAGE = 'The file needs a "places" list in the same format as the sample.'

# Readable column names for the tables on the page
COLUMNS = {
    "place_id": st.column_config.TextColumn("Place ID"),
    "name": st.column_config.TextColumn("Business"),
    "address": st.column_config.TextColumn("Address"),
    "phone": st.column_config.TextColumn("Phone"),
    "website": st.column_config.TextColumn("Website"),
}


class ReplyError(Exception):
    """A problem with an uploaded file that the visitor can fix."""


class Result(NamedTuple):
    runs: list[dict[str, int]]
    leads: list[dict[str, Any]]


def read_reply(data: bytes) -> dict[str, Any]:
    """Read a file in the same format as Google's reply."""
    try:
        reply = json.loads(data)
    except ValueError as exc:
        raise ReplyError("The file isn't valid JSON.") from exc

    if not isinstance(reply, dict):
        raise ReplyError(FORMAT_MESSAGE)
    places = reply.get("places")
    if not isinstance(places, list) or not all(isinstance(p, dict) for p in places):
        raise ReplyError(FORMAT_MESSAGE)
    return reply


def raw_records(reply: dict[str, Any]) -> list[dict[str, Any]]:
    """The records as they arrive, before any cleaning."""
    records = []
    for place in reply["places"]:
        display_name = place.get("displayName")
        records.append(
            {
                "place_id": place.get("id"),
                "name": (
                    display_name.get("text") if isinstance(display_name, dict) else None
                ),
                "address": place.get("formattedAddress"),
                "phone": place.get("nationalPhoneNumber"),
                "website": place.get("websiteUri"),
            }
        )
    return records


def run_scraper(reply: dict[str, Any], runs: int) -> Result:
    """Clean and save the records, as many times as asked, in a new database.

    The database lives only in memory, so each visitor gets their own.
    """
    conn = connect(":memory:")
    try:
        create_table(conn)
        counts = []
        for _ in range(runs):
            run = save_places(conn, reply)
            run["total"] = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
            counts.append(run)
        rows = conn.execute(
            "SELECT place_id, name, address, phone, website FROM leads ORDER BY name"
        ).fetchall()
        return Result(counts, [dict(row) for row in rows])
    finally:
        conn.close()


def leads_csv(leads: list[dict[str, Any]]) -> str:
    """The saved leads as CSV text, for the download button."""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=LEAD_FIELDS)
    writer.writeheader()
    writer.writerows(leads)
    return output.getvalue()


def run_table(runs: list[dict[str, int]]) -> list[dict[str, int]]:
    """One row per run, with the counts from that run."""
    return [
        {
            "Run": number,
            "Inserted": run["inserted"],
            "Updated": run["updated"],
            "Skipped": run["skipped"],
            "Leads in database": run["total"],
        }
        for number, run in enumerate(runs, start=1)
    ]


def start_over() -> None:
    """Go back to one run when the visitor picks different data."""
    st.session_state.runs = 1


def run_again() -> None:
    st.session_state.runs += 1


def show_result(reply: dict[str, Any], result: Result) -> None:
    last = result.runs[-1]
    inserted, updated, skipped, total = st.columns(4)
    inserted.metric("Inserted", last["inserted"])
    updated.metric("Updated", last["updated"])
    skipped.metric("Skipped", last["skipped"])
    total.metric("Leads in database", last["total"])

    st.dataframe(run_table(result.runs), hide_index=True)
    st.caption(
        "Run it again with the same data. Leads already saved are updated, "
        "never duplicated."
    )

    # The two buttons sit side by side on the left
    buttons = st.container(horizontal=True)
    buttons.button("Run it again", on_click=run_again)
    buttons.download_button(
        "Download the leads (CSV)",
        leads_csv(result.leads),
        file_name=LEADS_FILE,
        mime="text/csv",
        type="primary",
    )

    before, after = st.tabs(["Before: as the data arrives", "After: cleaned and saved"])
    with before:
        st.dataframe(
            raw_records(reply), hide_index=True, placeholder="—", column_config=COLUMNS
        )
    with after:
        st.dataframe(
            result.leads, hide_index=True, placeholder="—", column_config=COLUMNS
        )


def main() -> None:
    st.set_page_config(page_title="Local Lead Scraper", layout="wide")
    st.title("Local Lead Scraper")
    st.write(
        "Cleans local business leads and saves them to a SQL database "
        "without duplicates."
    )
    st.caption(
        "This page uses made-up sample data and never calls Google. "
        "The full project collects real leads from the Google Places API."
    )

    if "runs" not in st.session_state:
        st.session_state.runs = 1

    choice = st.radio(
        "Data",
        [SAMPLE_CHOICE, UPLOAD_CHOICE],
        horizontal=True,
        on_change=start_over,
    )

    if choice == SAMPLE_CHOICE:
        data = SAMPLE_FILE.read_bytes()
        st.download_button(
            "Download the sample file",
            data,
            file_name=SAMPLE_FILE.name,
            mime="application/json",
        )
    else:
        st.caption(
            "Upload a .json file in the same format as Google's reply. "
            "Download the sample file to see the format."
        )
        uploaded = st.file_uploader(
            "Upload a file", type=["json"], on_change=start_over
        )
        if uploaded is None:
            st.info("Upload a .json file to clean and save its leads.")
            return
        data = uploaded.getvalue()

    try:
        reply = read_reply(data)
    except ReplyError as exc:
        st.error(str(exc))
        return

    show_result(reply, run_scraper(reply, st.session_state.runs))


if __name__ == "__main__":
    main()
