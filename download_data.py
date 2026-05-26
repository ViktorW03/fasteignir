#!/usr/bin/env python3
"""
Downloads all data from g.mbl.is GraphQL API into a local SQLite database.

Tables created:
  - listings       : active property listings (fs_fasteign)
  - purchase_history: sold transaction records (fs_purchase_history)
  - agencies       : real estate agencies (fs_sala)
  - postal_codes   : postal code → city mapping (fs_postal_code)

Usage:
    pip install requests
    python3 download_data.py

    # Resume after interruption (skips already-fetched pages):
    python3 download_data.py --resume

    # Only refresh listings (fast, daily use):
    python3 download_data.py --only listings
"""

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime

import requests

ENDPOINT = "https://g.mbl.is/v1/graphql"
HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://www.mbl.is",
    "Referer": "https://www.mbl.is/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/146.0.0.0 Safari/537.36",
}
DB_PATH = "mbl_fasteignir.db"
BATCH_SIZE = 100
DELAY = 0.3  # seconds between requests — be polite


def gql(query: str, variables: dict = None):
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = requests.post(ENDPOINT, headers=HEADERS, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL error: {data['errors']}")
    return data["data"]


def setup_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS listings (
            eign_id         INTEGER PRIMARY KEY,
            heimilisfang    TEXT,
            hverfi          TEXT,
            postfang        INTEGER,
            city            TEXT,
            teg_eign        TEXT,
            verd            INTEGER,
            fermetrar       REAL,
            fermetraverd    REAL,
            fasteignamat    INTEGER,
            brunabotamat    INTEGER,
            ahvilandi_lan   INTEGER,
            bygg_ar         INTEGER,
            fjoldi_herb     INTEGER,
            fjoldi_svefnhb  INTEGER,
            fjoldi_badherb  INTEGER,
            fjoldi_haeda    INTEGER,
            latitude        REAL,
            longitude       REAL,
            sent_dags       TEXT,
            br_dags         TEXT,
            nybygging       INTEGER,
            gardur          INTEGER,
            svalir          INTEGER,
            bilskur         INTEGER,
            lyfta           INTEGER,
            parking         INTEGER,
            electric_car    INTEGER,
            pet_allowed     INTEGER,
            wheelchair_acc  INTEGER,
            seniors         INTEGER,
            makaskipti      INTEGER,
            aukaibud        INTEGER,
            agency_id       INTEGER,
            agency_name     TEXT,
            dealer_email    TEXT,
            syna            INTEGER,
            fetched_at      TEXT
        );

        CREATE TABLE IF NOT EXISTS purchase_history (
            faerslunumer    INTEGER PRIMARY KEY,
            heimlilisfang   TEXT,
            postnr          TEXT,
            sveitarfelag    TEXT,
            kaupverd        INTEGER,        -- in thousands of ISK (multiply by 1000)
            einflm          REAL,           -- price per sqm at sale
            fasteignamat    INTEGER,
            tegund          TEXT,
            byggar          TEXT,
            thinglystdags   TEXT,           -- legal registration date
            created         TEXT,
            fetched_at      TEXT
        );

        CREATE TABLE IF NOT EXISTS agencies (
            sala_id         INTEGER PRIMARY KEY,
            nafn            TEXT,
            heimilisfang    TEXT,
            postnumer       TEXT,
            email           TEXT,
            simi            TEXT,
            vefslod         TEXT,
            logo_url        TEXT,
            fetched_at      TEXT
        );

        CREATE TABLE IF NOT EXISTS postal_codes (
            postnr          TEXT PRIMARY KEY,
            baer            TEXT,
            fetched_at      TEXT
        );

        -- Track what we've already downloaded for resuming
        CREATE TABLE IF NOT EXISTS _sync_state (
            table_name      TEXT PRIMARY KEY,
            last_offset     INTEGER DEFAULT 0,
            total_fetched   INTEGER DEFAULT 0,
            completed       INTEGER DEFAULT 0,
            last_run        TEXT
        );
    """)
    conn.commit()


def get_sync_state(conn, table_name):
    row = conn.execute(
        "SELECT last_offset, total_fetched, completed FROM _sync_state WHERE table_name = ?",
        (table_name,)
    ).fetchone()
    if row:
        return {"last_offset": row[0], "total_fetched": row[1], "completed": bool(row[2])}
    return {"last_offset": 0, "total_fetched": 0, "completed": False}


def update_sync_state(conn, table_name, offset, total_fetched, completed=False):
    conn.execute("""
        INSERT INTO _sync_state (table_name, last_offset, total_fetched, completed, last_run)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(table_name) DO UPDATE SET
            last_offset = excluded.last_offset,
            total_fetched = excluded.total_fetched,
            completed = excluded.completed,
            last_run = excluded.last_run
    """, (table_name, offset, total_fetched, int(completed), datetime.utcnow().isoformat()))
    conn.commit()


# ---------------------------------------------------------------------------
# Listings (fs_fasteign)
# ---------------------------------------------------------------------------

LISTINGS_QUERY = """
query GetListings($limit: Int!, $offset: Int!) {
  fs_fasteign(
    limit: $limit
    offset: $offset
    order_by: {eign_id: asc}
  ) {
    eign_id
    heimilisfang
    hverfi
    postfang
    teg_eign
    verd
    fermetrar
    fermetraverd
    fasteignamat
    brunabotamat
    ahvilandi_lan
    bygg_ar
    fjoldi_herb
    fjoldi_svefnhb
    fjoldi_badherb
    fjoldi_haeda
    latitude
    longitude
    sent_dags
    br_dags
    nybygging
    gardur
    svalir
    bilskur
    lyfta
    parking
    electric_car
    pet_allowed
    wheelchair_acc
    seniors
    makaskipti
    aukaibud
    dealer_email
    syna
    agency { id: sala_id  name: nafn }
    postal_code { city: baer }
  }
}
"""


def download_listings(conn, resume=False):
    state = get_sync_state(conn, "listings")
    if state["completed"] and resume:
        print("  listings: already complete, skipping")
        return

    offset = state["last_offset"] if resume else 0
    total = state["total_fetched"] if resume else 0
    now = datetime.utcnow().isoformat()

    print(f"Downloading listings (starting at offset {offset})...")
    while True:
        data = gql(LISTINGS_QUERY, {"limit": BATCH_SIZE, "offset": offset})
        rows = data["fs_fasteign"]
        if not rows:
            break

        conn.executemany("""
            INSERT OR REPLACE INTO listings VALUES (
                :eign_id, :heimilisfang, :hverfi, :postfang, :city, :teg_eign,
                :verd, :fermetrar, :fermetraverd, :fasteignamat, :brunabotamat,
                :ahvilandi_lan, :bygg_ar, :fjoldi_herb, :fjoldi_svefnhb, :fjoldi_badherb,
                :fjoldi_haeda, :latitude, :longitude, :sent_dags, :br_dags,
                :nybygging, :gardur, :svalir, :bilskur, :lyfta, :parking,
                :electric_car, :pet_allowed, :wheelchair_acc, :seniors, :makaskipti,
                :aukaibud, :agency_id, :agency_name, :dealer_email, :syna, :fetched_at
            )
        """, [
            {
                **r,
                "city": (r.get("postal_code") or {}).get("city"),
                "agency_id": (r.get("agency") or {}).get("id"),
                "agency_name": (r.get("agency") or {}).get("name"),
                "nybygging": int(r.get("nybygging") or False),
                "gardur": int(r.get("gardur") or False),
                "svalir": int(r.get("svalir") or False),
                "bilskur": int(r.get("bilskur") or False),
                "lyfta": int(r.get("lyfta") or False),
                "parking": int(r.get("parking") or False),
                "electric_car": int(r.get("electric_car") or False),
                "pet_allowed": int(r.get("pet_allowed") or False),
                "wheelchair_acc": int(r.get("wheelchair_acc") or False),
                "seniors": int(r.get("seniors") or False),
                "makaskipti": int(r.get("makaskipti") or False),
                "aukaibud": int(r.get("aukaibud") or False),
                "syna": int(r.get("syna") or False),
                "fetched_at": now,
            }
            for r in rows
        ])
        conn.commit()

        total += len(rows)
        offset += len(rows)
        update_sync_state(conn, "listings", offset, total)
        print(f"  listings: {total} rows fetched", end="\r")
        time.sleep(DELAY)

    update_sync_state(conn, "listings", offset, total, completed=True)
    print(f"\n  ✓ listings complete: {total} total rows")


# ---------------------------------------------------------------------------
# Purchase History (fs_purchase_history)
# ---------------------------------------------------------------------------

PURCHASE_QUERY = """
query GetPurchaseHistory($limit: Int!, $offset: Int!) {
  fs_purchase_history(
    limit: $limit
    offset: $offset
    order_by: {faerslunumer: asc}
  ) {
    faerslunumer
    heimlilisfang
    postnr
    sveitarfelag
    kaupverd
    einflm
    fasteignamat
    tegund
    byggar
    thinglystdags
    created
  }
}
"""


def download_purchase_history(conn, resume=False):
    state = get_sync_state(conn, "purchase_history")
    if state["completed"] and resume:
        print("  purchase_history: already complete, skipping")
        return

    offset = state["last_offset"] if resume else 0
    total = state["total_fetched"] if resume else 0
    now = datetime.utcnow().isoformat()

    print(f"Downloading purchase history (starting at offset {offset})...")
    while True:
        data = gql(PURCHASE_QUERY, {"limit": BATCH_SIZE, "offset": offset})
        rows = data["fs_purchase_history"]
        if not rows:
            break

        conn.executemany("""
            INSERT OR REPLACE INTO purchase_history VALUES (
                :faerslunumer, :heimlilisfang, :postnr, :sveitarfelag,
                :kaupverd, :einflm, :fasteignamat, :tegund, :byggar,
                :thinglystdags, :created, :fetched_at
            )
        """, [{**r, "fetched_at": now} for r in rows])
        conn.commit()

        total += len(rows)
        offset += len(rows)
        update_sync_state(conn, "purchase_history", offset, total)
        print(f"  purchase_history: {total} rows fetched", end="\r")
        time.sleep(DELAY)

    update_sync_state(conn, "purchase_history", offset, total, completed=True)
    print(f"\n  ✓ purchase_history complete: {total} total rows")


# ---------------------------------------------------------------------------
# Agencies (fs_sala)
# ---------------------------------------------------------------------------

AGENCIES_QUERY = """
query GetAgencies($limit: Int!, $offset: Int!) {
  fs_sala(limit: $limit, offset: $offset, order_by: {sala_id: asc}) {
    sala_id
    nafn
    heimilisfang
    postnumer
    email: email_tl
    simi
    vefslod
    logo_url
  }
}
"""


def download_agencies(conn, resume=False):
    state = get_sync_state(conn, "agencies")
    if state["completed"] and resume:
        print("  agencies: already complete, skipping")
        return

    offset = 0
    total = 0
    now = datetime.utcnow().isoformat()

    print("Downloading agencies...")
    while True:
        data = gql(AGENCIES_QUERY, {"limit": BATCH_SIZE, "offset": offset})
        rows = data["fs_sala"]
        if not rows:
            break

        conn.executemany("""
            INSERT OR REPLACE INTO agencies VALUES (
                :sala_id, :nafn, :heimilisfang, :postnumer,
                :email, :simi, :vefslod, :logo_url, :fetched_at
            )
        """, [{**r, "fetched_at": now} for r in rows])
        conn.commit()

        total += len(rows)
        offset += len(rows)
        time.sleep(DELAY)

    update_sync_state(conn, "agencies", offset, total, completed=True)
    print(f"  ✓ agencies complete: {total} total rows")


# ---------------------------------------------------------------------------
# Postal Codes (fs_postal_code)
# ---------------------------------------------------------------------------

POSTAL_QUERY = """
{
  fs_postal_code {
    postnr
    baer
  }
}
"""


def download_postal_codes(conn):
    print("Downloading postal codes...")
    data = gql(POSTAL_QUERY)
    rows = data["fs_postal_code"]
    now = datetime.utcnow().isoformat()

    conn.executemany(
        "INSERT OR REPLACE INTO postal_codes VALUES (:postnr, :baer, :fetched_at)",
        [{**r, "fetched_at": now} for r in rows]
    )
    conn.commit()
    print(f"  ✓ postal_codes: {len(rows)} rows")


# ---------------------------------------------------------------------------
# Summary queries after download
# ---------------------------------------------------------------------------

def print_summary(conn):
    print("\n--- Database Summary ---")
    tables = ["listings", "purchase_history", "agencies", "postal_codes"]
    for t in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:25s}: {count:,} rows")

    print("\n--- Active listings by type ---")
    rows = conn.execute("""
        SELECT teg_eign, COUNT(*) as n,
               ROUND(AVG(verd)/1000000.0, 1) as avg_price_m,
               ROUND(AVG(fermetraverd)) as avg_per_sqm
        FROM listings WHERE syna = 1 AND fermetrar > 0
        GROUP BY teg_eign ORDER BY n DESC
    """).fetchall()
    for r in rows:
        print(f"  {r[0]:12s}: {r[1]:4d} listings | avg {r[2]}M ISK | {r[3]:,} ISK/m²")

    print("\n--- Active listings by postal code (top 10) ---")
    rows = conn.execute("""
        SELECT postfang, city, COUNT(*) as n,
               ROUND(AVG(verd)/1000000.0, 1) as avg_price_m
        FROM listings WHERE syna = 1
        GROUP BY postfang ORDER BY n DESC LIMIT 10
    """).fetchall()
    for r in rows:
        print(f"  {r[0]} {(r[1] or ''):20s}: {r[2]:4d} listings | avg {r[3]}M ISK")

    print("\n--- Price changes detected (br_dags != sent_dags) ---")
    changed = conn.execute("""
        SELECT COUNT(*) FROM listings WHERE syna = 1 AND br_dags != sent_dags
    """).fetchone()[0]
    print(f"  {changed} listings have had price updates")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Download mbl.is real estate data to SQLite")
    parser.add_argument("--resume", action="store_true", help="Resume a previous download")
    parser.add_argument("--only", choices=["listings", "purchase_history", "agencies", "postal_codes"],
                        help="Only download a specific table")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    setup_db(conn)

    print(f"Database: {DB_PATH}")
    print(f"Started:  {datetime.utcnow().isoformat()}\n")

    only = args.only
    try:
        if not only or only == "postal_codes":
            download_postal_codes(conn)
        if not only or only == "agencies":
            download_agencies(conn, resume=args.resume)
        if not only or only == "listings":
            download_listings(conn, resume=args.resume)
        if not only or only == "purchase_history":
            download_purchase_history(conn, resume=args.resume)
    except KeyboardInterrupt:
        print("\n\nInterrupted — progress saved. Run with --resume to continue.")
        sys.exit(0)

    print_summary(conn)
    conn.close()
    print(f"\nDone. Open with: sqlite3 {DB_PATH}")
    print("Or: datasette mbl_fasteignir.db  (pip install datasette)")


if __name__ == "__main__":
    main()