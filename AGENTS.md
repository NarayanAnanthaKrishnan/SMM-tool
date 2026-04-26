Purpose
- Short, high-signal instructions for automated agents (OpenCode sessions) and humans who need to ramp fast or modify behavior without breaking the app.

Quick entrypoints & commands
- Run the FastAPI backend (development): `uvicorn app:app --reload --port 8000`
- Run the full CLI pipeline (extract → orchestrator): `python main.py <instagram_username>`
- Run orchestrator directly (given an extracted JSON and optional run id): `python orchestrator.py <raw_payload.json> [run_id]`
- Run extractor only (requires APIFY_API_TOKEN): `python extract.py <username>`
- Test website scraping: `python web_scraper.py https://example.com`
- Inspect processed metrics (processor CLI): `python processor.py raw_payload.json`

Top files to read first (in order)
- `app.py` — HTTP API + background task entrypoint and the primary place to change web-facing behavior.
- `main.py` — CLI wrapper that runs `extract.py` then `orchestrator.py`.
- `orchestrator.py` — LangGraph workflow (processor → analyst → visualizer → outreach → generator). Heavy LLM integration here.
- `processor.py` — pure-Python metrics and filters; deterministic and the ideal unit-test surface.
- `extract.py` — Apify-based Instagram scraper (contains an import-time token check; see Gotchas).
- `web_scraper.py` — Jina primary, Firecrawl fallback, content pruning logic.

Required environment variables
- APIFY_API_TOKEN — REQUIRED if you run the extraction step or call `scrape_instagram`. Warning: earlier versions exited at import-time if missing; code now checks at call-time.
- GOOGLE_API_KEY or GEMINI_API_KEY — required for LLM calls (orchestrator and /audit/{run_id}/chat).
- FIRECRAWL_API_KEY — optional; used as premium fallback by web_scraper.py.
- JINA_API_KEY (or JINA_API_KEYS) — optional; used by web_scraper.py primary path.

Non-obvious architecture & runtime notes
- Flow: `extract.py` → `processor.process_profile` → `orchestrator` (LangGraph) → outputs saved to `runs/{run_id}/`.
- `app.py` runs audits via `BackgroundTasks.add_task(run_pipeline, ...)`. `run_pipeline` imports `orchestrator` lazily to avoid heavy startup costs.
- `audit_status` in `app.py` is in-memory only; it does NOT survive restarts and is not shared across multiple uvicorn worker processes.
- `orchestrator` compiles the state graph on import and initializes LLM clients — avoid importing it in contexts without credentials.
- `processor.py` is deterministic and low-risk to change — prioritize unit tests here.

Important gotchas
- extract.py previously called `sys.exit(1)` at import if APIFY_API_TOKEN was missing. That will crash FastAPI at startup because `app.py` imports extract on module load. The codebase now avoids exit-at-import and raises a clear error when the scraping function is invoked.
- orchestrator imports/initializes LLM clients at module import; importing it without keys or dependencies may raise. app.py delays the import until the background pipeline starts — keep that pattern.
- audit progress: `AuditProgress.STAGES` lists more stages than run_pipeline originally advanced. The pipeline now advances the intermediate stages to make frontend progress meaningful.
- `audit_status` is not shared across processes — use Redis/DB if you need persistence or scaled workers.
- run_id length differs: `main.py` uses 6 chars, `app.py` uses 8 chars. Not a functional bug, but be aware if matching run directories externally.

Recommended quick improvements (already included)
1. Avoid import-time exits in libraries (done for extract.py).
2. Advance audit progress through the listed stages for better frontend UX (done in app.py).
