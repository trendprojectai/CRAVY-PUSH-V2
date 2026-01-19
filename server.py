from fastapi import FastAPI
import subprocess
import os

app = FastAPI()

@app.get("/")
def health():
    return {"status": "ok"}

@app.post("/run-soho-import")
def run_soho_import():
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
            return {
                "status": "error",
                "message": "Script failed — check logs"
            }

        return {
            "status": "success",
            "message": "Soho import completed — check logs"
        }

    except Exception as e:
        return {
            "status": "exception",
            "message": str(e)
        }
