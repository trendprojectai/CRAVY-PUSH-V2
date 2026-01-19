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
        # Run your existing script
        result = subprocess.run(
            ["python", "main.py"],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return {
                "status": "error",
                "stderr": result.stderr
            }

        return {
            "status": "success",
            "stdout": result.stdout
        }

    except Exception as e:
        return {
            "status": "exception",
            "message": str(e)
        }
