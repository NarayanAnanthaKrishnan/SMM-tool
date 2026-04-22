import os
import sys
import json
import subprocess
from dotenv import load_dotenv

load_dotenv()

def get_data_test():
    """
    TEST MODE: Reads from output.txt instead of calling live scrapers
    """
    print("--- [TEST MODE] Reading Data from output.txt ---")
    try:
        if not os.path.exists("output.txt"):
            print("Error: output.txt not found. Please ensure it exists for testing.")
            return None
            
        with open("output.txt", "r", encoding="utf-8") as f:
            content = f.read()
            
        # Find the JSON block within the file
        # We look for the first '{' that likely starts the social/website payload
        # after the terminal logs.
        start_index = content.find('{\n  "social":')
        if start_index == -1:
            # Fallback to any JSON start
            start_index = content.find('{')
            
        end_index = content.rfind('}') + 1
        
        if start_index != -1 and end_index != -1:
            json_str = content[start_index:end_index]
            return json.loads(json_str)
        else:
            print("Error: Could not isolate JSON payload in output.txt")
            return None
    except Exception as e:
        print(f"Failed to parse test data: {e}")
        return None

def main():
    # --- PHASE 1: DATA EXTRACTION (MOCKED) ---
    # In production, we would use:
    # username = sys.argv[1]
    # data = get_data_live(username)
    
    data = get_data_test()
    if not data:
        print("Pipeline aborted: No valid data to analyze.")
        sys.exit(1)
        
    # Save raw data for Phase 2 to consume
    raw_path = "raw_data_test.json"
    with open(raw_path, "w") as f:
        json.dump(data, f, indent=2)
    
    # --- PHASE 2: STRATEGIC AUDIT (LANGGRAPH) ---
    print(f"\n--- Phase 2: Strategic Audit (LangGraph) ---")
    # We pass the JSON file to the orchestrator
    subprocess.run([sys.executable, "orchestrator.py", raw_path])

if __name__ == "__main__":
    main()
