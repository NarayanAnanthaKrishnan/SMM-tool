import os
import json
import asyncio
from pathlib import Path
from typing import Dict, Any

from fastapi import HTTPException

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage


async def perform_audit_chat(run_dir: Path, request_body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Performs the post-analysis chat logic originally in app.py.
    Expects run_dir to exist and request_body to contain 'message' and optional 'history'.
    Returns a dict: {"response": str}
    """
    processed = {}
    analysis = {}
    outreach = ""

    processed_path = run_dir / "processed_metrics.json"
    if processed_path.exists():
        with open(processed_path, encoding="utf-8") as f:
            processed = json.load(f)

    analysis_path = run_dir / "analysis.json"
    if analysis_path.exists():
        with open(analysis_path, encoding="utf-8") as f:
            analysis = json.load(f)

    outreach_path = run_dir / "outreach.txt"
    if outreach_path.exists():
        with open(outreach_path, encoding="utf-8") as f:
            outreach = f.read()

    if not processed:
        raise HTTPException(status_code=400, detail="Audit not yet complete for this run")

    # Build the grounding context (same as previous implementation)
    context = f"""
You are a social media strategist assistant. You have already completed an audit
for @{processed.get('handle', 'unknown')}. Below is the audit data.
Answer the user's question or follow their instruction using this data.
If they ask you to rewrite the outreach, use the metrics below.
Never invent numbers — only reference data from the audit.

AUDIT SUMMARY:
- Followers: {processed.get('followers', 'N/A')} ({processed.get('engagement', {}).get('follower_tier_label', 'N/A')} tier)
- Clean Engagement: {processed.get('engagement', {}).get('clean_engagement_rate_pct', 'N/A')}% ({processed.get('engagement', {}).get('benchmark_label', 'N/A')})
- Best Format: {processed.get('format_analysis', {}).get('best_performing_format', 'N/A')}
- Cadence: {processed.get('cadence', {}).get('cadence_rating', 'N/A')} (avg {processed.get('cadence', {}).get('avg_days_between_posts', 'N/A')} days)
- Website: {processed.get('website_audit', {}).get('site_type', 'N/A')} — {processed.get('website_audit', {}).get('funnel_score', 'N/A')}/10
- Missing Critical: {processed.get('website_audit', {}).get('missing_critical', [])}

ANALYSIS:
- Top Strength: {analysis.get('top_strength', 'N/A')}
- Top Weakness: {analysis.get('top_weakness', 'N/A')}
- Dominant Theme: {analysis.get('dominant_theme', 'N/A')}
- Missing Themes: {analysis.get('missing_themes', [])}
- Summary: {analysis.get('summary', 'N/A')}

CURRENT OUTREACH DRAFT:
{outreach}
"""

    GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", google_api_key=GEMINI_API_KEY)

    messages = [SystemMessage(content=context)]

    # Add conversation history
    for msg in (request_body.get("history") or []):
        if msg.get("role") == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg.get("role") == "assistant":
            messages.append(AIMessage(content=msg["content"]))

    # Add current message
    messages.append(HumanMessage(content=request_body.get("message", "")))

    # Call LLM in thread to avoid blocking
    try:
        response = await asyncio.to_thread(llm.invoke, messages)
        return {"response": response.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")
