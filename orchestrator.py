"""
orchestrator.py — LangGraph Audit Pipeline
Usage: python orchestrator.py <raw_payload.json> [run_id]

Pipeline: processor → analyst → visualizer → outreach → generator
All outputs saved to runs/{run_id}/
"""

import os
import sys
import json
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for server use
import matplotlib.pyplot as plt
from typing import TypedDict, List, Optional
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from processor import process_profile

load_dotenv()

GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

# ── Output directory (set by main.py or defaults to ./output) ──
RUN_DIR = "output"


def set_run_dir(run_id: str):
    global RUN_DIR
    RUN_DIR = os.path.join("runs", run_id)
    os.makedirs(RUN_DIR, exist_ok=True)
    os.makedirs(os.path.join(RUN_DIR, "charts"), exist_ok=True)


# =============================================
# 1. STATE
# =============================================
class AgentState(TypedDict):
    raw_data: dict
    processed_data: dict
    analysis: dict
    report_config: List[dict]
    outreach_draft: Optional[str]
    errors: List[str]


# =============================================
# 2. STRUCTURED OUTPUT MODELS
# =============================================
class AnalysisResult(BaseModel):
    engagement_rate: float = Field(description="Clean engagement rate from processed data")
    engagement_status: str = Field(description="'Exceptional', 'Strong', 'Average', or 'Low'")
    content_format_gap: str = Field(description="Analysis of format mix and recommendations")
    website_friction: str = Field(description="Website funnel issues and missing elements")
    posting_consistency: str = Field(description="Assessment of posting cadence and gaps")
    top_strength: str = Field(description="The single biggest positive to lead outreach with")
    top_weakness: str = Field(description="The single biggest gap to highlight in outreach")
    summary: str = Field(description="3-4 sentence strategic audit summary")
    dominant_theme: str = Field(description="Primary content archetype: personal_narrative, case_study, educational, social_proof, promotional, engagement_bait, behind_the_scenes, or curated_value")
    missing_themes: List[str] = Field(description="Content archetypes NOT present that would strengthen their mix")
    theme_balance: str = Field(description="'diverse' (4+ types), 'moderate' (2-3), or 'narrow' (1)")


class OutreachMessage(BaseModel):
    subject_line: str = Field(description="DM opener or email subject line")
    message_body: str = Field(description="4-6 sentence personalized outreach message")
    key_data_points_used: List[str] = Field(description="List of specific metrics referenced in the message")


# Initialize Gemini
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", google_api_key=GEMINI_API_KEY)


# =============================================
# 3. NODE 0 — PROCESSOR (pure Python, no LLM)
# =============================================
def processor_node(state: AgentState):
    print("--- [Node] Processor ---")
    try:
        processed = process_profile(state["raw_data"])
        print(f"  ✓ Engagement: {processed['engagement']['clean_engagement_rate_pct']}% (clean)")
        print(f"  ✓ Cadence: {processed['cadence']['cadence_rating']}")
        print(f"  ✓ Funnel Score: {processed['website_audit'].get('funnel_score', 'N/A')}/10")
        print(f"  ✓ Site Type: {processed['website_audit'].get('site_type', 'N/A')}")
        print(f"  ✓ Content Signals: {len(processed.get('content_signals', {}).get('per_post', []))} posts analyzed")
        recency = processed['engagement']['recency_filter']
        if recency['posts_excluded'] > 0:
            print(f"  ⚠ Recency: {recency['posts_excluded']} post(s) excluded (< 24hrs old)")
        outlier = processed['engagement']['outlier_detection']
        if outlier['has_outliers']:
            print(f"  ⚠ Outliers: {outlier['outlier_count']} outlier post(s) detected")
        return {"processed_data": processed, "errors": []}
    except Exception as e:
        print(f"  ✖ Processor failed: {e}")
        return {"processed_data": {}, "errors": [f"Processor error: {str(e)}"]}


