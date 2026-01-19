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
    try:
        # Run the existing main.py script
        process = subprocess.Popen(
            ["python", "main.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        # Stream logs live to Railway
        for line in process.stdout:
            print(line, end="")

        process.wait()

        if process.returncode != 0:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": "Script failed — check Railway logs"
                }
            )

        # If CSV exists, return it as a download
        if os.path.exists(CSV_FILENAME):
            return FileResponse(
                path=CSV_FILENAME,
                media_type="text/csv",
                filename=CSV_FILENAME
            )

        # Fallback if CSV was not created
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "CSV not found after script completed"
            }
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": "exception",
                "message": str(e)
            }
        )

        return {
            "status": "exception",
            "message": str(e)
        }
