"""
processor.py — Final Version (with staleness filter)
Takes raw scraped JSON → outputs analysis-ready metrics JSON.
NO LLM calls. Pure Python math and string parsing.

Includes:
  - Staleness filter (excludes posts older than 6 months, keeps min 3)
  - Recency filter (excludes posts < 24hrs old)
  - IQR-based outlier detection
  - Tiered engagement benchmarks by follower count
  - Niche-agnostic content signals
  - Site type classification + context-aware funnel scoring
  - Testimonial name false positive filtering
  - Broader educational signal detection
"""

import json
import re
from datetime import datetime, timezone, timedelta
from collections import Counter


# ── Constants ──
RECENCY_THRESHOLD_HOURS = 24
STALENESS_THRESHOLD_DAYS = 180  # 6 months


def process_profile(raw_data: dict) -> dict:
    social = raw_data["social"]
    website = raw_data["website"]
    all_posts = social["latest_posts"]

    # ── Step 0: Filter stale posts ──
    staleness = filter_stale_posts(all_posts, STALENESS_THRESHOLD_DAYS)
    active_posts = staleness["active_posts"]

    result = {
        "handle": social["username"],
        "bio": social.get("bio", ""),
        "followers": social["followers"],
        "following": social["following"],
        "total_posts": social["total_posts"],

        # ── New profile metadata ──
        "is_verified": social.get("is_verified", False),
        "is_business": social.get("is_business", False),
        "category": social.get("category", ""),
        "profile_pic_url": social.get("profile_pic_url", ""),

        "credibility": compute_credibility(social),
        "engagement": compute_engagement(active_posts, social["followers"]),
        "format_analysis": compute_format_breakdown(active_posts),
        "cadence": compute_cadence(active_posts, social["total_posts"]),
        "cta_analysis": extract_cta_patterns(active_posts),
        "content_signals": extract_content_signals(active_posts),
        "website_audit": audit_website(website, social.get("bio", "")),

        # ── Staleness metadata ──
        "staleness_filter": {
            "total_scraped": len(all_posts),
            "active_posts_used": len(active_posts),
            "stale_posts_excluded": staleness["stale_count"],
            "cutoff_days": staleness["cutoff_days"],
            "stale_post_urls": [p["url"] for p in staleness["stale_posts"]],
        },
    }

    return result


