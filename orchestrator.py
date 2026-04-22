import os
import json
import matplotlib.pyplot as plt
from typing import TypedDict, List, Optional, Any
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv()

# Configuration
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY") # Ensure this is set in .env
if not GEMINI_API_KEY:
    # Fallback to FIRECRAWL_API_KEY if that's what's available, but usually it's GOOGLE_API_KEY
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 1. Define LangGraph State
class AgentState(TypedDict):
    raw_data: dict
    analysis: dict
    report_config: List[dict]
    outreach_draft: Optional[str]
    errors: List[str]

# 2. Define Structured Output Models
class AnalysisResult(BaseModel):
    engagement_rate: float = Field(description="Calculated engagement rate (likes + views or just likes / followers)")
    engagement_status: str = Field(description="'Good' or 'Bad' based on benchmarks")
    content_format_gap: str = Field(description="Description of format mix and if it meets Reels benchmark")
    website_friction: str = Field(description="Findings on CTA, Lead Magnets, and general UX friction")
    summary: str = Field(description="Overall strategic summary of the audit")

class ChartConfig(BaseModel):
    chart_type: str = Field(description="Type of chart, e.g., 'pie', 'bar'")
    data: List[float] = Field(description="Numerical data for the chart")
    labels: List[str] = Field(description="Labels for the data")
    title: str = Field(description="Title of the chart")

class ReportConfig(BaseModel):
    charts: List[ChartConfig] = Field(description="List of chart configurations to generate")
    critique_cards: List[str] = Field(description="List of text-based critique cards if data is thin")

# Initialize Gemini
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", google_api_key=GEMINI_API_KEY)

# 3. Implement Nodes

def smart_analyst_node(state: AgentState):
    """
    Analyzes raw data using Gemini and structured logic.
    """
    print("--- [Node] Smart Analyst ---")
    raw = state["raw_data"]
    social = raw.get("social", {})
    website = raw.get("website", {})
    
    # Pre-process some stats for the LLM
    followers = social.get("followers", 1)
    posts = social.get("latest_posts", [])
    num_posts = len(posts)
    
    total_engagement = sum([p.get("likes", 0) + p.get("views", 0) for p in posts])
    avg_engagement_rate = (total_engagement / num_posts / followers) * 100 if num_posts > 0 else 0
    
    reels_count = sum([1 for p in posts if p.get("type") == "Video"])
    reels_percentage = (reels_count / num_posts) * 100 if num_posts > 0 else 0

    prompt = f"""
    You are a Strategic SMM Auditor. Analyze the following data:
    
    INSTAGRAM DATA:
    - Followers: {followers}
    - Recent Posts Count: {num_posts}
    - Avg Engagement Rate (Calculated): {avg_engagement_rate:.2f}%
    - Reels Percentage: {reels_percentage:.2f}%
    
    WEBSITE DATA (Markdown):
    {website.get("content", "No content available")[:2000]} # Limit context
    
    BENCHMARKS:
    - < 1.0% Engagement = "Bad"
    - < 60% Reels = "Content Format Gap"
    - Missing CTA/Lead Magnet on website = "Leaky Bucket"
    
    Logic for Density:
    - If < 3 posts, recommend 'Post Critique' instead of trend charts.
    
    Return a structured analysis.
    """
    
    structured_llm = llm.with_structured_output(AnalysisResult)
    analysis = structured_llm.invoke([SystemMessage(content="You are a data-driven SMM expert."), HumanMessage(content=prompt)])
    
    return {
        "analysis": analysis.model_dump(),
        "errors": []
    }

def visualizer_node(state: AgentState):
    """
    Generates chart configurations and critique cards.
    """
    print("--- [Node] Visualizer ---")
    analysis = state["analysis"]
    raw = state["raw_data"]
    posts = raw.get("social", {}).get("latest_posts", [])
    
    prompt = f"""
    Based on this analysis: {json.dumps(analysis)}
    And these posts: {len(posts)} posts available.
    
    Generate chart configurations for Matplotlib.
    - If format gap exists, create a pie chart of Reels vs Others.
    - If engagement is high/low, create a bar chart of likes across the 5 posts.
    - If < 3 posts, focus on 'critique_cards' instead of charts.
    """
    
    structured_llm = llm.with_structured_output(ReportConfig)
    report_config = structured_llm.invoke([HumanMessage(content=prompt)])
    
    # Actually generate the charts (saving as files for now)
    chart_files = []
    os.makedirs("charts", exist_ok=True)
    for i, config in enumerate(report_config.charts):
        plt.figure(figsize=(6, 4))
        if config.chart_type == "pie":
            plt.pie(config.data, labels=config.labels, autopct='%1.1f%%')
        elif config.chart_type == "bar":
            plt.bar(config.labels, config.data)
        plt.title(config.title)
        filename = f"charts/chart_{i}.png"
        plt.savefig(filename)
        plt.close()
        chart_files.append(filename)
    
    return {
        "report_config": report_config.model_dump(),
        "outreach_draft": f"Hey! I noticed your engagement is {analysis['engagement_status']}..."
    }

def output_generator_node(state: AgentState):
    """
    Finalizes the report.
    """
    print("--- [Node] Output Generator ---")
    analysis = state["analysis"]
    report_config = state["report_config"]
    
    report_text = f"""
    STRATEGIC AUDIT SUMMARY
    =======================
    Engagement: {analysis['engagement_rate']:.2f}% ({analysis['engagement_status']})
    Format Gap: {analysis['content_format_gap']}
    Website: {analysis['website_friction']}
    
    SUMMARY:
    {analysis['summary']}
    
    CRITIQUE CARDS:
    {chr(10).join(['- ' + c for c in report_config.get('critique_cards', [])])}
    """
    
    with open("report_summary.txt", "w") as f:
        f.write(report_text)
    
    print("✓ Report generated: report_summary.txt")
    return state

# 4. Build Graph
workflow = StateGraph(AgentState)

workflow.add_node("analyst", smart_analyst_node)
workflow.add_node("visualizer", visualizer_node)
workflow.add_node("generator", output_generator_node)

workflow.set_entry_point("analyst")
workflow.add_edge("analyst", "visualizer")
workflow.add_edge("visualizer", "generator")
workflow.add_edge("generator", END)

app = workflow.compile()

def run_audit(json_path):
    with open(json_path, "r") as f:
        raw_data = json.load(f)
    
    initial_state = {
        "raw_data": raw_data,
        "analysis": {},
        "report_config": [],
        "outreach_draft": "",
        "errors": []
    }
    
    print("Starting LangGraph Workflow...")
    app.invoke(initial_state)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        run_audit(sys.argv[1])
    else:
        print("Please provide path to raw_data.json")
