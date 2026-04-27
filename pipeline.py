import json
from pathlib import Path
from typing import Optional

# Imports from other modules in the repo
from extract import scrape_instagram, clean_payload
from web_scraper import scrape_website
from processor import process_profile


def run_pipeline(progress, run_dir: Path, username: str, user_context: Optional[str] = None):
    """
    Executes the full pipeline: extract → process → analyze → outreach.
    This function was extracted from app.py to keep the web layer small.

    Arguments:
      - progress: AuditProgress-like object with advance(stage) and fail(error) methods
      - run_dir: Path where run artifacts are written
      - username: Instagram username
      - user_context: optional string
    """
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
        result = run_orchestrator_audit(str(raw_path), run_dir.name)

        # Orchestrator performs analysis, chart generation and outreach generation.
        # Advance progress to reflect intermediate stages listed in AuditProgress.STAGES
        try:
            progress.advance("generating_charts")
        except Exception:
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
        with open(error_path, "w", encoding="utf-8") as f:
            json.dump({"error": str(e), "stage": progress.current_stage}, f, indent=2)
