"""Local DesignQA API and background job coordinator."""
import json
import os
import threading
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, SecretStr, StringConstraints

from .sources import BusinessError, SystemFault, figma_url, live_url
from .storage import Store
from .worker import ROOT, analyze, prepare

Width = Annotated[int, Field(ge=320, le=2560)]
Short = Annotated[str, StringConstraints(max_length=2000)]
ACTIVE = {"queued", "running", "awaiting_frames", "awaiting_mapping"}


class Start(BaseModel):
    mode: Literal["figma", "demo"]
    breakpoints: list[Width] = Field(min_length=1, max_length=2)
    figma_url: Short | None = None
    live_url: Short | None = None
    figma_token: SecretStr | None = None
    hide_selectors: list[Short] = Field(default_factory=list, max_length=30)
    demo_variant: Literal["baseline", "buggy"] = "buggy"


class FrameChoice(BaseModel):
    breakpoint: Width
    frame_id: Short


class SelectFrames(BaseModel):
    frames: list[FrameChoice] = Field(min_length=1, max_length=2)


class MappingChoice(BaseModel):
    breakpoint: Width
    node_id: Short
    selector: Short | None


class SelectMappings(BaseModel):
    mappings: list[MappingChoice] = Field(max_length=240)


def now():
    return datetime.now(timezone.utc).isoformat()


