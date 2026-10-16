import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile as StarletteUploadFile

from src import orchestrator
from src.intelligence.ingest import load_reviews
from src.mcp import gate

UI_DIR = Path(__file__).resolve().parent / "ui"

app = FastAPI(title="Review Insights")
app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(UI_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/api/reviews/preview")
async def reviews_preview(file: UploadFile | None = None) -> dict:
    if file is not None:
        reviews = load_reviews(file.file)
    else:
        reviews = load_reviews(orchestrator.SAMPLE_CSV)
    return {
        "count": len(reviews),
        "first_5": [r.model_dump(mode="json") for r in reviews[:5]],
    }


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@app.post("/api/runs")
async def create_run(request: Request) -> dict:
    """Start a run from an uploaded CSV (multipart ``file``) or ``{"use_sample": true}``."""
    content_type = request.headers.get("content-type", "")
    csv_path: str | None = None
    temp_path: str | None = None

    if content_type.startswith("multipart/form-data") or content_type.startswith(
        "application/x-www-form-urlencoded"
    ):
        form = await request.form()
        upload = form.get("file")
        if isinstance(upload, StarletteUploadFile) and upload.filename:
            data = await upload.read()
            fd, temp_path = tempfile.mkstemp(suffix=".csv")
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            csv_path = temp_path
        elif not _truthy(form.get("use_sample")):
            raise HTTPException(
                status_code=400, detail="Provide a CSV file or use_sample=true."
            )
    elif "application/json" in content_type:
        try:
            body = await request.json()
        except ValueError:
            body = {}
        if not _truthy(body.get("use_sample")):
            raise HTTPException(
                status_code=400, detail="Provide a CSV file or use_sample=true."
            )
    else:
        raise HTTPException(
            status_code=400, detail="Expected multipart CSV or JSON body."
        )

    try:
        run = await run_in_threadpool(
            orchestrator.start_run, csv_path or orchestrator.SAMPLE_CSV
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

    return run.model_dump(mode="json")


@app.get("/api/runs/{run_id}")
def read_run(run_id: str) -> dict:
    run = orchestrator.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return run.model_dump(mode="json")


ARTIFACTS = {
    "notes": ("notes.md", gate.TOOL_NOTES),
    "email-draft": ("email-draft.md", gate.TOOL_EMAIL),
}


@app.get("/api/runs/{run_id}/artifacts/{name}", include_in_schema=False)
def read_artifact(run_id: str, name: str, download: bool = False) -> FileResponse:
    """Serve an approved run's output file (view or download).

    Only the two known artifacts are reachable, and only after the matching
    MCP tool logged success for this run — there is no arbitrary file access.
    """
    run = orchestrator.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")

    entry = ARTIFACTS.get(name)
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown artifact.")
    filename, tool = entry

    if not any(log.tool == tool and log.ok for log in run.logs):
        raise HTTPException(
            status_code=409, detail="Artifact not written yet; approve the run first."
        )

    path = orchestrator.OUTPUT_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact file not found on disk.")

    return FileResponse(
        path,
        media_type="text/markdown; charset=utf-8",
        filename=filename if download else None,
    )


@app.post("/api/runs/{run_id}/approve")
def approve_run(run_id: str) -> dict:
    run = orchestrator.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    try:
        run = gate.approve(run)
    except gate.GateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    orchestrator.save_run(run)
    return run.model_dump(mode="json")


@app.post("/api/runs/{run_id}/reject")
def reject_run(run_id: str) -> dict:
    run = orchestrator.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    try:
        run = gate.reject(run)
    except gate.GateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    orchestrator.save_run(run)
    return run.model_dump(mode="json")
