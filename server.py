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

CSV_FILENAME = "soho_restaurants_final.csv"
SCAN_HISTORY_FILENAME = "scan_history.json"
SCAN_EVENTS_FILENAME = "scan_events.json"


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/run-soho-import")
def run_soho_import():
    """
    Runs the long job and writes the CSV to disk.
    Returns JSON after completion.
    """
    try:
        process = subprocess.Popen(
            ["python", "main.py"],
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

        if not os.path.exists(CSV_FILENAME):
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Run finished but CSV not found"}
            )

        scan_id = 0
        new_found = 0
        total_discovered = 0
        if os.path.exists(SCAN_HISTORY_FILENAME):
            try:
                with open(SCAN_HISTORY_FILENAME, encoding="utf-8") as f:
                    history = json.load(f)
                if isinstance(history, list) and history:
                    latest = history[-1]
                    scan_id = latest.get("scan_number", 0)
                    new_found = latest.get("new_found", 0)
                    total_discovered = latest.get("total", 0)
            except json.JSONDecodeError:
                pass

        return {
            "status": "complete",
            "scan_id": scan_id,
            "new_found": new_found,
            "total_discovered": total_discovered
        }

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "exception", "message": str(e)}
        )


@app.get("/download-soho-csv")
def download_soho_csv():
    """
    Instant download endpoint.
    """
    if not os.path.exists(CSV_FILENAME):
        return JSONResponse(
            status_code=404,
            content={
                "status": "not_ready",
                "message": "CSV not found yet. Run /run-soho-import first."
            }
        )

    return FileResponse(
        path=CSV_FILENAME,
        media_type="text/csv",
        filename=CSV_FILENAME
    )


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