def create_app(root=None):
    root = Path(root or os.getenv("DESIGNQA_OUTPUT", ROOT / "Output/web")).resolve()
    lock = threading.RLock()
    sessions = {}

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(root)
        app.state.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="designqa")
        try:
            yield
        finally:
            app.state.pool.shutdown(wait=True, cancel_futures=True)
            sessions.clear()

    app = FastAPI(title="DesignQA", lifespan=lifespan)

    @app.middleware("http")
    async def workspace_boundary(request: Request, call_next):
        host = request.url.hostname
        origin = request.headers.get("origin")
        local = {"127.0.0.1", "localhost", "::1", "testserver"}
        if host not in local or (origin and urlsplit(origin).hostname not in local):
            return JSONResponse({"detail": "DesignQA is available on the local workspace."}, status_code=403)
        response = await call_next(request)
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        fields = ", ".join(".".join(str(part) for part in issue["loc"][1:]) for issue in error.errors()[:5])
        return JSONResponse({"detail": f"Check the submitted fields: {fields}."}, status_code=422)

    @app.exception_handler(BusinessError)
    async def bad_input(request, error):
        return JSONResponse({"detail": str(error)}, status_code=422)

    def get(job_id):
        job = app.state.store.get(str(job_id))
        if not job:
            raise HTTPException(404, "Analysis not found.")
        return job

    def save(job):
        with app.state.store.connect() as db:
            app.state.store.put(job, db)

    def public(job):
        return {key: value for key, value in job.items()
                if key not in {"file_key", "preferred", "hide_selectors"}}

    def run(job_id):
        job = get(job_id)
        with lock:
            session = sessions[job_id]
        job.update(state="running", error=None)
        save(job)
        started = time.monotonic()

        def complete_stage():
            if job.get("stage"):
                event = {"stage": job["stage"], "message": job.get("stage_message"), "at": now()}
                job["events"].append(event)
                job["events"] = job["events"][-100:]

        def stage(key, detail=None):
            complete_stage()
            job.update(stage=key, stage_message=detail, elapsed_seconds=round(time.monotonic() - started, 1))
            save(job)

        try:
            stage("validate")
            if job["mode"] == "figma":
                live_url(job["live_url"], resolve=True)
                prepare(job, session, app.state.store, stage)
            if job["state"] == "running":
                analyze(job, session, root, stage, save)
            complete_stage()
            job["stage"] = None
            job["elapsed_seconds"] = round(time.monotonic() - started, 1)
        except (BusinessError, SystemFault) as error:
            job.update(state="failed", error={"type": type(error).__name__, "message": str(error)})
        except Exception as error:
            logging.getLogger(__name__).error("Analysis %s raised %s", job_id, type(error).__name__)
            job.update(state="failed", error={"type": "SystemFault", "message": "The worker could not finish the analysis. Check that Chromium is installed and retry."})
        with lock:
            save(job)
            if job["state"] not in ACTIVE:
                sessions.pop(job_id, None)

    def enqueue(job):
        job["state"] = "queued"
        save(job)
        app.state.pool.submit(run, job["job_id"])

    @app.get("/api/health")
    def health():
        return {"status": "ok", "scope": "local"}

    @app.post("/api/analyze", status_code=202)
    def start(data: Start):
        widths = data.breakpoints
        if len(widths) != len(set(widths)):
            raise BusinessError("Choose distinct viewport widths.")
        key = preferred = token = source = target = None
        if data.mode == "figma":
            key, preferred = figma_url(data.figma_url or "")
            target = live_url(data.live_url or "")
            token = (data.figma_token.get_secret_value().strip() if data.figma_token else "") or os.getenv("FIGMA_TOKEN", "").strip()
            if not token:
                raise BusinessError("Provide a Figma access token or set FIGMA_TOKEN on the server.")
            if len(token) > 1024 or any(char.isspace() for char in token):
                raise BusinessError("The Figma access token is invalid.")
            if any(token in value for value in [target, data.figma_url or "", *data.hide_selectors]):
                raise BusinessError("Remove the Figma access token from other fields.")
            source = f"https://www.figma.com/design/{key}" + (f"?node-id={preferred.replace(':', '-')}" if preferred else "")
        elif any(width not in {375, 1440} for width in widths):
            raise BusinessError("Demo viewports are 1440 and 375 px.")
        job = {"job_id": str(uuid4()), "mode": data.mode, "created_at": now(), "events": [],
               "breakpoints": widths, "total_checks": len(widths), "completed_checks": 0,
               "file_key": key, "preferred": preferred, "figma_url": source, "live_url": target,
               "hide_selectors": data.hide_selectors if data.mode == "figma" else [], "demo_variant": data.demo_variant}
        with lock:
            if len(sessions) >= 12:
                raise HTTPException(429, "The workspace already has too many active analyses.")
            sessions[job["job_id"]] = {"token": token}
            enqueue(job)
        return {"job_id": job["job_id"], "status_url": f"/api/analyze/{job['job_id']}"}

    @app.get("/api/analyze/{job_id}")
    def status(job_id: UUID):
        return public(get(job_id))

    @app.post("/api/analyze/{job_id}/frames", status_code=202)
    def select_frames(job_id: UUID, data: SelectFrames):
        with lock:
            job = get(job_id)
            if job["state"] != "awaiting_frames":
                raise HTTPException(409, "This analysis is not waiting for frames.")
            selection = {item.breakpoint: item.frame_id for item in data.frames}
            frames = {frame["id"] for frame in job["frames"]}
            if (set(selection) != set(job["breakpoints"]) or len(selection) != len(data.frames)
                    or not set(selection.values()) <= frames):
                raise BusinessError("Choose an available frame for every breakpoint.")
            sessions[str(job_id)]["selected"] = selection
            job["selected_frames"] = selection
            enqueue(job)
        return {"job_id": str(job_id)}

    @app.post("/api/analyze/{job_id}/mapping", status_code=202)
    def select_mapping(job_id: UUID, data: SelectMappings):
        with lock:
            job = get(job_id)
            if job["state"] != "awaiting_mapping":
                raise HTTPException(409, "This analysis is not waiting for mappings.")
            approved = {(item.breakpoint, item.node_id): item.selector for item in data.mappings}
            valid = {(item["breakpoint"], item["node_id"]) for item in job["mappings"]}
            token = sessions[str(job_id)]["token"]
            if len(approved) != len(data.mappings) or not approved.keys() <= valid:
                raise BusinessError("The submitted mappings do not match the selected frames.")
            if token and any(token in value for value in approved.values() if value):
                raise BusinessError("Remove the Figma access token from the selector.")
            sessions[str(job_id)]["approved"] = approved
            enqueue(job)
        return {"job_id": str(job_id)}

    def completed(job_id):
        job = get(job_id)
        if job["state"] != "completed":
            raise HTTPException(409, "Results are available when the analysis completes.")
        return root / str(job_id)

    @app.get("/api/results/{job_id}")
    def result(job_id: UUID):
        return json.loads((completed(job_id) / "result.json").read_text(encoding="utf-8"))

    @app.get("/api/results/{job_id}/images/{image_id}")
    def image(job_id: UUID, image_id: str):
        run_dir = completed(job_id)
        if Path(image_id).name != image_id or not image_id.endswith(".png"):
            raise HTTPException(404, "Image not found.")
        outputs = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
        expected = {Path(url).name for check in outputs["checks"] for url in check.get("images", {}).values()}
        if image_id not in expected:
            raise HTTPException(404, "Image not found.")
        return FileResponse(run_dir / "images" / image_id, media_type="image/png")

    @app.get("/api/reports/{job_id}")
    def report(job_id: UUID, format: Literal["html", "xlsx", "json"] = "html"):
        name = {"html": "report.html", "xlsx": "findings.xlsx", "json": "result.json"}[format]
        return FileResponse(completed(job_id) / name, filename=f"designqa-{job_id}-{name}")

    @app.get("/api/history")
    def history(offset: Annotated[int, Field(ge=0)] = 0, limit: Annotated[int, Field(ge=1, le=100)] = 30):
        with app.state.store.connect() as db:
            jobs = app.state.store.jobs(db)
        finished = [job for job in jobs if job["state"] == "completed"]
        scores = [job["similarity"] for job in finished if job["similarity"] is not None]
        totals = {"issues": sum(job["issues"] for job in finished),
                  "websites": len({job["live_url"] or "Brewly" for job in finished if job.get("similarity") is not None}),
                  "similarity": sum(scores) / len(scores) if scores else None}
        return {"items": [
            {**{key: job.get(key) for key in ("job_id", "created_at", "state", "verdict", "similarity", "issues")},
             "name": job["live_url"] or f"Brewly demo · {job['demo_variant']}"}
            for job in jobs[offset:offset + limit]], "totals": totals, "total": len(jobs)}

    frontend = ROOT / "frontend/dist"
    if (frontend / "index.html").is_file():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


app = create_app()