# =============================================
# 4. NODE 1 — ANALYST (LLM interprets pre-computed metrics)
# =============================================
def smart_analyst_node(state: AgentState):
    print("--- [Node] Smart Analyst ---")
    processed = state["processed_data"]

    if not processed:
        return {
            "analysis": {
                "engagement_rate": 0, "engagement_status": "Unknown",
                "content_format_gap": "Unable to analyze — processor failed",
                "website_friction": "Unable to analyze",
                "posting_consistency": "Unable to analyze",
                "top_strength": "N/A", "top_weakness": "N/A",
                "summary": "Analysis could not be completed due to data processing errors.",
                "dominant_theme": "unknown", "missing_themes": [], "theme_balance": "unknown",
            },
            "errors": state.get("errors", []) + ["Analyst skipped: no processed data"]
        }

    # Build content signals section
    content_signals = processed.get("content_signals", {})
    aggregate = content_signals.get("aggregate", {})
    per_post = content_signals.get("per_post", [])

    caption_snippets = "\n".join([
        f"  Post {i+1} [{s['type']}]: {s['caption_snippet']}"
        for i, s in enumerate(per_post)
    ])

    # Build data quality notes
    recency = processed['engagement']['recency_filter']
    outlier = processed['engagement']['outlier_detection']
    staleness = processed.get('staleness_filter', {})
    data_quality_notes = []
    if staleness.get('stale_posts_excluded', 0) > 0:
        data_quality_notes.append(f"{staleness['stale_posts_excluded']} stale post(s) excluded (> {staleness['cutoff_days']} days old)")
    if recency['posts_excluded'] > 0:
        data_quality_notes.append(f"{recency['posts_excluded']} post(s) excluded from engagement math (< 24hrs old)")
    if outlier['has_outliers']:
        data_quality_notes.append(f"{outlier['outlier_count']} outlier post(s) excluded from clean engagement rate")
    data_quality_str = " | ".join(data_quality_notes) if data_quality_notes else "All posts included, no adjustments needed."

    prompt = f"""
You are a Strategic Social Media Auditor. Below is a PRE-COMPUTED analytics report.
Your job is to INTERPRET these numbers — do NOT recalculate anything.
Use the exact numbers provided.

PROFILE: @{processed['handle']}
Bio: {processed['bio']}
Followers: {processed['followers']} | Following: {processed['following']}
Total Posts: {processed['total_posts']}

CREDIBILITY:
- Follower/Following Ratio: {processed['credibility']['follower_following_ratio']} ({processed['credibility']['ratio_signal']})

DATA QUALITY: {data_quality_str}

ENGAGEMENT (pre-calculated):
- Raw Avg Engagement Rate: {processed['engagement']['avg_engagement_rate_pct']}%
- Clean Engagement Rate: {processed['engagement']['clean_engagement_rate_pct']}% (outliers removed)
- Benchmark: "{processed['engagement']['benchmark_label']}" (based on clean rate, tier: {processed['engagement']['follower_tier_label']})
- Tier Thresholds: {processed['engagement']['tier_thresholds']}
- Posts Evaluated: {recency['posts_evaluated']} ({recency['posts_excluded']} excluded as < 24hrs old)
- Best Post: {processed['engagement']['best_post']['engagement_rate']}% engagement ({processed['engagement']['best_post']['likes']} likes, URL: {processed['engagement']['best_post']['url']})
- Worst Post: {processed['engagement']['worst_post']['engagement_rate']}% engagement ({processed['engagement']['worst_post']['likes']} likes)
- Likes-to-Comments Ratio: {processed['engagement']['likes_to_comments_ratio']}

FORMAT ANALYSIS:
{json.dumps(processed['format_analysis']['breakdown'], indent=2)}
- Best Format: {processed['format_analysis']['best_performing_format']}
- Mix: {json.dumps(processed['format_analysis']['format_mix_pct'])}

POSTING CADENCE:
- Average Gap: {processed['cadence']['avg_days_between_posts']} days — rated "{processed['cadence']['cadence_rating']}"
- Longest Gap: {processed['cadence']['longest_gap']['days']} days ({processed['cadence']['longest_gap']['from']} → {processed['cadence']['longest_gap']['to']})
- {processed['cadence']['caveat']}

CTA PATTERNS:
- Keywords Used: {processed['cta_analysis']['comment_cta_keywords']}
- Posts Without CTA: {processed['cta_analysis']['posts_without_cta']} out of {len(state['raw_data']['social']['latest_posts'])}
- Diversity: {processed['cta_analysis']['cta_diversity_rating']}

CONTENT SIGNALS (pre-extracted structural patterns):
{json.dumps(aggregate, indent=2)}

CAPTION SNIPPETS FOR THEME CLASSIFICATION:
{caption_snippets}

Based on the structural signals AND caption snippets above, classify the content
into these UNIVERSAL archetypes:
- "personal_narrative" — First-person story, origin story, journey, lesson learned
- "case_study" — Third-person success story, client/customer transformation, before/after
- "educational" — Tips, how-tos, frameworks, myths busted, listicles
- "social_proof" — Testimonials, endorsements, name-drops, "as featured in"
- "promotional" — Launch announcements, event promos, sales, urgency-driven
- "engagement_bait" — Giveaways, "tag a friend", polls, questions designed for comments
- "behind_the_scenes" — Process, workspace, team, day-in-the-life
- "curated_value" — Sharing others' content, quotes, industry news

Identify the dominant_theme, list missing_themes that would strengthen their mix,
and rate theme_balance as "diverse" (4+), "moderate" (2-3), or "narrow" (1).

WEBSITE FUNNEL AUDIT:
- Site Type: {processed['website_audit'].get('site_type', 'unknown')}
- Funnel Score: {processed['website_audit'].get('funnel_score', 'N/A')}/10
- Has Booking CTA: {processed['website_audit'].get('cta', {}).get('has_booking_cta', 'N/A')}
- Has Email Capture: {processed['website_audit'].get('cta', {}).get('has_email_capture', 'N/A')}
- Has Lead Magnet: {processed['website_audit'].get('cta', {}).get('has_download_cta', 'N/A')}
- Has Testimonials: {processed['website_audit'].get('social_proof', {}).get('has_testimonials', 'N/A')} ({processed['website_audit'].get('social_proof', {}).get('testimonial_count', 0)} found)
- Missing (Critical): {processed['website_audit'].get('missing_critical', [])}
- Missing (Nice-to-Have): {processed['website_audit'].get('missing_nice_to_have', [])}

Provide your strategic interpretation. Reference the EXACT numbers above.
Use the CLEAN engagement rate (not raw) when discussing engagement performance.
"""

    structured_llm = llm.with_structured_output(AnalysisResult)
    analysis = structured_llm.invoke([
        SystemMessage(content="You are a data-driven SMM expert. Use ONLY the pre-computed numbers given. Never invent statistics."),
        HumanMessage(content=prompt)
    ])

    return {"analysis": analysis.model_dump(), "errors": []}


