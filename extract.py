import os
import sys
import json
from dotenv import load_dotenv
from apify_client import ApifyClient
from firecrawl import FirecrawlApp

# Load environment variables
load_dotenv()

APIFY_API_TOKEN = os.getenv('APIFY_API_TOKEN')
FIRECRAWL_API_KEY = os.getenv('FIRECRAWL_API_KEY')

if not APIFY_API_TOKEN or not FIRECRAWL_API_KEY:
    print("Missing APIFY_API_TOKEN or FIRECRAWL_API_KEY in .env file")
    sys.exit(1)

# Initialize clients
apify_client = ApifyClient(APIFY_API_TOKEN)
firecrawl_app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)

def scrape_instagram(username):
    """
    Scrapes Instagram profile and latest posts using Apify
    """
    print(f"\n[Instagram] Scraping @{username}...")
    
    run_input = {
        "directUrls": [f"https://www.instagram.com/{username}/"],
        "resultsLimit": 5,
        "addParentData": True,
        "fields": [
            "shortCode", "type", "caption", "videoUrl", 
            "videoViewCount", "likesCount", "owner.followersCount", "owner.externalUrl"
        ],
        "proxyConfiguration": {"useApifyProxy": True},
    }

    # Run the actor and wait for it to finish
    run = apify_client.actor("apify/instagram-scraper").call(run_input=run_input)

    # Fetch results
    items = list(apify_client.dataset(run["defaultDatasetId"]).iterate_items())

    if not items:
        raise Exception("No Instagram data found.")

    first_item = items[0]
    owner = first_item.get('owner', {})
    bio_link = owner.get('externalUrl') or first_item.get('externalUrl')

    social_data = {
        "username": username,
        "followers": owner.get('followersCount', 0),
        "latest_posts": [
            {
                "url": f"https://www.instagram.com/p/{item.get('shortCode')}/",
                "type": item.get('type'),
                "videoUrl": item.get('videoUrl'),
                "caption": item.get('caption', ''),
                "views": item.get('videoViewCount', 0),
                "likes": item.get('likesCount', 0)
            } for item in items
        ]
    }

    return social_data, bio_link

def scrape_website(url):
    """
    Scrapes a website and returns Markdown using Firecrawl
    """
    if not url:
        return {"url": None, "content": "No URL provided"}
    
    print(f"\n[Firecrawl] Scraping {url}...")
    try:
        # Firecrawl v1 Python SDK method
        scrape_result = firecrawl_app.scrape_url(url, params={'formats': ['markdown']})
        
        # Firecrawl returns a dict or object depending on version
        # Usually: {'success': True, 'markdown': '...'} or data nested
        if isinstance(scrape_result, dict):
            return {
                "url": url,
                "content": scrape_result.get('markdown') or scrape_result.get('data', {}).get('markdown') or "Empty content"
            }
        else:
            # If it returns an object
            return {
                "url": url,
                "content": getattr(scrape_result, 'markdown', None) or "Empty content"
            }
            
    except Exception as e:
        return {"url": url, "content": f"Firecrawl Exception: {str(e)}"}

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python extract.py <username>      # Full extraction")
        print("  python extract.py <url>           # Website only (test Firecrawl)")
        sys.exit(1)

    target = sys.argv[1]

    try:
        result = {}

        if target.startswith('http'):
            # MODE: Website Only
            web_data = scrape_website(target)
            result = {"website": web_data}
        else:
            # MODE: Full Extraction
            social_data, bio_link = scrape_instagram(target)
            web_data = scrape_website(bio_link)
            
            result = {
                "social": social_data,
                "website": web_data
            }

        print("\n--- Final Payload ---")
        print(json.dumps(result, indent=2))

    except Exception as e:
        print(f"\n✖ Pipeline Failed: {str(e)}")

if __name__ == "__main__":
    main()
