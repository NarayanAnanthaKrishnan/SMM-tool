import os
import sys
import json
import requests
import re
from dotenv import load_dotenv

load_dotenv()

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

FIRECRAWL_API_KEY = os.getenv('FIRECRAWL_API_KEY')
JINA_API_KEY = os.getenv('JINA_API_KEY') or os.getenv('JINA_API_KEYS')


def prune_website_content(content):
    """
    Removes noise and limits to high-signal content.
    Targets: navigation menus, country code dropdowns, footers,
    disclaimers, empty sections. Cuts at paragraph boundaries.
    """
    if not content:
        return ""

    # ── Remove repetitive navigation link blocks ──
    content = re.sub(r'(\[.*?\]\(.*?\)\s*){6,}', '\n[... Navigation Removed ...]\n', content)

    # ── Remove country code dropdowns from phone forms ──
    # Matches patterns like "* Afghanistan+93\n* Albania+355\n..."
    content = re.sub(
        r'(\*\s+[A-Z][a-z]+[\w\s()‎]*\+\d+\s*\n?){5,}',
        '\n[... Phone Country Codes Removed ...]\n',
        content
    )

    # ── Remove footer disclaimers ──
    content = re.sub(
        r'(?i)(disclaimer|©\s*\d{4}|copyright|all rights reserved|can.?spam|privacy policy|terms of service)[\s\S]{0,500}$',
        '',
        content
    )

    # ── Remove empty "As Seen with/on" sections ──
    content = re.sub(r'(?i)as seen (with|on|in):?\s*\n*', '', content)

    # ── Collapse multiple blank lines ──
    content = re.sub(r'\n{3,}', '\n\n', content)

    # ── Smart length limit — cut at paragraph boundary ──
    max_len = 3500
    if len(content) > max_len:
        # Find the last double newline before the limit
        cut_point = content.rfind('\n\n', 0, max_len)
        if cut_point > max_len * 0.6:
            content = content[:cut_point]
        else:
            content = content[:max_len]

    return content.strip()


def scrape_website(url):
    """
    Two-stage website scraper:
    1. Jina AI (Primary, Fast)
    2. Firecrawl REST API (Fallback, Premium)
    """
    if not url:
        return {"url": None, "content": "No website URL found on this profile.", "source": "no_url"}

    # --- STAGE 1: Jina AI ---
    print(f"\n[Jina AI] Scraping: {url}...")
    try:
        jina_url = f"https://r.jina.ai/{url}"
        headers = {
            "X-Return-Format": "markdown",
            "X-Retain-Images": "none",
            "X-Token-Budget": "200000"
        }
        if JINA_API_KEY:
            clean_key = JINA_API_KEY.replace("Bearer ", "").replace('"', '').replace("'", "").strip()
            headers["Authorization"] = f"Bearer {clean_key}"

        response = requests.get(jina_url, headers=headers, timeout=20)
        if response.status_code == 200 and len(response.text) > 150:
            print("✓ Jina AI scrape successful.")
            return {"url": url, "content": prune_website_content(response.text), "source": "jina"}
        else:
            print(f"! Jina AI returned status {response.status_code}")
    except Exception as e:
        print(f"! Jina AI failed: {e}")

    # --- STAGE 2: Firecrawl (Fallback) ---
    if not FIRECRAWL_API_KEY:
        return {"url": url, "content": "Jina failed and no Firecrawl key provided.", "source": "error"}

    print(f"[Firecrawl] Falling back to premium browser scrape...")
    try:
        firecrawl_url = "https://api.firecrawl.dev/v1/scrape"
        payload = {
            "url": url,
            "formats": ["markdown"],
            "onlyMainContent": True
        }
        headers = {
            "Authorization": f"Bearer {FIRECRAWL_API_KEY.strip()}",
            "Content-Type": "application/json"
        }

        response = requests.post(firecrawl_url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            content = data.get('data', {}).get('markdown') or data.get('markdown')
            if content:
                print("✓ Firecrawl fallback successful.")
                return {"url": url, "content": prune_website_content(content), "source": "firecrawl"}
        print(f"! Firecrawl failed with status {response.status_code}")
    except Exception as e:
        print(f"✖ Firecrawl Exception: {str(e)}")

    return {
        "url": url,
        "content": "Both Jina and Firecrawl failed to extract content.",
        "source": "error"
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python web_scraper.py <url>")
        sys.exit(1)

    test_url = sys.argv[1]
    result = scrape_website(test_url)
    print("\n--- Scrape Result ---")
    print(f"Source: {result['source']}")
    print(f"Length: {len(result['content'])} chars")
    print(f"Snippet:\n{result['content'][:500]}...")