# =============================================
# 5. NODE 2 — VISUALIZER (deterministic, no LLM)
# =============================================
def visualizer_node(state: AgentState):
    print("--- [Node] Visualizer ---")
    processed = state["processed_data"]
    analysis = state["analysis"]
    charts_dir = os.path.join(RUN_DIR, "charts")
    chart_files = []

    if processed:
        # ── Chart 1: Format Breakdown (Pie) ──
        fmt_breakdown = processed["format_analysis"]["breakdown"]
        if fmt_breakdown:
            plt.figure(figsize=(6, 4))
            labels = list(fmt_breakdown.keys())
            sizes = [fmt_breakdown[f]["count"] for f in labels]
            plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90)
            plt.title(f"@{processed['handle']} — Content Format Mix")
            path = os.path.join(charts_dir, "format_mix.png")
            plt.savefig(path, bbox_inches='tight')
            plt.close()
            chart_files.append(path)

        # ── Chart 2: Engagement Per Post (Bar) ──
        posts = state["raw_data"]["social"]["latest_posts"]
        recency = processed["engagement"]["recency_filter"]
        excluded_urls = {ep["url"] for ep in recency.get("excluded_posts", [])} if recency["posts_excluded"] > 0 else set()
        eval_posts = [p for p in posts if p["url"] not in excluded_urls]

        if eval_posts:
            plt.figure(figsize=(8, 4))
            labels = []
            eng_rates = []
            followers = processed["followers"]
            for p in eval_posts:
                date_str = p["timestamp"][:10] if p.get("timestamp") else "unknown"
                labels.append(date_str)
                rate = ((p["likes"] + p["comments"]) / followers * 100) if followers > 0 else 0
                eng_rates.append(round(rate, 2))

            colors = ['#2ecc71' if r > 6 else '#f39c12' if r > 3 else '#e74c3c' for r in eng_rates]
            plt.bar(labels, eng_rates, color=colors)
            clean_rate = processed["engagement"]["clean_engagement_rate_pct"]
            plt.axhline(y=clean_rate, color='blue', linestyle='--', label=f'Clean Avg: {clean_rate}%')
            plt.xlabel("Post Date")
            plt.ylabel("Engagement Rate (%)")
            plt.title(f"@{processed['handle']} — Per-Post Engagement")
            plt.legend()
            plt.xticks(rotation=45)
            plt.tight_layout()
            path = os.path.join(charts_dir, "engagement_per_post.png")
            plt.savefig(path, bbox_inches='tight')
            plt.close()
            chart_files.append(path)

        # ── Chart 3: Website Funnel Score (Horizontal Bar) ──
        website = processed.get("website_audit", {})
        if website.get("scrape_status") == "success":
            plt.figure(figsize=(7, 3))
            score = website.get("funnel_score", 0)
            max_score = website.get("funnel_score_max", 10)
            plt.barh(["Funnel Score"], [score], color='#3498db')
            plt.barh(["Funnel Score"], [max_score - score], left=[score], color='#ecf0f1')
            plt.xlim(0, max_score)
            plt.title(f"Website Funnel Score: {score}/{max_score} ({website.get('site_type', 'unknown')})")
            plt.tight_layout()
            path = os.path.join(charts_dir, "funnel_score.png")
            plt.savefig(path, bbox_inches='tight')
            plt.close()
            chart_files.append(path)

    print(f"  ✓ Generated {len(chart_files)} charts → {charts_dir}/")

    return {
        "report_config": {
            "chart_files": chart_files,
            "critique_cards": analysis.get("summary", "").split(". ")
        }
    }


