# InstaConsultant - Social Media Audit Tool

AI-powered Instagram profile auditing tool for Social Media Managers (SMMs). Get actionable insights, engagement benchmarks, content analysis, and personalized outreach messages.

## Features

- **Profile Validation** - Quick Instagram username validation without using API credits
- **Engagement Analysis** - Clean engagement rates with tiered benchmarks
- **Content Strategy** - Format mix analysis, posting cadence, and content theme detection
- **Website Funnel Audit** - Scans bio link and evaluates conversion elements
- **AI Outreach Generator** - Personalized DM/email templates ready to send
- **Chat Widget** - Follow-up conversations about the audit results
- **Interactive Charts** - Visual representations of key metrics

## Tech Stack

- **Backend**: Python 3.10+, FastAPI, LangGraph, LangChain, Gemini AI
- **Scraping**: Apify (Instagram), Jina AI / Firecrawl (Website)
- **Frontend**: Next.js 14, TypeScript, Tailwind CSS

## Quick Start

### Backend (Python)

```bash
# Install dependencies
pip install -r requirements.txt

# Start the API server
python -m uvicorn app:app --reload --port 8000
```

### Frontend (Next.js)

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

The frontend will run on `http://localhost:3000` (or 3001 if 3000 is busy).

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/validate/{username}` | Quick profile validation |
| POST | `/audit` | Start full audit pipeline |
| GET | `/audit/{run_id}/status` | Poll pipeline progress |
| GET | `/audit/{run_id}/results` | Get completed results |
| POST | `/audit/{run_id}/chat` | Follow-up chat |
| GET | `/runs` | List recent audits |

## Environment Variables

Create a `.env` file in the root directory:

```
APIFY_API_TOKEN=your_apify_token
GOOGLE_API_KEY=your_google_api_key
GEMINI_API_KEY=your_gemini_key
FIRECRAWL_API_KEY=your_firecrawl_key  # optional
JINA_API_KEY=your_jina_key  # optional
```

## Architecture

```
extract.py → processor.py → orchestrator.py (LangGraph)
                    ↓
              runs/{run_id}/
              ├── processed_metrics.json
              ├── analysis.json
              ├── outreach.txt
              ├── report_summary.txt
              └── charts/
```

## Project Structure

```
SMM-tool/
├── app.py              # FastAPI backend
├── pipeline.py        # Pipeline orchestration
├── processor.py      # Metrics calculation
├── orchestrator.py    # LangGraph workflow
├── extract.py         # Instagram scraper
├── web_scraper.py     # Website scraper
├── audit_chat.py      # Post-analysis chat
├── frontend/          # Next.js frontend
│   ├── app/
│   │   ├── page.tsx           # Landing page
│   │   └── results/[run_id]/ # Results page
│   └── components/
│       ├── SearchCard.tsx
│       ├── RecentRuns.tsx
│       └── ChatWidget.tsx
├── runs/              # Audit outputs (gitignored)
└── requirements.txt
```

## License

MIT