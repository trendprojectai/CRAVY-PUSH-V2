from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import subprocess
import os
import json

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