# =============================================
# 6. NODE 3 — OUTREACH GENERATOR (LLM)
# =============================================
def outreach_node(state: AgentState):
    print("--- [Node] Outreach Generator ---")
    processed = state["processed_data"]
    analysis = state["analysis"]

    dominant_theme = analysis.get("dominant_theme", "unknown").replace("_", " ")
    missing_themes = analysis.get("missing_themes", [])

    prompt = f"""
You are writing a cold outreach DM to @{processed['handle']}, a {dominant_theme} creator
with {processed['followers']} followers.

THEIR METRICS (use these exact numbers):
- Clean Engagement Rate: {processed['engagement']['clean_engagement_rate_pct']}% (classified: {processed['engagement']['benchmark_label']}, tier: {processed['engagement']['follower_tier_label']})
- Best Post: {processed['engagement']['best_post']['likes']} likes, {processed['engagement']['best_post']['engagement_rate']}% engagement rate
- Posting Cadence: {processed['cadence']['cadence_rating']} (avg {processed['cadence']['avg_days_between_posts']} days between posts, longest gap: {processed['cadence']['longest_gap']['days']} days)
- Content Mix: {json.dumps(processed['format_analysis']['format_mix_pct'])}
- Best Format: {processed['format_analysis']['best_performing_format']}
- Content Balance: {analysis.get('theme_balance', 'N/A')} — missing: {missing_themes}
- Website Type: {processed['website_audit'].get('site_type', 'N/A')}
- Website Funnel Score: {processed['website_audit'].get('funnel_score', 'N/A')}/10
- Website Missing (Critical): {processed['website_audit'].get('missing_critical', [])}
- Top Strength (from audit): {analysis.get('top_strength', 'N/A')}
- Top Weakness (from audit): {analysis.get('top_weakness', 'N/A')}

RULES:
1. Open with a SPECIFIC positive about their account using an exact number.
2. Mention ONE concrete gap with the actual metric.
3. End with a soft, non-pushy CTA.
4. Keep it to 4-6 sentences total.
5. Tone: professional but warm, like a peer, not a salesperson.
6. NEVER invent numbers. Only use what's provided above.
7. Use the CLEAN engagement rate, not the raw rate.
"""

    structured_llm = llm.with_structured_output(OutreachMessage)
    outreach = structured_llm.invoke([
        SystemMessage(content="You write concise, data-driven outreach messages. Every claim must reference a real metric."),
        HumanMessage(content=prompt)
    ])

    outreach_text = f"Subject: {outreach.subject_line}\n\n{outreach.message_body}"
    print(f"  ✓ Outreach generated ({len(outreach.message_body)} chars)")
    print(f"  ✓ Data points used: {outreach.key_data_points_used}")

    return {"outreach_draft": outreach_text}


