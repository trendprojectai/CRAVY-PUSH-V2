from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import csv
import os
import json
import re
import subprocess

import httpx

app = FastAPI()

# ✅ THIS IS THE FIX
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # OK for internal admin tool
    allow_credentials=True,
    allow_methods=["*"],          # Allows OPTIONS, POST, GET
    allow_headers=["*"],
)

MASTER_CSV_FILENAME = "master_restaurants.csv"
ZONES_FILENAME = "zones.json"
SCAN_EVENTS_FILENAME = "scan_events.json"
MAX_SUPABASE_BATCH_SIZE = 500


def load_zones() -> list[dict]:
    if not os.path.exists(ZONES_FILENAME):
        return []

    try:
        with open(ZONES_FILENAME, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def find_zone(zones: list[dict], zone_id: str | None) -> dict | None:
    if not zone_id:
        return None
    for zone in zones:
        if zone.get("zone_id") == zone_id:
            return zone
    return None


def get_latest_csv_filename() -> str | None:
    csv_files = [
        filename
        for filename in os.listdir(".")
        if filename.lower().endswith(".csv") and os.path.isfile(filename)
    ]
    if not csv_files:
        return None
    return max(csv_files, key=lambda filename: os.path.getmtime(filename))


def parse_zone_name_from_filename(filename: str, zones: list[dict]) -> str | None:
    match = re.search(r"zone_([^_]+)", filename.lower())
    zone_id = match.group(1) if match else None
    for zone in zones:
        candidate_id = str(zone.get("zone_id", "")).lower()
        if not candidate_id:
            continue
        if zone_id and candidate_id == zone_id:
            return zone.get("zone_name")
        if candidate_id in filename.lower():
            return zone.get("zone_name")
    return None


def normalize_row(row: dict) -> dict:
    def normalize_number(value: str, cast):
        if value is None:
            return None
        value = value.strip()
        if value == "":
            return None
        try:
            return cast(value)
        except ValueError:
            return None

    normalized = {key: (value.strip() if isinstance(value, str) else value) for key, value in row.items()}
    for key in ("latitude", "longitude", "rating"):
        normalized[key] = normalize_number(normalized.get(key), float)
    for key in ("reviews_count", "price_level"):
        normalized[key] = normalize_number(normalized.get(key), int)
    for key, value in normalized.items():
        if isinstance(value, str) and value == "":
            normalized[key] = None
    return normalized


def read_csv_rows(csv_filename: str) -> list[dict]:
    with open(csv_filename, newline="", encoding="utf-8") as file_handle:
        reader = csv.DictReader(file_handle)
        return [normalize_row(row) for row in reader]


def chunk_rows(rows: list[dict], chunk_size: int) -> list[list[dict]]:
    return [rows[index:index + chunk_size] for index in range(0, len(rows), chunk_size)]


async def insert_restaurants(
    client: httpx.AsyncClient,
    supabase_url: str,
    supabase_key: str,
    rows: list[dict]
) -> tuple[int, str | None]:
    inserted_rows = 0
    error_message = None
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=ignore-duplicates,return=representation"
    }
    endpoint = f"{supabase_url}/rest/v1/restaurants?on_conflict=google_place_id"
    batches = chunk_rows(rows, MAX_SUPABASE_BATCH_SIZE)

    for index, batch in enumerate(batches, start=1):
        print(f"📤 Supabase batch {index}/{len(batches)}: inserting {len(batch)} rows", flush=True)
        response = await client.post(endpoint, headers=headers, json=batch)
        if response.status_code >= 400:
            error_message = f"Batch {index} failed: {response.status_code} {response.text}"
            print(f"❌ {error_message}", flush=True)
            break

        try:
            inserted_rows += len(response.json())
        except json.JSONDecodeError:
            error_message = f"Batch {index} returned invalid JSON"
            print(f"❌ {error_message}", flush=True)
            break

        await asyncio.sleep(0)

    return inserted_rows, error_message


