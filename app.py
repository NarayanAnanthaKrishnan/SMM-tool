"""
app.py — FastAPI Backend for Social Media Audit Tool

Endpoints:
  GET  /validate/{username}       → Quick Instagram profile check
  POST /audit                     → Start full pipeline (async)
  GET  /audit/{run_id}/status     → Poll pipeline progress
  GET  /audit/{run_id}/results    → Fetch completed audit results
  POST /audit/{run_id}/chat       → Post-analysis follow-up chat
  GET  /audit/{run_id}/charts/{filename} → Serve chart images

Run: uvicorn app:app --reload --port 8000
"""

import os
import sys
import json
import re
import uuid
import asyncio
import requests
from datetime import datetime, timezone
from typing import Optional, List
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

# ── Imports from your existing pipeline ──
from extract import scrape_instagram, clean_payload
from web_scraper import scrape_website
from processor import process_profile
from audit_chat import perform_audit_chat

# Lazy import for orchestrator (heavy LangGraph deps)
# We import inside the function that needs it

# ── Config ──
RUNS_DIR = Path("runs")
RUNS_DIR.mkdir(exist_ok=True)

# In-memory status tracking (swap for Redis in production)
audit_status: dict = {}


# =============================================
# STATUS TRACKING
# =============================================
class AuditProgress:
    """Tracks pipeline progress for a single run."""

    STAGES = [
        ("validating", 5),
        ("scraping_instagram", 15),
        ("scraping_website", 30),
        ("processing", 45),
        ("analyzing", 65),
        ("generating_charts", 80),
        ("generating_outreach", 90),
        ("complete", 100),
    ]

    def __init__(self, run_id: str, username: str):
        self.run_id = run_id
        self.username = username
        self.current_stage = "queued"
        self.progress_pct = 0
        self.error = None
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.completed_at = None

    def advance(self, stage: str):
        self.current_stage = stage
        for name, pct in self.STAGES:
            if name == stage:
                self.progress_pct = pct
                break
        if stage == "complete":
            self.completed_at = datetime.now(timezone.utc).isoformat()
        print(f"  [{self.run_id}] {stage} ({self.progress_pct}%)")

    def fail(self, error: str):
        self.current_stage = "failed"
        self.error = error
        self.completed_at = datetime.now(timezone.utc).isoformat()
        print(f"  [{self.run_id}] FAILED: {error}")

    def to_dict(self):
        return {
            "run_id": self.run_id,
            "username": self.username,
            "status": self.current_stage,
            "progress_pct": self.progress_pct,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


# =============================================
# REQUEST/RESPONSE MODELS
# =============================================
class AuditRequest(BaseModel):
    username: str = Field(..., description="Instagram username (without @)")
    user_context: Optional[str] = Field(
        None,
        description="Optional context about why you're auditing this profile. "
                    "E.g. 'This is my competitor in the fitness niche' or "
                    "'I want to pitch them on email marketing services'",
    )


class AuditResponse(BaseModel):
    run_id: str
    status: str
    message: str


class ChatRequest(BaseModel):
    message: str = Field(..., description="User's follow-up question or instruction")
    history: Optional[List[dict]] = Field(
        default=[],
        description="Conversation history as [{role: 'user'|'assistant', content: '...'}]",
    )


class ChatResponse(BaseModel):
    response: str
    run_id: str


# =============================================
# FASTAPI APP
# =============================================
app = FastAPI(
    title="Social Media Audit API",
    description="Analyze Instagram profiles and generate data-driven outreach messages",
    version="1.0.0",
)

# CORS — allow Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        # Add your production domain here
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================
# ENDPOINT 1: VALIDATE USERNAME
# =============================================
@app.get("/validate/{username}")
async def validate_username(username: str):
    """
    Quick check if an Instagram profile exists.
    No Apify credits burned. No LLM tokens spent.
    Returns in < 2 seconds.
    """
    # Clean the input
    username = username.strip().lstrip("@").split("?")[0].split("/")[-1]

    if not username:
        return {"valid": False, "reason": "empty_username", "username": username}

    if not re.match(r'^[a-zA-Z0-9._]{1,30}$', username):
        return {"valid": False, "reason": "invalid_characters", "username": username}

    # Hit Instagram's public page
    try:
        resp = await asyncio.to_thread(
            requests.get,
            f"https://www.instagram.com/{username}/",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=10,
            allow_redirects=False,
        )

        if resp.status_code == 404:
            return {"valid": False, "reason": "profile_not_found", "username": username}

        if resp.status_code == 301:
            return {"valid": False, "reason": "redirected", "username": username,
                    "detail": "Username may have changed"}

        if resp.status_code == 200:
            return {"valid": True, "username": username}

        # Instagram sometimes returns 302 for login walls
        if resp.status_code in (302, 429):
            return {"valid": True, "username": username,
                    "detail": "Likely valid but Instagram rate-limited the check"}

        return {"valid": False, "reason": f"unexpected_status_{resp.status_code}",
                "username": username}

    except requests.Timeout:
        return {"valid": False, "reason": "timeout", "username": username}
    except requests.RequestException as e:
        return {"valid": False, "reason": "network_error", "username": username,
                "detail": str(e)}


# =============================================
# ENDPOINT 2: START AUDIT (ASYNC)
# =============================================
@app.post("/audit", response_model=AuditResponse)
async def start_audit(request: AuditRequest, background_tasks: BackgroundTasks):
    """
    Kicks off the full audit pipeline as a background task.
    Returns immediately with a run_id to poll status.
    """
    username = request.username.strip().lstrip("@")

    if not username:
        raise HTTPException(status_code=400, detail="Username is required")

    run_id = str(uuid.uuid4())[:8]

    # Initialize status tracker
    progress = AuditProgress(run_id, username)
    audit_status[run_id] = progress

    # Create run directory
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "charts").mkdir(exist_ok=True)

    # Save the request metadata
    meta = {
        "username": username,
        "user_context": request.user_context,
        "run_id": run_id,
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(run_dir / "request_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    # Launch pipeline in background
    background_tasks.add_task(
        run_pipeline,
        run_id=run_id,
        username=username,
        user_context=request.user_context,
    )

    return AuditResponse(
        run_id=run_id,
        status="started",
        message=f"Audit pipeline started for @{username}. Poll /audit/{run_id}/status for progress.",
    )


# =============================================
# THE ACTUAL PIPELINE (runs in background)
# =============================================
def run_pipeline(run_id: str, username: str, user_context: Optional[str] = None):
    """
    Executes the full pipeline: extract → process → analyze → outreach.
    Updates audit_status[run_id] at each stage.
    """
    progress = audit_status[run_id]
    run_dir = RUNS_DIR / run_id

    try:
        # ── Stage 1: Scrape Instagram ──
        progress.advance("scraping_instagram")
        social_data, bio_link = scrape_instagram(username)

        # ── Stage 2: Scrape Website ──
        progress.advance("scraping_website")
        web_data = scrape_website(bio_link)

        # ── Stage 3: Clean & Save Raw Payload ──
        full_payload = {"social": social_data, "website": web_data}
        optimized_payload = clean_payload(full_payload)

        raw_path = run_dir / "raw_payload.json"
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(optimized_payload, f, indent=2, ensure_ascii=False)

        # ── Stage 4: Process Metrics ──
        progress.advance("processing")
        processed = process_profile(optimized_payload)

        # Inject user context into processed data for the orchestrator
        if user_context:
            processed["user_context"] = user_context

        processed_path = run_dir / "processed_metrics.json"
        with open(processed_path, "w", encoding="utf-8") as f:
            json.dump(processed, f, indent=2, ensure_ascii=False)

        # ── Stage 5: Run Orchestrator (LangGraph) ──
        progress.advance("analyzing")

        # Import orchestrator here to avoid heavy startup imports
        from orchestrator import run_audit as run_orchestrator_audit
        result = run_orchestrator_audit(str(raw_path), run_id)

        # Orchestrator performs analysis, chart generation and outreach generation.
        # Advance progress to reflect intermediate stages listed in AuditProgress.STAGES
        try:
            progress.advance("generating_charts")
        except Exception:
            # If the stage name is missing for any reason, continue
            pass
        try:
            progress.advance("generating_outreach")
        except Exception:
            pass

        # ── Done ──
        progress.advance("complete")

    except Exception as e:
        progress.fail(str(e))
        # Save error details
        error_path = run_dir / "error.json"
        with open(error_path, "w") as f:
            json.dump({"error": str(e), "stage": progress.current_stage}, f, indent=2)


# =============================================
# ENDPOINT 3: POLL STATUS
# =============================================
@app.get("/audit/{run_id}/status")
async def get_audit_status(run_id: str):
    """
    Returns current pipeline stage and progress percentage.
    Frontend polls this every 2-3 seconds.
    """
    if run_id not in audit_status:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    return audit_status[run_id].to_dict()


# =============================================
# ENDPOINT 4: GET RESULTS
# =============================================
@app.get("/audit/{run_id}/results")
async def get_audit_results(run_id: str):
    """
    Returns the complete audit results once the pipeline is done.
    Combines processed metrics, analysis, and outreach into one response.
    """
    if run_id in audit_status and audit_status[run_id].current_stage == "failed":
        error_path = RUNS_DIR / run_id / "error.json"
        error_detail = {}
        if error_path.exists():
            with open(error_path) as f:
                error_detail = json.load(f)
        raise HTTPException(status_code=500, detail=error_detail)

    run_dir = RUNS_DIR / run_id

    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # Check if pipeline is still running
    if run_id in audit_status and audit_status[run_id].current_stage != "complete":
        return JSONResponse(
            status_code=202,
            content={
                "status": "in_progress",
                "current_stage": audit_status[run_id].current_stage,
                "message": "Pipeline is still running. Keep polling /status.",
            },
        )

    # Load all result files
    result = {}

    processed_path = run_dir / "processed_metrics.json"
    if processed_path.exists():
        with open(processed_path, encoding="utf-8") as f:
            result["processed_metrics"] = json.load(f)

    analysis_path = run_dir / "analysis.json"
    if analysis_path.exists():
        with open(analysis_path, encoding="utf-8") as f:
            result["analysis"] = json.load(f)

    outreach_path = run_dir / "outreach.txt"
    if outreach_path.exists():
        with open(outreach_path, encoding="utf-8") as f:
            result["outreach"] = f.read()

    report_path = run_dir / "report_summary.txt"
    if report_path.exists():
        with open(report_path, encoding="utf-8") as f:
            result["report"] = f.read()

    # List available charts
    charts_dir = run_dir / "charts"
    if charts_dir.exists():
        result["charts"] = [
            f"/audit/{run_id}/charts/{f.name}"
            for f in charts_dir.iterdir()
            if f.suffix == ".png"
        ]
    else:
        result["charts"] = []

    # Include run metadata
    result["run_id"] = run_id
    result["status"] = "complete"

    meta_path = run_dir / "request_meta.json"
    if meta_path.exists():
        with open(meta_path) as f:
            result["request_meta"] = json.load(f)

    return result


# =============================================
# ENDPOINT 5: CHAT (Post-Analysis Follow-Up)
# =============================================
@app.post("/audit/{run_id}/chat", response_model=ChatResponse)
async def audit_chat(run_id: str, request: ChatRequest):
    """Post-analysis conversational follow-up.
    Delegates the heavy LLM/chat logic to audit_chat.perform_audit_chat to keep
    app.py focused on routing and lightweight orchestration.
    """
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    result = await perform_audit_chat(run_dir, request.dict())
    return ChatResponse(response=result["response"], run_id=run_id)


# =============================================
# ENDPOINT 6: SERVE CHARTS
# =============================================
@app.get("/audit/{run_id}/charts/{filename}")
async def get_chart(run_id: str, filename: str):
    """Serves chart PNG images from the run directory."""
    # Sanitize filename to prevent path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    chart_path = RUNS_DIR / run_id / "charts" / filename

    if not chart_path.exists():
        raise HTTPException(status_code=404, detail=f"Chart {filename} not found")

    return FileResponse(
        path=str(chart_path),
        media_type="image/png",
        filename=filename,
    )


# =============================================
# UTILITY: LIST ALL RUNS
# =============================================
@app.get("/runs")
async def list_runs(limit: int = 20):
    """
    Lists recent audit runs. Useful for the frontend's
    'recently analyzed' section on the landing page.
    """
    runs = []

    for run_dir in sorted(RUNS_DIR.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue

        meta_path = run_dir / "request_meta.json"
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)

            # Add status if available
            run_id = run_dir.name
            status = "unknown"
            if run_id in audit_status:
                status = audit_status[run_id].current_stage

            runs.append({
                "run_id": run_id,
                "username": meta.get("username"),
                "requested_at": meta.get("requested_at"),
                "status": status,
            })

        if len(runs) >= limit:
            break

    return {"runs": runs, "total": len(runs)}


# =============================================
# HEALTH CHECK
# =============================================
@app.get("/health")
async def health():
    """Health check for deployment monitoring."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "active_runs": sum(
            1 for p in audit_status.values()
            if p.current_stage not in ("complete", "failed")
        ),
    }