# =============================================
# 7. NODE 4 — OUTPUT GENERATOR
# =============================================
def output_generator_node(state: AgentState):
    print("--- [Node] Output Generator ---")
    analysis = state["analysis"]
    processed = state["processed_data"]
    report_config = state["report_config"]
    recency = processed['engagement']['recency_filter']
    outlier = processed['engagement']['outlier_detection']
    staleness = processed.get('staleness_filter', {})

    report_text = f"""
=====================================
 STRATEGIC AUDIT: @{processed.get('handle', 'unknown')}
=====================================

PROFILE:
  Followers: {processed['followers']} | Following: {processed['following']}
  Total Posts: {processed['total_posts']}
  Tier: {processed['engagement']['follower_tier_label']}
  Credibility: {processed['credibility']['ratio_signal']} (ratio: {processed['credibility']['follower_following_ratio']})
  Verified: {processed.get('is_verified', False)} | Business: {processed.get('is_business', False)}
  Category: {processed.get('category', 'N/A') or 'N/A'}

DATA QUALITY:
  Posts scraped: {staleness.get('total_scraped', 'N/A')} | Active used: {staleness.get('active_posts_used', 'N/A')} | Stale excluded: {staleness.get('stale_posts_excluded', 0)}
  Posts evaluated for engagement: {recency['posts_evaluated']} | Excluded (< 24hrs): {recency['posts_excluded']}
  Outliers detected: {outlier['has_outliers']} ({outlier['outlier_count']})

ENGAGEMENT: {processed['engagement']['clean_engagement_rate_pct']}% clean ({analysis['engagement_status']})
  Raw rate: {processed['engagement']['avg_engagement_rate_pct']}% | Clean rate: {processed['engagement']['clean_engagement_rate_pct']}%
  Best Post:  {processed['engagement']['best_post']['engagement_rate']}% — {processed['engagement']['best_post']['url']}
  Worst Post: {processed['engagement']['worst_post']['engagement_rate']}% — {processed['engagement']['worst_post']['url']}

FORMAT GAP:
  {analysis['content_format_gap']}

POSTING CONSISTENCY:
  {analysis.get('posting_consistency', 'N/A')}

CONTENT THEMES:
  Dominant: {analysis.get('dominant_theme', 'N/A')}
  Balance: {analysis.get('theme_balance', 'N/A')}
  Missing: {', '.join(analysis.get('missing_themes', []))}

WEBSITE FUNNEL ({processed['website_audit'].get('site_type', '?')} — {processed['website_audit'].get('funnel_score', '?')}/10):
  {analysis['website_friction']}
  Critical Missing: {', '.join(processed['website_audit'].get('missing_critical', []))}
  Nice-to-Have Missing: {', '.join(processed['website_audit'].get('missing_nice_to_have', []))}

TOP STRENGTH: {analysis.get('top_strength', 'N/A')}
TOP WEAKNESS: {analysis.get('top_weakness', 'N/A')}

SUMMARY:
  {analysis['summary']}

=====================================
 OUTREACH DRAFT
=====================================
{state.get('outreach_draft', 'No outreach generated')}

CHARTS GENERATED: {report_config.get('chart_files', [])}
"""

    # Save all outputs to RUN_DIR
    report_path = os.path.join(RUN_DIR, "report_summary.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    metrics_path = os.path.join(RUN_DIR, "processed_metrics.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(processed, f, indent=2, ensure_ascii=False)

    analysis_path = os.path.join(RUN_DIR, "analysis.json")
    with open(analysis_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)

    outreach_path = os.path.join(RUN_DIR, "outreach.txt")
    with open(outreach_path, "w", encoding="utf-8") as f:
        f.write(state.get('outreach_draft', ''))

    print(f"  ✓ Report  → {report_path}")
    print(f"  ✓ Metrics → {metrics_path}")
    print(f"  ✓ Analysis → {analysis_path}")
    print(f"  ✓ Outreach → {outreach_path}")
    return state


# =============================================
# 8. BUILD GRAPH
# =============================================
workflow = StateGraph(AgentState)

workflow.add_node("processor", processor_node)
workflow.add_node("analyst", smart_analyst_node)
workflow.add_node("visualizer", visualizer_node)
workflow.add_node("outreach", outreach_node)
workflow.add_node("generator", output_generator_node)

workflow.set_entry_point("processor")
workflow.add_edge("processor", "analyst")
workflow.add_edge("analyst", "visualizer")
workflow.add_edge("visualizer", "outreach")
workflow.add_edge("outreach", "generator")
workflow.add_edge("generator", END)

app = workflow.compile()


# =============================================
# 9. RUN
# =============================================
def run_audit(json_path: str, run_id: str = None):
    if run_id:
        set_run_dir(run_id)
    else:
        os.makedirs(RUN_DIR, exist_ok=True)

    with open(json_path, "r", encoding='utf-8') as f:
        raw_data = json.load(f)

    # Also save raw data to the run directory for reproducibility
    raw_copy_path = os.path.join(RUN_DIR, "raw_payload.json")
    with open(raw_copy_path, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, indent=2, ensure_ascii=False)

    initial_state = {
        "raw_data": raw_data,
        "processed_data": {},
        "analysis": {},
        "report_config": [],
        "outreach_draft": "",
        "errors": []
    }

    print(f"\nStarting LangGraph Workflow...")
    print(f"Pipeline: processor → analyst → visualizer → outreach → generator")
    print(f"Output: {RUN_DIR}/\n")

    result = app.invoke(initial_state)
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python orchestrator.py <raw_payload.json> [run_id]")
        sys.exit(1)

    json_path = sys.argv[1]
    run_id = sys.argv[2] if len(sys.argv) > 2 else None
    run_audit(json_path, run_id)