# =============================================
# STALENESS FILTER
# =============================================
def filter_stale_posts(posts: list, max_age_days: int = STALENESS_THRESHOLD_DAYS, min_posts: int = 3) -> dict:
    """
    Separates posts into recent (usable for analysis) and stale (too old).
    Always keeps at least min_posts even if all are old — falls back to newest.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max_age_days)

    recent = []
    stale = []

    for p in posts:
        try:
            post_time = datetime.fromisoformat(p["timestamp"].replace("Z", "+00:00"))
            if post_time >= cutoff:
                recent.append(p)
            else:
                stale.append(p)
        except (ValueError, TypeError, KeyError):
            recent.append(p)  # If no timestamp, include it

    # Fallback: if too few recent posts, pull newest stale ones back in
    if len(recent) < min_posts and stale:
        stale_sorted = sorted(stale, key=lambda x: x.get("timestamp", ""), reverse=True)
        needed = min_posts - len(recent)
        recent.extend(stale_sorted[:needed])
        stale = stale_sorted[needed:]

    return {
        "active_posts": recent,
        "stale_posts": stale,
        "stale_count": len(stale),
        "cutoff_days": max_age_days,
    }


# =============================================
# SECTION 1: Credibility Signals
# =============================================
def compute_credibility(social: dict) -> dict:
    followers = social["followers"]
    following = social["following"]

    ratio = round(followers / following, 2) if following > 0 else 999999

    if ratio > 2.0:
        ratio_signal = "strong"
    elif ratio >= 1.0:
        ratio_signal = "moderate"
    else:
        ratio_signal = "weak_follow_for_follow"

    return {
        "follower_following_ratio": ratio,
        "ratio_signal": ratio_signal,
        "posts_per_follower": round(social["total_posts"] / followers, 2) if followers > 0 else 0,
    }


# =============================================
# SECTION 2: Engagement (Tiered + Recency + Outlier)
# =============================================
def get_follower_tier(followers: int) -> dict:
    if followers >= 1_000_000:
        return {"tier": "mega", "label": "1M+", "thresholds": {"exceptional": 1.0, "strong": 0.5, "average": 0.2}}
    elif followers >= 100_000:
        return {"tier": "macro", "label": "100K-1M", "thresholds": {"exceptional": 2.5, "strong": 1.5, "average": 0.5}}
    elif followers >= 10_000:
        return {"tier": "mid", "label": "10K-100K", "thresholds": {"exceptional": 5.0, "strong": 3.0, "average": 1.0}}
    elif followers >= 1_000:
        return {"tier": "micro", "label": "1K-10K", "thresholds": {"exceptional": 8.0, "strong": 5.0, "average": 2.0}}
    else:
        return {"tier": "nano", "label": "<1K", "thresholds": {"exceptional": 12.0, "strong": 8.0, "average": 4.0}}


def classify_engagement(rate: float, followers: int) -> str:
    tier = get_follower_tier(followers)
    t = tier["thresholds"]
    if rate >= t["exceptional"]:
        return "exceptional"
    elif rate >= t["strong"]:
        return "strong"
    elif rate >= t["average"]:
        return "average"
    return "low"


def detect_outliers(values: list) -> dict:
    if len(values) < 3:
        return {"has_outliers": False, "outlier_values": [], "clean_values": values}

    sorted_vals = sorted(values)
    n = len(sorted_vals)
    q1 = sorted_vals[n // 4]
    q3 = sorted_vals[(3 * n) // 4]
    iqr = q3 - q1

    lower_bound = q1 - 3 * iqr
    upper_bound = q3 + 3 * iqr

    outliers = [v for v in values if v < lower_bound or v > upper_bound]
    clean = [v for v in values if lower_bound <= v <= upper_bound]

    return {
        "has_outliers": len(outliers) > 0,
        "outlier_values": outliers,
        "clean_values": clean,
        "bounds": {"lower": round(lower_bound, 2), "upper": round(upper_bound, 2)},
    }


def compute_engagement(posts: list, followers: int) -> dict:
    now = datetime.now(timezone.utc)

    # ── Step 1: Recency filter ──
    evaluable_posts = []
    too_recent_posts = []

    for p in posts:
        try:
            post_time = datetime.fromisoformat(p["timestamp"].replace("Z", "+00:00"))
            age_hours = (now - post_time).total_seconds() / 3600

            if age_hours < RECENCY_THRESHOLD_HOURS:
                too_recent_posts.append({
                    "url": p["url"],
                    "age_hours": round(age_hours, 1),
                    "likes": p["likes"],
                    "comments": p["comments"],
                })
            else:
                evaluable_posts.append(p)
        except (ValueError, TypeError, KeyError):
            evaluable_posts.append(p)

    used_all_fallback = len(evaluable_posts) == 0
    if used_all_fallback:
        evaluable_posts = posts
        too_recent_posts = []

    # ── Step 2: Compute on evaluable posts ──
    total_likes = sum(p["likes"] for p in evaluable_posts)
    total_comments = sum(p["comments"] for p in evaluable_posts)
    total_interactions = total_likes + total_comments
    num_posts = len(evaluable_posts)

    avg_engagement_rate = round(
        total_interactions / (num_posts * followers) * 100, 2
    ) if followers > 0 and num_posts > 0 else 0

    per_post = []
    for p in evaluable_posts:
        rate = round((p["likes"] + p["comments"]) / followers * 100, 2) if followers > 0 else 0
        per_post.append({
            "url": p["url"],
            "engagement_rate": rate,
            "likes": p["likes"],
            "comments": p["comments"],
        })

    per_post_sorted = sorted(per_post, key=lambda x: x["engagement_rate"], reverse=True)

    # ── Step 3: Outlier detection ──
    rates = [pp["engagement_rate"] for pp in per_post]
    outlier_info = detect_outliers(rates)

    if outlier_info["has_outliers"] and len(outlier_info["clean_values"]) > 0:
        clean_avg = round(sum(outlier_info["clean_values"]) / len(outlier_info["clean_values"]), 2)
    else:
        clean_avg = avg_engagement_rate

    # ── Step 4: Tiered benchmarking on clean rate ──
    tier_info = get_follower_tier(followers)
    benchmark = classify_engagement(clean_avg, followers)

    return {
        "avg_engagement_rate_pct": avg_engagement_rate,
        "clean_engagement_rate_pct": clean_avg,
        "benchmark_label": benchmark,
        "follower_tier": tier_info["tier"],
        "follower_tier_label": tier_info["label"],
        "tier_thresholds": tier_info["thresholds"],
        "total_likes": total_likes,
        "total_comments": total_comments,
        "best_post": per_post_sorted[0] if per_post_sorted else None,
        "worst_post": per_post_sorted[-1] if per_post_sorted else None,
        "likes_to_comments_ratio": round(total_likes / total_comments, 2) if total_comments > 0 else 999999,
        "outlier_detection": {
            "has_outliers": outlier_info["has_outliers"],
            "outlier_count": len(outlier_info["outlier_values"]),
            "method": "iqr",
            "note": "clean_engagement_rate_pct excludes outlier posts"
                    if outlier_info["has_outliers"] else "no outliers detected",
        },
        "recency_filter": {
            "threshold_hours": RECENCY_THRESHOLD_HOURS,
            "posts_excluded": len(too_recent_posts),
            "posts_evaluated": len(evaluable_posts),
            "excluded_posts": too_recent_posts,
            "used_all_fallback": used_all_fallback,
        },
    }


# =============================================
# SECTION 3: Format Breakdown
# =============================================
def compute_format_breakdown(posts: list) -> dict:
    formats = {}
    for p in posts:
        fmt = p["type"]
        if fmt not in formats:
            formats[fmt] = {"count": 0, "total_likes": 0, "total_comments": 0, "total_views": 0}

        formats[fmt]["count"] += 1
        formats[fmt]["total_likes"] += p["likes"]
        formats[fmt]["total_comments"] += p["comments"]
        formats[fmt]["total_views"] += p.get("views", 0)

    breakdown = {}
    for fmt, data in formats.items():
        n = data["count"]
        breakdown[fmt] = {
            "count": n,
            "avg_likes": round(data["total_likes"] / n, 1),
            "avg_comments": round(data["total_comments"] / n, 1),
            "avg_views": round(data["total_views"] / n, 1),
            "total_engagement": data["total_likes"] + data["total_comments"],
        }

    best_format = max(
        breakdown.items(),
        key=lambda x: x[1]["avg_likes"] + x[1]["avg_comments"],
        default=(None, None)
    )

    return {
        "breakdown": breakdown,
        "best_performing_format": best_format[0],
        "format_mix_pct": {
            fmt: round(data["count"] / len(posts) * 100, 1)
            for fmt, data in breakdown.items()
        } if posts else {}
    }


# =============================================
# SECTION 4: Posting Cadence
# =============================================
def compute_cadence(posts: list, total_posts: int) -> dict:
    if len(posts) < 2:
        return {"avg_days_between_posts": None, "gaps": [], "cadence_rating": "insufficient_data"}

    dates = sorted([
        datetime.fromisoformat(p["timestamp"].replace("Z", "+00:00"))
        for p in posts if p.get("timestamp")
    ])

    if len(dates) < 2:
        return {"avg_days_between_posts": None, "gaps": [], "cadence_rating": "insufficient_data"}

    gaps = []
    for i in range(1, len(dates)):
        gap_days = (dates[i] - dates[i - 1]).days
        gaps.append({
            "from": dates[i - 1].strftime("%Y-%m-%d"),
            "to": dates[i].strftime("%Y-%m-%d"),
            "days": gap_days
        })

    avg_gap = round(sum(g["days"] for g in gaps) / len(gaps), 1)
    max_gap = max(gaps, key=lambda g: g["days"])
    min_gap = min(gaps, key=lambda g: g["days"])
    total_span_days = (dates[-1] - dates[0]).days

    if avg_gap <= 7:
        rating = "consistent"
    elif avg_gap <= 30:
        rating = "moderate"
    else:
        rating = "inconsistent"

    return {
        "avg_days_between_posts": avg_gap,
        "longest_gap": max_gap,
        "shortest_gap": min_gap,
        "total_span_days": total_span_days,
        "posts_in_span": len(posts),
        "cadence_rating": rating,
        "caveat": f"Based on {len(posts)} most recent active posts. Profile has {total_posts} total posts."
    }


# =============================================
# SECTION 5: CTA Pattern Analysis
# =============================================
def extract_cta_patterns(posts: list) -> dict:
    comment_ctas = []
    link_ctas = 0
    dm_ctas = 0

    comment_pattern = re.compile(
        r'[Cc]omment\s*["\u201c\u201d\']?(\w+)["\u201c\u201d\']?',
        re.IGNORECASE
    )

    for p in posts:
        caption = p.get("caption", "")

        matches = comment_pattern.findall(caption)
        for m in matches:
            comment_ctas.append(m.upper())

        if re.search(r'link\s*(in\s*)?bio|click.*link|tap.*link', caption, re.IGNORECASE):
            link_ctas += 1

        if re.search(r'\bDM\b|direct\s*message|send.*message', caption, re.IGNORECASE):
            dm_ctas += 1

    return {
        "comment_cta_keywords": list(set(comment_ctas)),
        "comment_cta_count": len(comment_ctas),
        "unique_ctas": len(set(comment_ctas)),
        "link_in_bio_ctas": link_ctas,
        "dm_ctas": dm_ctas,
        "posts_without_cta": sum(
            1 for p in posts
            if not comment_pattern.search(p.get("caption", ""))
        ),
        "cta_diversity_rating": "varied" if len(set(comment_ctas)) >= 3 else "repetitive" if len(set(comment_ctas)) >= 1 else "none",
    }


# =============================================
# SECTION 6: Content Signals (niche-agnostic)
# =============================================
EDUCATIONAL_PATTERN = re.compile(
    r'('
    r'how to'
    r'|here\'?s (the|a|how|what|why)'
    r'|step[s]?\s*\d'
    r'|\d\s*(tip[s]?|way[s]?|mistake[s]?|thing[s]?|reason[s]?|sign[s]?|hack[s]?|rule[s]?|secret[s]?|lesson[s]?)'
    r'|the truth about'
    r'|myth|misconception'
    r'|stop (doing|making|using)'
    r'|you\'?re (doing|making|getting).*wrong'
    r'|most people (don\'?t|ignore|forget|miss)'
    r'|this is (why|how|what)'
    r'|instead of'
    r'|cheat code|cheatcode|playbook'
    r'|fix (them|this|it|your)'
    r'|you need|you should|you must'
    r'|the (secret|key|trick|hack) (to|is)'
    r'|\bguide\b|\btutorial\b'
    r')',
    re.IGNORECASE
)


def extract_content_signals(posts: list) -> dict:
    signals_per_post = []

    for p in posts:
        caption = p.get("caption", "")
        caption_lower = caption.lower()

        signals = {
            "url": p.get("url", ""),
            "type": p.get("type", ""),
            "timestamp": p.get("timestamp", ""),
            "caption_length": len(caption),
            "line_count": caption.count("\n") + 1,
            "word_count": len(caption.split()),
            "has_question": bool(re.search(r'\?', caption)),
            "has_cta_comment": bool(re.search(r'comment\s*["\u201c\u201d\']?\w+', caption_lower)),
            "has_cta_dm": bool(re.search(r'\bDM\b|direct.?message|send.*message', caption, re.IGNORECASE)),
            "has_cta_link": bool(re.search(r'link.?in.?bio|click.*link|tap.*link', caption_lower)),
            "has_cta_save": bool(re.search(r'\bsave\b.*later|\bsave\b.*this', caption_lower)),
            "has_cta_share": bool(re.search(r'\bshare\b.*with|\btag\b.*friend|\btag\b.*someone', caption_lower)),
            "has_list_format": bool(re.search(r'(?:^|\n)\s*[\u2022•\-\d]+[\.\)]\s', caption)),
            "has_emoji_heavy": len(re.findall(r'[\U0001f300-\U0001f9ff\u2600-\u26ff\u2700-\u27bf]', caption)) > 5,
            "has_hashtags": bool(re.search(r'#\w+', caption)),
            "hashtag_count": len(re.findall(r'#\w+', caption)),
            "has_mentions": bool(re.search(r'@\w+', caption)),
            "mention_count": len(re.findall(r'@\w+', caption)),
            "has_first_person_story": bool(re.search(r'\b(I was|my journey|I went|I learned|I struggled|I started|I built|I made|I lost)\b', caption, re.IGNORECASE)),
            "has_third_person_story": bool(re.search(r'\b(he was|she was|they went|here\'?s how .+ (made|did|built|grew|earned))\b', caption, re.IGNORECASE)),
            "has_number_claims": bool(re.search(r'(\d+[%xX]|\$[\d,]+|₹[\d,]+|\d+[kKmM]\b|\d+\s*(followers|clients|leads|users|subscribers|customers|downloads|sales|revenue))', caption, re.IGNORECASE)),
            "has_before_after": bool(re.search(r'before.*after|went from.*to|used to.*now', caption_lower)),
            "has_urgency": bool(re.search(r'limited|last chance|only \d|spots left|closing|deadline|ends', caption_lower)),
            "has_social_proof": bool(re.search(r'trusted by|as seen|featured|client.*(said|result)|testimonial', caption_lower)),
            "has_giveaway": bool(re.search(r'giveaway|giving away|free.*download|free.*guide|free.*template', caption_lower)),
            "has_educational_markers": bool(EDUCATIONAL_PATTERN.search(caption)),
            "caption_snippet": (caption[:150] + " ... " + caption[-100:]).strip() if len(caption) > 250 else caption,
        }

        signals_per_post.append(signals)

    n = len(signals_per_post)
    if n == 0:
        return {"per_post": [], "aggregate": {}}

    aggregate = {
        "avg_caption_length": round(sum(s["caption_length"] for s in signals_per_post) / n, 0),
        "avg_word_count": round(sum(s["word_count"] for s in signals_per_post) / n, 0),
        "posts_with_question": sum(1 for s in signals_per_post if s["has_question"]),
        "posts_with_comment_cta": sum(1 for s in signals_per_post if s["has_cta_comment"]),
        "posts_with_hashtags": sum(1 for s in signals_per_post if s["has_hashtags"]),
        "avg_hashtags": round(sum(s["hashtag_count"] for s in signals_per_post) / n, 1),
        "posts_with_mentions": sum(1 for s in signals_per_post if s["has_mentions"]),
        "posts_with_first_person_story": sum(1 for s in signals_per_post if s["has_first_person_story"]),
        "posts_with_third_person_story": sum(1 for s in signals_per_post if s["has_third_person_story"]),
        "posts_with_number_claims": sum(1 for s in signals_per_post if s["has_number_claims"]),
        "posts_with_before_after": sum(1 for s in signals_per_post if s["has_before_after"]),
        "posts_with_educational_markers": sum(1 for s in signals_per_post if s["has_educational_markers"]),
        "posts_with_urgency": sum(1 for s in signals_per_post if s["has_urgency"]),
        "posts_with_social_proof": sum(1 for s in signals_per_post if s["has_social_proof"]),
        "posts_with_giveaway": sum(1 for s in signals_per_post if s["has_giveaway"]),
    }

    return {"per_post": signals_per_post, "aggregate": aggregate}


# =============================================
# SECTION 7: Website / Funnel Audit (site-type-aware)
# =============================================
def classify_site_type(content: str, bio: str) -> str:
    combined = (content + " " + bio).lower()

    if any(kw in combined for kw in ['book a call', 'book your call', 'schedule a call', 'strategy call',
                                      'consultation', 'book slot', 'book a demo', 'discovery call']):
        return "service_business"
    if any(kw in combined for kw in ['add to cart', 'buy now', 'shop now', 'checkout', 'add to bag',
                                      'our products', 'shop the', 'store', 'merch']):
        return "ecommerce"
    if any(kw in combined for kw in ['subscribe', 'newsletter', 'blog', 'article', 'read more',
                                      'latest news', 'trending', 'editorial', 'magazine']):
        return "media_content"
    if any(kw in combined for kw in ['download', 'free guide', 'free ebook', 'free template',
                                      'lead magnet', 'get your free', 'grab your', 'opt in']):
        return "lead_gen"
    if any(kw in combined for kw in ['linktree', 'linktr.ee', 'lnk.bio', 'bio.link',
                                      'link in bio', 'all my links', 'connect with me']):
        return "link_aggregator"
    return "informational"


SITE_SCORING_RULES = {
    "service_business": {
        "scoring": [("has_booking_cta", 2.0), ("has_testimonials", 1.5), ("has_specific_numbers", 1.5), ("has_urgency", 1.0), ("has_email_capture", 1.0), ("has_faq", 1.0), ("has_guarantee", 1.0), ("has_pricing", 1.0)],
        "critical_missing": {"has_booking_cta": "no_booking_cta", "has_email_capture": "no_email_capture", "has_testimonials": "no_testimonials"},
        "nice_to_have_missing": {"has_download_cta": "no_lead_magnet", "has_guarantee": "no_guarantee", "has_pricing": "no_pricing_transparency"},
    },
    "ecommerce": {
        "scoring": [("has_pricing", 2.0), ("has_specific_numbers", 1.5), ("has_testimonials", 1.5), ("has_urgency", 1.0), ("has_guarantee", 1.5), ("has_email_capture", 1.0), ("has_faq", 0.5), ("has_booking_cta", 0.5)],
        "critical_missing": {"has_pricing": "no_pricing", "has_guarantee": "no_guarantee_or_returns_policy"},
        "nice_to_have_missing": {"has_email_capture": "no_email_capture", "has_testimonials": "no_reviews_or_testimonials", "has_faq": "no_faq"},
    },
    "lead_gen": {
        "scoring": [("has_download_cta", 2.0), ("has_email_capture", 2.0), ("has_testimonials", 1.5), ("has_specific_numbers", 1.0), ("has_urgency", 1.0), ("has_faq", 1.0), ("has_guarantee", 0.5), ("has_pricing", 0.0)],
        "critical_missing": {"has_email_capture": "no_email_capture", "has_download_cta": "no_lead_magnet"},
        "nice_to_have_missing": {"has_testimonials": "no_social_proof", "has_urgency": "no_urgency"},
    },
    "media_content": {
        "scoring": [("has_email_capture", 2.5), ("has_download_cta", 1.5), ("has_specific_numbers", 1.0), ("has_faq", 0.5), ("has_testimonials", 0.5), ("has_urgency", 0.0), ("has_guarantee", 0.0), ("has_pricing", 0.0)],
        "critical_missing": {"has_email_capture": "no_email_or_subscribe"},
        "nice_to_have_missing": {"has_download_cta": "no_content_offers"},
    },
    "link_aggregator": {
        "scoring": [("has_email_capture", 2.0), ("has_download_cta", 2.0), ("has_booking_cta", 2.0), ("has_specific_numbers", 1.0), ("has_testimonials", 1.0), ("has_urgency", 0.5), ("has_faq", 0.0), ("has_guarantee", 0.0), ("has_pricing", 0.0)],
        "critical_missing": {},
        "nice_to_have_missing": {"has_email_capture": "no_email_capture"},
    },
    "informational": {
        "scoring": [("has_booking_cta", 1.5), ("has_download_cta", 1.5), ("has_email_capture", 1.5), ("has_testimonials", 1.5), ("has_specific_numbers", 1.0), ("has_urgency", 0.5), ("has_faq", 0.5), ("has_guarantee", 0.5), ("has_pricing", 0.5)],
        "critical_missing": {},
        "nice_to_have_missing": {"has_email_capture": "no_email_capture", "has_download_cta": "no_lead_magnet"},
    },
}


def extract_testimonial_names(content: str) -> list:
    raw_names = re.findall(r'##\s*([A-Z][a-z]+ [A-Z][a-z]+)', content)

    heading_stopwords = {
        "Free Strategy", "Book Your", "Will You", "Meet Your", "Still Not",
        "Get Top", "Get Started", "Get Your", "Learn More", "Read More",
        "See What", "See How", "Find Out", "Sign Up", "Join Now",
        "Join Our", "Start Your", "Try Our", "Watch Now", "Live Sessions",
        "Live Resume", "Live Session", "Focus Session", "Monthly Office",
        "Industry Speaker", "The Ultimate",
    }

    common_words = {
        "Free", "Live", "Get", "Our", "Your", "The", "New", "Top", "Best",
        "How", "Why", "What", "See", "Try", "All", "Any", "Big", "Start",
        "Join", "Find", "Read", "More", "Full", "Easy", "Fast", "Quick",
        "Next", "Last", "Most", "Real", "True", "High", "Low", "Open",
        "Session", "Sessions", "Focus", "Monthly", "Weekly", "Daily",
        "Ultimate", "Complete", "Total", "Special", "Premium", "Industry",
        "Office", "Speaker", "Resume", "Immigration", "Career",
    }

    filtered = []
    for name in raw_names:
        if name in heading_stopwords:
            continue
        words = name.split()
        if all(w in common_words for w in words):
            continue
        if re.search(r'\d', name):
            continue
        filtered.append(name)

    return filtered


def audit_website(website: dict, bio: str = "") -> dict:
    content = website.get("content", "")
    url = website.get("url", "")
    source = website.get("source", "unknown")

    if not content or "failed" in content.lower() or "exception" in content.lower():
        return {"scrape_status": "failed", "scrape_source": source, "url": url}

    content_lower = content.lower()
    site_type = classify_site_type(content, bio)

    detections = {
        "has_booking_cta": bool(re.search(r'book.*call|schedule.*call|book.*slot|book.*now|book.*demo', content_lower)),
        "has_download_cta": bool(re.search(r'download|free.*guide|free.*ebook|lead.*magnet|get.*free', content_lower)),
        "has_email_capture": bool(re.search(r'email|subscribe|newsletter|opt.?in', content_lower)),
        "has_phone_capture": bool(re.search(r'phone|mobile|whatsapp|call.*number', content_lower)),
        "has_testimonials": False,
        "has_specific_numbers": bool(re.search(r'₹[\d,]+|\$[\d,]+|(?:\d+[%xX])', content)),
        "has_urgency": bool(re.search(r'limited|before.*fill|only.*left|hurry|last.*chance|slots', content_lower)),
        "has_faq": bool(re.search(r'faq|frequently asked', content_lower)),
        "has_guarantee": bool(re.search(r'guarantee|money.?back|refund|risk.?free', content_lower)),
        "has_pricing": bool(re.search(r'(?:price|cost|invest|pay|pricing)\s*[:=]?\s*[₹$]?\d', content_lower)),
    }

    testimonial_names = extract_testimonial_names(content)
    detections["has_testimonials"] = len(testimonial_names) > 0

    rules = SITE_SCORING_RULES.get(site_type, SITE_SCORING_RULES["informational"])

    score = 0
    max_possible = 0
    for signal_key, weight in rules["scoring"]:
        max_possible += weight
        if detections.get(signal_key, False):
            score += weight

    normalized_score = round((score / max_possible) * 10, 1) if max_possible > 0 else 0

    missing_critical = [label for signal_key, label in rules.get("critical_missing", {}).items() if not detections.get(signal_key, False)]
    missing_nice = [label for signal_key, label in rules.get("nice_to_have_missing", {}).items() if not detections.get(signal_key, False)]

    return {
        "scrape_status": "success",
        "scrape_source": source,
        "url": url,
        "site_type": site_type,
        "cta": {k: v for k, v in detections.items() if k.startswith("has_") and k in ["has_booking_cta", "has_download_cta", "has_email_capture", "has_phone_capture"]},
        "social_proof": {
            "has_testimonials": detections["has_testimonials"],
            "testimonial_count": len(testimonial_names),
            "testimonial_names": testimonial_names,
            "has_specific_numbers": detections["has_specific_numbers"],
        },
        "trust_signals": {
            "has_urgency": detections["has_urgency"],
            "has_faq": detections["has_faq"],
            "has_guarantee": detections["has_guarantee"],
            "has_pricing": detections["has_pricing"],
        },
        "funnel_score": normalized_score,
        "funnel_score_max": 10,
        "missing_critical": missing_critical,
        "missing_nice_to_have": missing_nice,
        "missing_elements": missing_critical + missing_nice,
    }


# =============================================
# MAIN
# =============================================
if __name__ == "__main__":
    import sys

    input_path = sys.argv[1] if len(sys.argv) > 1 else "raw_payload.json"

    with open(input_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    processed = process_profile(raw)
    print(json.dumps(processed, indent=2, ensure_ascii=False))

    output_path = input_path.replace(".json", "_processed.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(processed, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Saved to {output_path}")