# AGENTS.md - Social Media Audit Tool

## Purpose
- Short, high-signal instructions for automated agents (OpenCode sessions) and humans who need to ramp fast or modify behavior without breaking the app.

## Quick Entry Points & Commands
- Run the FastAPI backend (development): `uvicorn app:app --reload --port 8000` or `python -m uvicorn app:app --reload --port 8000`
- Run the full CLI pipeline (extract → orchestrator): `python main.py <instagram_username>`
- Run orchestrator directly (given an extracted JSON and optional run id): `python orchestrator.py <raw_payload.json> [run_id]`
- Run extractor only (requires APIFY_API_TOKEN): `python extract.py <username>`
- Test website scraping: `python web_scraper.py <url>`
- Inspect processed metrics (processor CLI): `python processor.py raw_payload.json`
- Run frontend: `cd frontend && npm run dev`

## Top Files to Read First (in order)
1. `app.py` — HTTP API + background task entrypoint. Routes are defined here.
2. `pipeline.py` — Heavy pipeline logic (extract → process → orchestrate). Keeps web layer small.
3. `orchestrator.py` — LangGraph workflow (processor → analyst → visualizer → outreach → generator). LLM heavy.
4. `processor.py` — Pure Python metrics and filters. Deterministic, test surface.
5. `extract.py` — Apify-based Instagram scraper. Token check at runtime.
6. `web_scraper.py` — Jina primary, Firecrawl fallback. Content pruning.
7. `audit_chat.py` — Post-analysis chat logic. LLM-powered.
8. `frontend/` — Next.js + TypeScript + Tailwind frontend application.

## Required Environment Variables
- `APIFY_API_TOKEN` — Required for extraction/scrape_instagram.
- `GOOGLE_API_KEY` or `GEMINI_API_KEY` — LLM calls (orchestrator and chat).
- `FIRECRAWL_API_KEY` — Optional, premium fallback for web scraping.
- `JINA_API_KEY` or `JINA_API_KEYS` — Optional, primary for web scraping.

## Architecture & Runtime Notes
- **Flow**: extract.py → processor.process_profile → orchestrator (LangGraph) → outputs to `runs/{run_id}/`
- `app.py` routes Heavy tasks delegated to `pipeline.run_pipeline` and `audit_chat.perform_audit_chat`.
- `audit_status` in app.py is in-memory only. Not shared across workers. Use Redis/DB for production.
- `orchestrator` compiles the graph on import and initializes LLM clients — avoid importing at startup without keys.
- `processor.py` is deterministic. Ideal for unit tests.

## Important Gotchas & Bugs Fixed
- **extract.py**: No longer exits at import-time when APIFY_API_TOKEN missing. Raises RuntimeError at call time instead.
- **Float Inf**: Changed `float("inf")` to `999999` in processor.py for JSON compliance (fixed ValueError: Out of range float).
- **CORS**: Added `*` and localhost:3001 to CORS allow_origins in app.py.
- **run_id**: Type casting needed in Next.js pages for dynamic routes (fixed string|string[] issue).

## Frontend Notes
- Frontend runs on port 3000 (or 3001 if 3000 in use).
- API_BASE defaults to `http://localhost:8000` for local dev.
- Tailwind CSS manually generated to `app/tailwind.css` due to config detection issues. Import in layout.tsx.
- Charts displayed with base64 encoding for better reliability.
- Theme toggle in both layout.tsx and results page.

## Recent Changes (v2)
- Added frontend with Next.js + TypeScript + Tailwind
- Added ChatWidget for follow-up questions
- Theme toggle (light/dark mode)
- Charts standardized with uniform sizing
- Fixed JSON serialization for edge cases

## Recommended Quick Improvements
1. Add Redis for status persistence (currently in-memory)
2. Add unit tests for processor.process_profile
3. Add PDF generation for report export
4. Add authentication for production deployment