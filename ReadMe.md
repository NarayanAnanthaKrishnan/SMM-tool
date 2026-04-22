# InstaConsultant Pipeline - Context

## Objective
Build an agentic automation tool for Social Media Managers (SMMs) to perform instant account audits and outreach.

## Current Progress (Phase 1 Complete)
- **Environment:** Switched from Node.js to Python.
- **Scraper Engine:** Implemented `extract.py` which:
  1. Scrapes Instagram profile data & latest 5 posts using Apify.
  2. Finds the bio link and scrapes the destination website using Jina AI (Markdown mode).
  3. Uses Firecrawl as a premium fallback if Jina is blocked.
- **Goal:** The output of this script (JSON payload) must be passed to a LangGraph-based agentic workflow for Analysis and Report Generation.

## Technology Stack
- **Languages:** Python 3.10+
- **APIs:** Apify (Instagram), Jina AI (Reader), Firecrawl (Fallback Scrape), Gemini 1.5 Pro (Brain).
- **Architecture Goal:** A stateful LangGraph workflow.

# Phase 2: The Agentic Brain & Analysis

## Task Overview
Implement a LangGraph state machine that takes the JSON output from `extract.py` and performs a "Strategic Audit."

## 1. Define LangGraph State
Create a `TypedDict` or Pydantic `State` object to store:
- `raw_data`: (The JSON from Phase 1)
- `analysis`: (Structured findings: engagement, format mix, website friction)
- `report_config`: (A JSON list of which charts to generate based on data density)
- `outreach_draft`: (Optional string)

## 2. Implement the "Smart Analyst" Node (Gemini 2.5 flashlight)
This node must:
- **Calculate Benchmarks:** - < 1.0% Engagement = "Bad"
    - < 60% Reels = "Content Format Gap"
    - Missing CTA/Lead Magnet on website = "Leaky Bucket"
- **Density Logic:** - If < 3 posts, don't generate a trend chart; generate "Post Critique" cards instead.
    - If Bio Link leads to a generic homepage, flag "Conversion Friction."

## 3. Implement the "Visualizer" Node
- Generate configuration JSON for `matplotlib`. 
- Example: If the analyst flags "Format Gap," output: `{"chart_type": "pie", "data": [80, 20], "labels": ["Images", "Reels"]}`.

## 4. Dependencies to add
- `langgraph`
- `langchain-google-genai`
- `matplotlib`
- `reportlab` (for the final PDF generation)

## Definition of Done
The agent should be able to take a raw JSON file and output a `report_summary.txt` and a list of chart commands.