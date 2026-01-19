from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
import subprocess
import os

app = FastAPI()

CSV_FILENAME = "soho_restaurants_final.csv"


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/run-soho-import")
def run_soho_import():
    """
    Runs the long job and writes the CSV to disk.
    Returns JSON immediately after completion (no file download).
    """
    try:
        process = subprocess.Popen(
            ["python", "main.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        # Stream logs to Railway in real time
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

        return {"status": "success", "message": f"Generated {CSV_FILENAME}"}

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "exception", "message": str(e)}
        )


@app.get("/download-soho-csv")
def download_soho_csv():
    """
    Instant download endpoint. Only works if CSV exists.
    """
    if not os.path.exists(CSV_FILENAME):
        return JSONResponse(
            status_code=404,
            content={"status": "not_ready", "message": "CSV not found yet. Run /run-soho-import first."}
        )

    return FileResponse(
        path=CSV_FILENAME,
        media_type="text/csv",
        filename=CSV_FILENAME
    )