async def log_push(
    client: httpx.AsyncClient,
    supabase_url: str,
    supabase_key: str,
    payload: dict
) -> None:
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    endpoint = f"{supabase_url}/rest/v1/csv_push_logs"
    response = await client.post(endpoint, headers=headers, json=payload)
    if response.status_code >= 400:
        print(
            f"⚠️ Failed to log push: {response.status_code} {response.text}",
            flush=True
        )


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/run-zone-scan")
def run_zone_scan(zone_id: str | None = None):
    """
    Runs the long job and writes the CSV to disk.
    Returns JSON after completion.
    """
    try:
        command = ["python", "main.py"]
        if zone_id:
            command.extend(["--zone-id", zone_id])

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        # Stream logs to Railway
        for line in process.stdout:
            print(line, end="")

        process.wait()

        if process.returncode != 0:
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Script failed — check Railway logs"}
            )

        if not os.path.exists(MASTER_CSV_FILENAME):
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Run finished but master CSV not found"}
            )

        zones = load_zones()
        zone = find_zone(zones, zone_id)
        if zone:
            return {
                "status": "complete",
                "zone_id": zone.get("zone_id"),
                "scan_id": zone.get("scan_count", 0),
                "new_found": zone.get("last_scan_new_found", 0),
                "total_discovered": zone.get("total_discovered", 0),
                "likely_complete": zone.get("likely_complete", False)
            }

        return {
            "status": "complete",
            "zones": zones
        }

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "exception", "message": str(e)}
        )


@app.post("/run-soho-import")
def run_soho_import():
    return run_zone_scan()


@app.get("/download-zone-csv")
def download_zone_csv(zone_id: str | None = None, scan_number: int | None = None):
    """
    Instant download endpoint.
    """
    zones = load_zones()
    zone = find_zone(zones, zone_id)
    if zone and scan_number is None:
        scan_number = zone.get("scan_count")

    if zone and scan_number:
        filename = f"zone_{zone.get('zone_id')}_scan_{scan_number}.csv"
        if os.path.exists(filename):
            return FileResponse(
                path=filename,
                media_type="text/csv",
                filename=filename
            )

    if not os.path.exists(MASTER_CSV_FILENAME):
        return JSONResponse(
            status_code=404,
            content={
                "status": "not_ready",
                "message": "CSV not found yet. Run /run-zone-scan first."
            }
        )

    return FileResponse(
        path=MASTER_CSV_FILENAME,
        media_type="text/csv",
        filename=MASTER_CSV_FILENAME
    )


@app.get("/download-soho-csv")
def download_soho_csv():
    return download_zone_csv()


@app.get("/scan-events")
def get_scan_events():
    if not os.path.exists(SCAN_EVENTS_FILENAME):
        return []

    events: list[dict] = []
    with open(SCAN_EVENTS_FILENAME, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return events


@app.post("/push-to-supabase")
async def push_to_supabase():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        return JSONResponse(
            status_code=500,
            content={"status": "failed", "message": "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY"}
        )

    csv_filename = get_latest_csv_filename()
    if not csv_filename:
        return JSONResponse(
            status_code=404,
            content={"status": "failed", "message": "No CSV files found on disk"}
        )

    print(f"📄 Reading CSV: {csv_filename}", flush=True)
    try:
        rows = await asyncio.to_thread(read_csv_rows, csv_filename)
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"status": "failed", "message": f"Failed to read CSV: {exc}"}
        )

    total_rows = len(rows)
    if total_rows == 0:
        return {"status": "success", "total_rows": 0, "inserted_rows": 0, "skipped_rows": 0}

    zones = load_zones()
    zone_name = parse_zone_name_from_filename(csv_filename, zones)

    async with httpx.AsyncClient(timeout=60.0) as client:
        inserted_rows, error_message = await insert_restaurants(
            client,
            supabase_url,
            supabase_key,
            rows
        )

        skipped_rows = max(total_rows - inserted_rows, 0)
        if error_message:
            status = "partial" if inserted_rows > 0 else "failed"
        else:
            status = "success" if skipped_rows == 0 else "partial"

        log_payload = {
            "csv_filename": os.path.basename(csv_filename),
            "zone_name": zone_name,
            "total_rows": total_rows,
            "inserted_rows": inserted_rows,
            "skipped_rows": skipped_rows,
            "status": status,
            "error_message": error_message
        }
        await log_push(client, supabase_url, supabase_key, log_payload)

    return {
        "status": status,
        "total_rows": total_rows,
        "inserted_rows": inserted_rows,
        "skipped_rows": skipped_rows
    }
