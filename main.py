"""
main.py — Full Pipeline Orchestrator
Usage: python main.py <instagram_username>

Flow:
  1. extract.py scrapes Instagram + bio link website
  2. Raw JSON saved to current_audit_data.json
  3. orchestrator.py runs processor → analyst → visualizer → outreach → generator
  4. All outputs saved to runs/{run_id}/
"""

import os
import sys
import json
import subprocess
import uuid
from dotenv import load_dotenv

load_dotenv()

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def get_data_live(username):
    """Calls extract.py and captures the JSON payload."""
    print(f"--- Phase 1: Live Data Extraction for @{username} ---")
    try:
        result = subprocess.run(
            [sys.executable, "extract.py", username],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        output = result.stdout

        if "--- Final Payload ---" in output:
            json_str = output.split("--- Final Payload ---")[1].strip()
            return json.loads(json_str)
        else:
            print("\n✖ Extraction failed. Logs:")
            print(output)
            if result.stderr:
                print("Error Details:", result.stderr)
            return None
    except Exception as e:
        print(f"Extraction execution failed: {e}")
        return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <instagram_username>")
        sys.exit(1)

    username = sys.argv[1].strip().lstrip("@")

    # Step 1: Extraction
    data = get_data_live(username)
    if not data:
        print("Pipeline aborted — extraction returned no data.")
        sys.exit(1)

    # Quick validation: check if we got real profile data
    followers = data.get("social", {}).get("followers", 0)
    posts = data.get("social", {}).get("latest_posts", [])
    print(f"\n  ✓ Extracted: {followers} followers, {len(posts)} posts")

    if followers == 0 and len(posts) == 0:
        print("  ⚠ Warning: Profile data looks empty. Username may be invalid or private.")

    # Step 2: Save raw data
    raw_path = "current_audit_data.json"
    with open(raw_path, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Raw data saved → {raw_path}")

    # Step 3: Run LangGraph analysis
    run_id = str(uuid.uuid4())[:8]  # Short ID for cleaner folder names
    print(f"\n--- Phase 2: Strategic Audit (LangGraph) [Run: {run_id}] ---")

    result = subprocess.run(
        [sys.executable, "orchestrator.py", raw_path, run_id],
        encoding='utf-8',
        errors='replace'
    )

    if result.returncode != 0:
        print(f"\n✖ Orchestrator failed with exit code {result.returncode}")
        sys.exit(result.returncode)

    print(f"\n✅ Pipeline complete for @{username}")
    print(f"   Results: runs/{run_id}/")
    print(f"   ├── report_summary.txt")
    print(f"   ├── processed_metrics.json")
    print(f"   ├── analysis.json")
    print(f"   ├── outreach.txt")
    print(f"   ├── raw_payload.json")
    print(f"   └── charts/")


if __name__ == "__main__":
    main()