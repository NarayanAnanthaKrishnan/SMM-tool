import os
import sys
import json
import re
from dotenv import load_dotenv
from apify_client import ApifyClient
from web_scraper import scrape_website

load_dotenv()

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

APIFY_API_TOKEN = os.getenv('APIFY_API_TOKEN')

# Delay creation of ApifyClient until the scraping function is invoked.
# This avoids exiting at import-time (which would crash app.py when it imports extract).
apify_client = None


def smart_truncate_caption(text, max_len=450):
    """Preserves Hook (start) and CTA (end) where conversion metrics live."""
    if not text or len(text) <= max_len:
        return text
    return text[:220] + "\n... [Middle Content Pruned] ...\n" + text[-220:]


def clean_payload(data):
    """Final pruning to optimize tokens for the LLM agent."""
    cleaned = json.loads(json.dumps(data))
    if "social" in cleaned:
        for post in cleaned["social"].get("latest_posts", []):
            post.pop("videoUrl", None)
            if post.get("caption"):
                post["caption"] = smart_truncate_caption(post["caption"])
    return cleaned


def scrape_instagram(username):
    """Handles all Instagram data extraction via Apify."""
    if not APIFY_API_TOKEN:
        raise RuntimeError("APIFY_API_TOKEN is not set. Cannot scrape Instagram.")

    # initialize client lazily so import-time doesn't require the token
    global apify_client
    if apify_client is None:
        apify_client = ApifyClient(APIFY_API_TOKEN)

    print(f"\n[Instagram] Scraping @{username}...")
    run_input = {
        "directUrls": [f"https://www.instagram.com/{username}/"],
        "resultsLimit": 12,  # ← CHANGED from 5: gives more posts to filter from
        "addParentData": True,
        "fields": [
            "shortCode", "type", "caption", "videoUrl", "videoViewCount",
            "likesCount", "commentsCount", "timestamp",
            "owner.externalUrl", "owner.followersCount", "owner.biography",
            "owner.followsCount", "owner.postsCount",
            "owner.isVerified", "owner.isBusinessAccount",
            "owner.businessCategoryName", "owner.profilePicUrl",
            "externalUrl", "followersCount", "biography", "followsCount", "postsCount",
            "isVerified", "isBusinessAccount", "categoryName", "profilePicUrl"
        ],
        "proxyConfiguration": {"useApifyProxy": True},
    }

    try:
        run = apify_client.actor("apify/instagram-scraper").call(run_input=run_input)
        raw_items = list(apify_client.dataset(run["defaultDatasetId"]).iterate_items())

        if not raw_items:
            raise Exception("Instagram scraper returned zero results.")

        first_item = raw_items[0]
        owner = first_item.get('owner', {})

        # Resilient metric mapping — check all possible paths
        followers = owner.get('followersCount') or first_item.get('followersCount') or owner.get('edge_followed_by', {}).get('count') or 0
        following = owner.get('followsCount') or first_item.get('followsCount') or owner.get('edge_follow', {}).get('count') or 0
        posts_total = owner.get('postsCount') or first_item.get('postsCount') or owner.get('edge_owner_to_timeline_media', {}).get('count') or 0

        bio_text = owner.get('biography') or first_item.get('biography') or owner.get('description', '') or ""
        bio_link = owner.get('externalUrl') or first_item.get('externalUrl') or owner.get('website')

        # Fallback: regex scan bio text for URLs
        if not bio_link and bio_text:
            found_urls = re.findall(r'(https?://[^\s]+)', bio_text)
            if found_urls:
                bio_link = found_urls[0]

        # ── NEW: Additional profile metadata ──
        is_verified = owner.get('isVerified') or first_item.get('isVerified') or False
        is_business = owner.get('isBusinessAccount') or first_item.get('isBusinessAccount') or False
        category = owner.get('businessCategoryName') or first_item.get('categoryName') or ""
        profile_pic = owner.get('profilePicUrl') or first_item.get('profilePicUrl') or ""

        social_data = {
            "username": username,
            "bio": bio_text,
            "followers": followers,
            "following": following,
            "total_posts": posts_total,
            "website_url": bio_link,
            "is_verified": is_verified,
            "is_business": is_business,
            "category": category,
            "profile_pic_url": profile_pic,
            "latest_posts": []
        }

        for item in raw_items:
            if item.get('shortCode'):
                views = item.get('videoViewCount') or item.get('videoPlayCount') or item.get('playCount') or 0
                social_data["latest_posts"].append({
                    "url": f"https://www.instagram.com/p/{item.get('shortCode')}/",
                    "type": item.get('type'),
                    "caption": item.get('caption', ''),
                    "views": views,
                    "likes": item.get('likesCount', 0),
                    "comments": item.get('commentsCount', 0),
                    "timestamp": item.get('timestamp')
                })

        social_data["latest_posts"] = sorted(
            social_data["latest_posts"],
            key=lambda x: x['timestamp'] or '',
            reverse=True
        )

        print(f"  ✓ Profile: {followers} followers, {posts_total} total posts, {len(social_data['latest_posts'])} scraped")
        if is_verified:
            print(f"  ✓ Verified account")
        if category:
            print(f"  ✓ Category: {category}")

        return social_data, bio_link

    except Exception as e:
        print(f"✖ Instagram Extraction Failed: {str(e)}")
        raise


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract.py <username>")
        sys.exit(1)

    username = sys.argv[1].strip().lstrip("@")
    try:
        social_data, bio_link = scrape_instagram(username)
        web_data = scrape_website(bio_link)

        full_payload = {"social": social_data, "website": web_data}
        optimized_payload = clean_payload(full_payload)

        print("\n--- Final Payload ---")
        print(json.dumps(optimized_payload, indent=2, ensure_ascii=False))

    except Exception as e:
        print(f"\n✖ Pipeline Error: {str(e)}")


if __name__ == "__main__":
    main()
