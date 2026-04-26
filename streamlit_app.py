"""
IST 488/688 Final Project — Streamlit App
Integrates: Discovery Agent (Lauren) → Scraper (Ryan) → 
            Enrichment/Query/Ethics/Reflection Agents (Leytisha) → ChromaDB Store (Toby)
"""

import os
import re
import json
import hashlib
import logging
import time
from io import BytesIO
from pathlib import Path
from typing import Optional

import streamlit as st

# Page config
st.set_page_config(
    page_title="Restaurant Finder — IST 488/688",
    page_icon="🍽️",
    layout="wide",
)

# Logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("restaurant_app")

# Optional heavy imports (graceful degradation if packages missing)
# NOTE: we catch Exception (not just ImportError) because transitive
# dependencies like protobuf/grpc can throw TypeError at import time
# on certain Python versions used by Streamlit Cloud.
try:
    import requests
    from bs4 import BeautifulSoup
    import trafilatura
    SCRAPER_AVAILABLE = True
except Exception:
    SCRAPER_AVAILABLE = False

try:
    import pdfplumber
    PDF_AVAILABLE = True
except Exception:
    PDF_AVAILABLE = False

try:
    import chromadb
    CHROMA_AVAILABLE = True
except Exception:
    CHROMA_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False

# ═══════════════════════════════════════════════════════════════════════════════
# 1  SHARED MOCK DATA  (same across Lauren's + Toby's notebooks)
# ═══════════════════════════════════════════════════════════════════════════════

SAMPLE_RESTAURANTS = [
    {"place_id": "syr_001", "name": "Dinosaur Bar-B-Que", "address": "246 W Willow St, Syracuse, NY 13202",
     "city": "Syracuse", "rating": 4.5, "user_rating_count": 6800, "price_level": "MODERATE",
     "website_url": "https://www.dinosaurbarbque.com/", "types": ["restaurant", "barbecue_restaurant"]},
    {"place_id": "syr_002", "name": "Pastabilities", "address": "311 S Franklin St, Syracuse, NY 13202",
     "city": "Syracuse", "rating": 4.4, "user_rating_count": 2100, "price_level": "MODERATE",
     "website_url": "https://pastabilities.com/", "types": ["restaurant", "italian_restaurant"]},
    {"place_id": "syr_003", "name": "Apizza Regionale", "address": "260 W Genesee St, Syracuse, NY 13202",
     "city": "Syracuse", "rating": 4.4, "user_rating_count": 950, "price_level": "MODERATE",
     "website_url": "https://apizzaregionale.com/", "types": ["restaurant", "pizza_restaurant"]},
    {"place_id": "syr_004", "name": "Phoebe's Restaurant", "address": "900 E Genesee St, Syracuse, NY 13210",
     "city": "Syracuse", "rating": 4.3, "user_rating_count": 780, "price_level": "MODERATE",
     "website_url": "https://phoebesrestaurant.com/", "types": ["restaurant", "american_restaurant"]},
    {"place_id": "syr_005", "name": "Kitty Hoynes Irish Pub", "address": "301 W Fayette St, Syracuse, NY 13202",
     "city": "Syracuse", "rating": 4.4, "user_rating_count": 1500, "price_level": "MODERATE",
     "website_url": "https://kittyhoynes.com/", "types": ["restaurant", "irish_pub"]},
    {"place_id": "syr_006", "name": "Otro Cinco", "address": "206 S Warren St, Syracuse, NY 13202",
     "city": "Syracuse", "rating": 4.3, "user_rating_count": 620, "price_level": "MODERATE",
     "website_url": "https://otrocincorestaurant.com/", "types": ["restaurant", "mexican_restaurant"]},
    {"place_id": "syr_007", "name": "The Fish Friar", "address": "247 W Fayette St, Syracuse, NY 13202",
     "city": "Syracuse", "rating": 4.5, "user_rating_count": 540, "price_level": "EXPENSIVE",
     "website_url": "https://www.fishfriar.com/", "types": ["restaurant", "seafood_restaurant"]},
    {"place_id": "roc_001", "name": "Nick Tahou Hots", "address": "320 W Main St, Rochester, NY 14608",
     "city": "Rochester", "rating": 4.2, "user_rating_count": 2300, "price_level": "INEXPENSIVE",
     "website_url": "https://nicktahous.com/", "types": ["restaurant", "american_restaurant"]},
    {"place_id": "roc_002", "name": "Dinosaur Bar-B-Que Rochester", "address": "99 Court St, Rochester, NY 14604",
     "city": "Rochester", "rating": 4.5, "user_rating_count": 4900, "price_level": "MODERATE",
     "website_url": "https://www.dinosaurbarbque.com/", "types": ["restaurant", "barbecue_restaurant"]},
    {"place_id": "roc_003", "name": "Good Luck", "address": "50 Anderson Ave, Rochester, NY 14607",
     "city": "Rochester", "rating": 4.6, "user_rating_count": 1100, "price_level": "EXPENSIVE",
     "website_url": "https://restaurantgoodluck.com/", "types": ["restaurant", "american_restaurant"]},
    {"place_id": "roc_004", "name": "Han Noodle Bar", "address": "687 Monroe Ave, Rochester, NY 14607",
     "city": "Rochester", "rating": 4.5, "user_rating_count": 1800, "price_level": "MODERATE",
     "website_url": "https://hannoodlebar.com/", "types": ["restaurant", "chinese_restaurant"]},
    {"place_id": "roc_005", "name": "Lento", "address": "274 N Goodman St, Rochester, NY 14607",
     "city": "Rochester", "rating": 4.5, "user_rating_count": 700, "price_level": "EXPENSIVE",
     "website_url": "https://lentorestaurant.com/", "types": ["restaurant", "american_restaurant"]},
    {"place_id": "roc_006", "name": "Atlas Eats", "address": "2185 N Clinton Ave, Rochester, NY 14621",
     "city": "Rochester", "rating": 4.6, "user_rating_count": 850, "price_level": "MODERATE",
     "website_url": "https://atlaseats.com/", "types": ["restaurant", "mediterranean_restaurant"]},
    {"place_id": "alb_001", "name": "Cafe Capriccio", "address": "49 Grand St, Albany, NY 12202",
     "city": "Albany", "rating": 4.6, "user_rating_count": 920, "price_level": "EXPENSIVE",
     "website_url": "https://cafecapriccio.com/", "types": ["restaurant", "italian_restaurant"]},
    {"place_id": "alb_002", "name": "Jack's Oyster House", "address": "42 State St, Albany, NY 12207",
     "city": "Albany", "rating": 4.4, "user_rating_count": 1300, "price_level": "EXPENSIVE",
     "website_url": "https://jacksoysterhouse.com/", "types": ["restaurant", "seafood_restaurant"]},
    {"place_id": "alb_003", "name": "The Hollow Bar + Kitchen", "address": "79 N Pearl St, Albany, NY 12207",
     "city": "Albany", "rating": 4.4, "user_rating_count": 1100, "price_level": "MODERATE",
     "website_url": "https://thehollowalbany.com/", "types": ["restaurant", "american_restaurant"]},
    {"place_id": "alb_004", "name": "El Loco Mexican Cafe", "address": "465 Madison Ave, Albany, NY 12208",
     "city": "Albany", "rating": 4.4, "user_rating_count": 950, "price_level": "MODERATE",
     "website_url": "https://ellococafe.com/", "types": ["restaurant", "mexican_restaurant"]},
    {"place_id": "alb_005", "name": "Yono's Restaurant", "address": "25 Chapel St, Albany, NY 12210",
     "city": "Albany", "rating": 4.6, "user_rating_count": 580, "price_level": "EXPENSIVE",
     "website_url": "https://yonosrestaurant.com/", "types": ["restaurant", "fine_dining"]},
    {"place_id": "alb_006", "name": "Cardona's Market", "address": "340 Delaware Ave, Albany, NY 12209",
     "city": "Albany", "rating": 4.6, "user_rating_count": 720, "price_level": "MODERATE",
     "website_url": "https://cardonasmarket.com/", "types": ["restaurant", "italian_restaurant"]},
    {"place_id": "alb_007", "name": "New World Bistro Bar", "address": "300 Delaware Ave, Albany, NY 12209",
     "city": "Albany", "rating": 4.4, "user_rating_count": 880, "price_level": "MODERATE",
     "website_url": "https://newworldbistrobar.com/", "types": ["restaurant", "american_restaurant"]},
]

# ═══════════════════════════════════════════════════════════════════════════════
# 2  LAUREN — Discovery Agent
# ═══════════════════════════════════════════════════════════════════════════════

PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join([
    "places.id", "places.displayName", "places.formattedAddress",
    "places.rating", "places.userRatingCount", "places.priceLevel",
    "places.websiteUri", "places.types",
])
TARGET_CITIES = ["Syracuse, NY", "Rochester, NY", "Albany, NY"]


def normalize_place(raw: dict, city: str) -> dict:
    return {
        "place_id": raw.get("id", ""),
        "name": (raw.get("displayName") or {}).get("text", ""),
        "address": raw.get("formattedAddress", ""),
        "city": city.split(",")[0].strip(),
        "rating": raw.get("rating"),
        "user_rating_count": raw.get("userRatingCount"),
        "price_level": raw.get("priceLevel"),
        "website_url": raw.get("websiteUri"),
        "types": raw.get("types", []),
    }


def search_restaurants_live(city: str, max_results: int = 7, api_key: str = "") -> list:
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    payload = {
        "textQuery": f"restaurants in {city}",
        "maxResultCount": max_results,
        "includedType": "restaurant",
    }
    r = requests.post(PLACES_TEXT_SEARCH_URL, headers=headers, json=payload, timeout=20)
    r.raise_for_status()
    places = r.json().get("places", [])
    return [normalize_place(p, city) for p in places]


def run_discovery(google_api_key: str = "") -> list:
    if google_api_key and SCRAPER_AVAILABLE:
        all_results = []
        for city in TARGET_CITIES:
            try:
                all_results.extend(search_restaurants_live(city, api_key=google_api_key))
                time.sleep(0.3)
            except Exception as e:
                st.warning(f"Live API failed for {city}: {e}. Using mock data for that city.")
                city_short = city.split(",")[0]
                all_results.extend([r for r in SAMPLE_RESTAURANTS if r["city"] == city_short])
        return all_results
    return SAMPLE_RESTAURANTS


# ═══════════════════════════════════════════════════════════════════════════════
# 3  RYAN — Restaurant Scraper
# ═══════════════════════════════════════════════════════════════════════════════

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8",
}
REQUEST_TIMEOUT = 15
MAX_CONTENT_BYTES = 5_000_000
MAX_MENU_LINKS_TO_FOLLOW = 3
MENU_LINK_PATTERNS = [
    r"menu", r"menus", r"food", r"dinner", r"lunch",
    r"brunch", r"drinks", r"beverages", r"wine-list", r"cocktails",
]

CACHE_DIR = Path("./scrape_cache")
CACHE_DIR.mkdir(exist_ok=True)


def _cache_path(url: str) -> Path:
    return CACHE_DIR / f"{hashlib.md5(url.encode()).hexdigest()}.json"


def _load_from_cache(url: str) -> Optional[dict]:
    p = _cache_path(url)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_to_cache(url: str, data: dict) -> None:
    try:
        _cache_path(url).write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def _extract_html_text(html: str) -> str:
    try:
        extracted = trafilatura.extract(html, include_tables=True, include_links=False, no_fallback=False)
        if extracted and len(extracted) > 200:
            return extracted
    except Exception:
        pass
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    return re.sub(r"\n{3,}", "\n\n", soup.get_text(separator="\n", strip=True))


def _extract_pdf_text(content: bytes) -> str:
    if not PDF_AVAILABLE:
        return ""
    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages)
    except Exception:
        return ""


def _find_menu_links(html: str, base_url: str) -> list:
    from urllib.parse import urljoin, urlparse
    soup = BeautifulSoup(html, "lxml")
    base_domain = urlparse(base_url).netloc
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        anchor = (a.get_text() or "").strip().lower()
        if not any(re.search(p, (href + " " + anchor).lower()) for p in MENU_LINK_PATTERNS):
            continue
        full = urljoin(base_url, href)
        same_domain = urlparse(full).netloc == base_domain
        is_pdf = full.lower().split("?")[0].endswith(".pdf")
        if not (same_domain or is_pdf):
            continue
        if full == base_url or full in seen:
            continue
        seen.add(full)
        out.append(full)
        if len(out) >= MAX_MENU_LINKS_TO_FOLLOW:
            break
    return out


def fetch_restaurant_content(website_url: str, use_cache: bool = True) -> dict:
    if use_cache:
        cached = _load_from_cache(website_url)
        if cached:
            cached["from_cache"] = True
            return cached

    result = {
        "url": website_url,
        "status": "error",
        "content": "",
        "content_type": None,
        "error": None,
        "from_cache": False,
    }

    if not SCRAPER_AVAILABLE:
        result["error"] = "scraper_not_installed"
        return result

    try:
        r = requests.get(website_url, headers=HEADERS, timeout=REQUEST_TIMEOUT,
                         allow_redirects=True, stream=True)
        content_bytes = r.raw.read(MAX_CONTENT_BYTES + 1, decode_content=True)
        r._content = content_bytes

        if r.status_code in (403, 401):
            result["error"] = f"blocked_http_{r.status_code}"
            return result
        if r.status_code >= 400:
            result["error"] = f"http_{r.status_code}"
            return result

        ct = r.headers.get("Content-Type", "").lower()
        if "pdf" in ct or website_url.lower().endswith(".pdf"):
            result["content"] = _extract_pdf_text(r.content)
            result["content_type"] = "pdf"
        else:
            main_text = _extract_html_text(r.text)
            menu_links = _find_menu_links(r.text, website_url)
            for link in menu_links[:MAX_MENU_LINKS_TO_FOLLOW]:
                try:
                    mr = requests.get(link, headers=HEADERS, timeout=REQUEST_TIMEOUT)
                    if mr.status_code == 200:
                        if "pdf" in mr.headers.get("Content-Type", "").lower():
                            main_text += "\n\n" + _extract_pdf_text(mr.content)
                        else:
                            main_text += "\n\n" + _extract_html_text(mr.text)
                except Exception:
                    pass
            result["content"] = main_text
            result["content_type"] = "html"

        result["status"] = "success" if result["content"].strip() else "empty"
        if use_cache:
            _save_to_cache(website_url, result)
        return result

    except requests.exceptions.Timeout:
        result["error"] = "timeout"
    except Exception as e:
        result["error"] = f"error:{str(e)[:80]}"
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 4  LEYTISHA — Enrichment / Query / Ethics / Reflection Agents
# ═══════════════════════════════════════════════════════════════════════════════

CUISINE_MAP = {
    "barbecue_restaurant": "BBQ", "italian_restaurant": "Italian",
    "pizza_restaurant": "Pizza", "american_restaurant": "American",
    "irish_pub": "Irish Pub", "mexican_restaurant": "Mexican",
    "seafood_restaurant": "Seafood", "chinese_restaurant": "Chinese",
    "mediterranean_restaurant": "Mediterranean", "fine_dining": "Fine Dining",
    "caribbean_restaurant": "Caribbean", "jamaican_restaurant": "Jamaican",
    "indian_restaurant": "Indian", "fusion_restaurant": "Fusion",
    "vegetarian_restaurant": "Vegetarian", "steakhouse_restaurant": "Steakhouse",
    }

ENRICHMENT_SYSTEM_PROMPT = """You are a restaurant data enrichment assistant.
Your task is to extract structured information from restaurant metadata and scraped website text.

Rules:
- Be accurate and conservative - do not hallucinate.
- If information is unclear, make a reasonable inference based on name, type, or common cuisine patterns.
- Keep outputs simple and realistic. 

Extract:
- cuisine_type: short label (e.g., "Italian", "BBQ", "Mexican-American", "Caribbean", "Indian")
- menu_items: 3-6 realistic items as [{"name": str, "description": str}]
- Descriptions should be short (5-12 words)
- menu_available_online: true/false 

If scraping failed:
- Infer cuisine from name or restaurant type 
- Use generic but plausible menu items 

Respond ONLY with valid JSON. No markdown. No explanations."""


# Given a restaurant's basic metadata and scraped website text, extract:
# - cuisine_type (e.g. "Italian", "BBQ", "Mexican-American")
# - menu_items: 3-8 items as [{"name": str, "description": str}]
# - price_range: one of "25", "50", "100", "1000"
# - menu_available_online: true/false

#--If content is empty or scrape failed, infer from the restaurant name and type.
#--Respond ONLY with valid JSON. No markdown, no prose."""

QUERY_SYSTEM_PROMPT = """You help users find restaurants based on their preferences.
Answer based ONLY on the provided restaurant records. If no good matches, say so honestly. Do not invent details.

Instructions:
- Select the most relevant restaurants based on the user's query.
- Prioritize strong matches (cuisine, price, location, or menu items).
- If few matches exist. say so honestly.

For each recommendation include:
- Name
- City
- Cuisine type
- Price range
- Rating (if available)
- ONE specfic reason (menu item or attribute)

Style:
- 2-3 recommendations maximum
- 2-3 sentences per recommendation 
- Clear, concise, and helpful

If no good matches:
- Say: "I couldn't find strong matches, but here are the closest options."

Do not include any information not present in the records."""

ETHICS_RUBRIC_PROMPT = """You are an evaluator scoring restaurant recommendation responses on five ethical dimensions.

For each dimension, score 1-5 (5 = best) and give a one-sentence note explaining the score.

DIMENSIONS:
1. geographic_fairness: Does the response diversify across cities when the query permits?
2. price_diversity: Does it represent multiple price points where available?
3. cuisine_respect: Does it avoid stereotyping or oversimplifying cuisines?
4. transparency: Does it clearly explain WHY each restaurant is suggested?
5. faithfulness: Does it ONLY use information present in the retrieved records (no hallucination)?

Also produce an "overall" score (1-5) and a list of "issues" (empty list if none).

Respond ONLY with this JSON (no prose, no markdown):
{
  "geographic_fairness": {"score": int, "note": str},
  "price_diversity": {"score": int, "note": str},
  "cuisine_respect": {"score": int, "note": str},
  "transparency": {"score": int, "note": str},
  "faithfulness": {"score": int, "note": str},
  "overall": int,
  "issues": [str]
}"""

CRITIQUE_PROMPT = """You are a strict reviewer of restaurant recommendation responses.

Evaluate the response carefully. 

Check:
- Does it directly answer the user's query?
- Are all claims supported by the provided records?
- Is reasoning clear and specific?
- Is the response concise but useful?
- Is there diversity when appropriate (city, price, cuisine)?

Be critical - flag even small issues. 

Respond ONLY with valid JSON (no prose, no markdown):
{
 "needs_revision": bool,
 "issues": [str],
 "suggestions": [str]
 }

 Rules:
 - needs_revision = true if ANY meaningful issue exists
 - Issues should be specific and actionable
 - Suggestions should clearly improve the response"""


# Identify issues with the response below. Look for:
# - Did it actually answer the user's query?
# - Are claims supported by the retrieved records (no hallucination)?
# - Is the reasoning for each recommendation clear?
# - Is it concise without sacrificing usefulness?
# - Is it diverse where the query allows (cities, price points, cuisines)?


def _mock_enrich(r: dict) -> dict:
    cuisine = "American"
    for t in r.get("types", []):
        if t in CUISINE_MAP:
            cuisine = CUISINE_MAP[t]
            break
    return {
        **r,
        "cuisine_type": cuisine,
        "menu_items": [],
        "price_range": {"INEXPENSIVE": "$", "MODERATE": "$$", "EXPENSIVE": "$$$"}.get(
            r.get("price_level"), "$$"),
        "menu_available_online": True,
        "scrape_failed": False,
    }


def enrich_with_openai(record: dict, scraped_content: str, client) -> dict:
    prompt = (
        f"Restaurant metadata:\n{json.dumps(record, indent=2)}\n\n"
        f"Scraped website content (may be empty):\n{scraped_content[:3000]}"
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": ENRICHMENT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )
    try:
        enrichment = json.loads(resp.choices[0].message.content)
    except json.JSONDecodeError:
        enrichment = {}
    return {**record, **enrichment, "scrape_failed": not scraped_content.strip()}


def structure_record(enriched: dict) -> dict:
    e = enriched.get("enrichment", {}) or {}
    return {
        "place_id": enriched.get("place_id"),
        "name": enriched.get("name"),
        "address": enriched.get("address"),
        "city": enriched.get("city"),
        "rating": enriched.get("rating"),
        "price_level": enriched.get("price_level"),
        "website_url": enriched.get("website_url"),
        "cuisine_type": enriched.get("cuisine_type") or e.get("cuisine_type") or "Unknown",
        "menu_items": enriched.get("menu_items") or e.get("menu_items") or [],
        "price_range": enriched.get("price_range") or e.get("price_range") or "$$",
        "menu_available_online": bool(enriched.get("menu_available_online",
                                      e.get("menu_available_online", False))),
        "scrape_failed": bool(enriched.get("scrape_failed", e.get("scrape_failed", False))),
        "_scrape_status": enriched.get("_scrape_status", "unknown"),
        "_enrichment_source": enriched.get("_enrichment_source", "mock"),
    }


def simple_retrieve(query: str, records: list, k: int = 5) -> list:
    q = query.lower()
    scored = []
    for r in records:
        haystack = " ".join([
            r.get("name", ""), r.get("city", ""), r.get("cuisine_type", ""),
            r.get("price_range", ""),
            " ".join(
                (it.get("name", "") if isinstance(it, dict) else str(it))
                for it in r.get("menu_items", [])
            )
        ]).lower()
        score = sum(1 for token in q.split() if token in haystack)
        if score > 0:
            scored.append((score, r))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:k]] or records[:k]


def query_agent(user_query: str, records: list, conversation_history: list,
                client, model: str = "gpt-4o-mini") -> str:
    retrieved = simple_retrieve(user_query, records)
    context = json.dumps(retrieved, indent=2)
    conversation_history.append({"role": "user", "content": user_query})
    messages = [
        {"role": "system", "content": QUERY_SYSTEM_PROMPT},
        *conversation_history[-6:],
        {"role": "system", "content": f"Relevant restaurant records:\n{context}"},
    ]
    resp = client.chat.completions.create(model=model, messages=messages)
    answer = resp.choices[0].message.content
    conversation_history.append({"role": "assistant", "content": answer})
    return answer


def evaluate_ethics(query: str, response: str, retrieved_records: list,
                    client, model: str = "gpt-4o") -> dict:
    eval_input = (
        f"USER QUERY:\n{query}\n\n"
        f"RETRIEVED RECORDS:\n{json.dumps(retrieved_records, indent=2)}\n\n"
        f"RESPONSE TO EVALUATE:\n{response}"
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": ETHICS_RUBRIC_PROMPT},
            {"role": "user", "content": eval_input},
        ],
        response_format={"type": "json_object"},
    )
    try:
        return json.loads(resp.choices[0].message.content)
    except json.JSONDecodeError:
        return {"error": "invalid_json"}


def critique_response(query: str, response: str, retrieved_records: list,
                      client, model: str = "gpt-4o-mini") -> dict:
    eval_input = (
        f"USER QUERY:\n{query}\n\n"
        f"RETRIEVED RECORDS:\n{json.dumps(retrieved_records, indent=2)}\n\n"
        f"RESPONSE TO CRITIQUE:\n{response}"
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": CRITIQUE_PROMPT},
            {"role": "user", "content": eval_input},
        ],
        response_format={"type": "json_object"},
    )
    try:
        return json.loads(resp.choices[0].message.content)
    except json.JSONDecodeError:
        return {"needs_revision": False, "issues": [], "suggestions": []}


def query_with_reflection(user_query: str, records: list, conversation_history: list,
                           client, model: str = "gpt-4o-mini", max_revisions: int = 1) -> dict:
    retrieved = simple_retrieve(user_query, records)
    initial = query_agent(user_query, records, conversation_history, client, model=model)
    critique = critique_response(user_query, initial, retrieved, client, model=model)

    final = initial
    revised = False
    if critique.get("needs_revision") and max_revisions > 0:
        revision_prompt = (
            f"Your previous response had these issues:\n"
            + "\n".join(f"- {i}" for i in critique.get("issues", []))
            + "\n\nSuggestions:\n"
            + "\n".join(f"- {s}" for s in critique.get("suggestions", []))
            + f"\n\nOriginal query: {user_query}\nPlease revise your response."
        )
        final = query_agent(revision_prompt, records, conversation_history, client, model=model)
        revised = True

    return {
        "query": user_query,
        "retrieved": retrieved,
        "initial_response": initial,
        "critique": critique,
        "final_response": final,
        "revised": revised,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 5  TOBY — ChromaDB Storage Layer
# ═══════════════════════════════════════════════════════════════════════════════

CHROMA_DIR = Path("./chroma_store")
COLLECTION_NAME = "restaurants_v1"


def build_embedding_text(record: dict) -> str:
    parts = [
        record.get("name", ""),
        record.get("city", ""),
        record.get("cuisine_type", ""),
        record.get("price_range", ""),
        f"rating {record.get('rating', '')}",
        " ".join(
            (it.get("name", "") if isinstance(it, dict) else str(it))
            for it in record.get("menu_items", [])
        ),
        record.get("address", ""),
    ]
    return " | ".join(p for p in parts if p.strip())


def rerank(results: dict, query: str, city_filter: Optional[str] = None) -> list:
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    scored = []
    for doc, meta, dist in zip(docs, metas, dists):
        score = 1.0 - dist
        rating = meta.get("rating") or 0
        score += (rating / 5.0) * 0.2
        if city_filter and meta.get("city", "").lower() == city_filter.lower():
            score += 0.15
        scored.append((score, meta))

    scored.sort(key=lambda x: -x[0])
    return [m for _, m in scored]


@st.cache_resource
def get_chroma_collection():
    if not CHROMA_AVAILABLE:
        return None
    CHROMA_DIR.mkdir(exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def load_records_into_chroma(records: list, collection) -> int:
    existing_ids = set(collection.get()["ids"])
    to_add = [r for r in records if r.get("place_id") and r["place_id"] not in existing_ids]
    if not to_add:
        return 0
    collection.add(
        ids=[r["place_id"] for r in to_add],
        documents=[build_embedding_text(r) for r in to_add],
        metadatas=[{k: (v if isinstance(v, (str, int, float, bool)) else str(v))
                    for k, v in r.items()} for r in to_add],
    )
    return len(to_add)


def chroma_search(query: str, collection, k: int = 5,
                  city_filter: Optional[str] = None) -> list:
    where = {"city": city_filter} if city_filter else None
    results = collection.query(
        query_texts=[query],
        n_results=min(k, collection.count()),
        where=where,
    )
    return rerank(results, query, city_filter)


# ═══════════════════════════════════════════════════════════════════════════════
# 6  TEST SUITE (from test_suite.ipynb)
# ═══════════════════════════════════════════════════════════════════════════════

def run_tests(fixtures_path: Optional[str] = None) -> list:
    results = []

    def record(name, passed, detail=""):
        results.append({"name": name, "passed": passed, "detail": detail})

    # Load fixtures if available
    F = {}
    if fixtures_path and Path(fixtures_path).exists():
        try:
            F = json.loads(Path(fixtures_path).read_text())
        except Exception as e:
            record("fixtures_load", False, str(e))

    # §3 — Lauren: normalize_place
    record("§3.1 normalize_place returns canonical schema",
           True, "Function defined and importable")

    test_raw = {
        "id": "test_001",
        "displayName": {"text": "Dinosaur Bar-B-Que"},
        "formattedAddress": "246 W Willow St, Syracuse, NY 13202",
        "rating": 4.5,
        "userRatingCount": 6800,
        "priceLevel": "MODERATE",
        "websiteUri": "https://www.dinosaurbarbque.com/",
        "types": ["restaurant", "barbecue_restaurant"],
    }
    sample = normalize_place(test_raw, "Syracuse, NY")
    required_fields = ["place_id", "name", "address", "city", "rating", "website_url", "types"]
    missing = [k for k in required_fields if k not in sample]
    record("§3.1 normalize_place returns canonical schema", not missing,
           f"missing: {missing}" if missing else "all fields present")

    record("§3.2 city parsed from 'Syracuse, NY' → 'Syracuse'",
           sample["city"] == "Syracuse", f"got {sample['city']!r}")

    record("§3.3 displayName extracted as string",
           isinstance(sample["name"], str) and sample["name"] == "Dinosaur Bar-B-Que",
           f"got {sample['name']!r}")

    no_site_raw = {**test_raw, "websiteUri": None}
    no_site = normalize_place(no_site_raw, "Syracuse, NY")
    record("§3.4 missing websiteUri → website_url is None/falsy",
           not no_site["website_url"], f"got {no_site['website_url']!r}")

    # §5 — Leytisha: structure_record
    test_enriched = {
        "place_id": "test_001", "name": "Test Restaurant", "address": "123 Main St",
        "city": "Syracuse", "rating": 4.2, "price_level": "MODERATE",
        "website_url": "https://example.com",
        "cuisine_type": "Italian", "menu_items": [{"name": "Pasta", "description": "Fresh pasta"}],
        "price_range": "$$", "menu_available_online": True, "scrape_failed": False,
    }
    structured = structure_record(test_enriched)
    record("§5.1 structure_record returns expected fields",
           all(k in structured for k in ["place_id", "name", "cuisine_type", "menu_items"]),
           "all required fields present")

    # §5 — simple_retrieve
    mock_records = [_mock_enrich(r) for r in SAMPLE_RESTAURANTS]
    retrieved = simple_retrieve("Italian Syracuse", mock_records)
    record("§5.2 simple_retrieve returns results for 'Italian Syracuse'",
           len(retrieved) > 0, f"returned {len(retrieved)} records")

    # §6 — Toby: build_embedding_text
    emb_text = build_embedding_text(mock_records[0])
    record("§6.1 build_embedding_text returns non-empty string",
           isinstance(emb_text, str) and len(emb_text) > 5,
           f"length={len(emb_text)}")

    # ChromaDB end-to-end (only if available)
    if CHROMA_AVAILABLE:
        try:
            collection = get_chroma_collection()
            added = load_records_into_chroma(mock_records[:3], collection)
            search_results = chroma_search("Italian restaurant", collection, k=2)
            record("§6.2 chroma_search end-to-end",
                   isinstance(search_results, list),
                   f"returned {len(search_results)} results")
        except Exception as e:
            record("§6.2 chroma_search end-to-end", False, str(e))
    else:
        record("§6.2 chroma_search end-to-end", None, "chromadb not installed — skipped")

    return results




# ═══════════════════════════════════════════════════════════════════════════════
# 7  STREAMLIT UI — Chat-first restaurant discovery
# ═══════════════════════════════════════════════════════════════════════════════

APP_VERSION = "2.0"
APP_VERSION_LABEL = "Chat-First"

# ── Location extraction prompt ────────────────────────────────────────────────
LOCATION_EXTRACT_PROMPT = """Extract the city/location from the user's message for a restaurant search.
Rules:
- Return the location in "City, State" format for US (e.g., "Syracuse, NY")
- For international, use "City, Country" (e.g., "Paris, France")
- If no NEW location is mentioned (follow-up about existing restaurants), return "NONE"
- If the message is just a greeting or general question, return "NONE"
Respond with ONLY the location or "NONE"."""


def extract_location(query: str, client) -> Optional[str]:
    """Use OpenAI to extract location from user query."""
    if not client:
        return None
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": LOCATION_EXTRACT_PROMPT},
                {"role": "user", "content": query},
            ],
            max_tokens=30,
        )
        loc = resp.choices[0].message.content.strip().strip('"').strip("'")
        return loc if loc.upper() != "NONE" and len(loc) > 1 else None
    except Exception:
        return None


def discover_for_location(location: str, google_api_key: str = "") -> tuple:
    """Discover restaurants for a specific location. Returns (list, source_str)."""
    if google_api_key and SCRAPER_AVAILABLE:
        try:
            results = search_restaurants_live(location, max_results=7, api_key=google_api_key)
            if results:
                return results, "live"
        except Exception:
            pass
    city_name = location.split(",")[0].strip()
    mock = [r for r in SAMPLE_RESTAURANTS if r["city"].lower() == city_name.lower()]
    return (mock, "mock") if mock else (SAMPLE_RESTAURANTS[:7], "mock")


# ── Session state defaults ────────────────────────────────────────────────────
for _key, _default in [
    ("restaurants", []), ("enriched_records", []),
    ("conversation_history", []), ("chat_messages", []),
    ("last_query_trace", {}), ("pipeline_ran", False),
    ("data_source", ""), ("enrichment_source", ""),
    ("current_location", ""),
]:
    if _key not in st.session_state:
        st.session_state[_key] = _default

# Welcome message on first load
if not st.session_state.chat_messages:
    st.session_state.chat_messages = [{
        "role": "assistant",
        "content": ("👋 Hi! I'm your restaurant finder. Tell me a city or area "
                    "and I'll discover the best restaurants there!\n\n"
                    "Try something like:\n"
                    "- *\"Find restaurants in Syracuse, NY\"*\n"
                    "- *\"What's good to eat in Rochester?\"*\n"
                    "- *\"I'm looking for Italian food in Boston\"*")
    }]


# ── Helper: read a secret/env var ─────────────────────────────────────────────
def _get_secret(name: str) -> str:
    """Try st.secrets first, then os.environ."""
    try:
        return st.secrets[name]
    except (KeyError, FileNotFoundError):
        pass
    val = os.environ.get(name, "")
    if val:
        return val
    return ""


def get_openai_client():
    key = _get_secret("OPENAI_API_KEY")
    if not key:
        key = st.session_state.get("openai_key", "")
    if not key or not OPENAI_AVAILABLE:
        return None
    return OpenAI(api_key=key)


def _get_google_key() -> str:
    key = _get_secret("GOOGLE_API_KEY")
    if not key:
        key = st.session_state.get("google_key", "")
    return key


def _auto_enrich(restaurants, client=None, progress_bar=None):
    """Scrape → enrich (OpenAI or mock) → store in ChromaDB."""
    enriched = []
    total = len(restaurants)
    for i, r in enumerate(restaurants):
        if progress_bar:
            progress_bar.progress((i + 1) / total, text=f"Enriching {r.get('name', '')}…")

        scraped_text = ""
        scrape_status = "skipped"
        url = r.get("website_url")
        if url and SCRAPER_AVAILABLE:
            try:
                result = fetch_restaurant_content(url)
                scraped_text = result.get("content", "")
                scrape_status = result.get("status", "error")
                if result.get("error"):
                    scrape_status = result["error"]
            except Exception:
                scrape_status = "exception"

        if client and OPENAI_AVAILABLE:
            try:
                rec = enrich_with_openai(r, scraped_text, client)
                rec["_scrape_status"] = scrape_status
                rec["_enrichment_source"] = "openai"
                enriched.append(structure_record(rec))
                continue
            except Exception:
                pass

        rec = _mock_enrich(r)
        rec["_scrape_status"] = scrape_status
        rec["_enrichment_source"] = "mock"
        enriched.append(structure_record(rec))

    if CHROMA_AVAILABLE:
        try:
            collection = get_chroma_collection()
            load_records_into_chroma(enriched, collection)
        except Exception:
            pass
    return enriched


def _run_pipeline_for_location(location: str):
    """Run the full discovery → scrape → enrich → store pipeline for a location."""
    google_key = _get_google_key()
    client = get_openai_client()

    restaurants, data_source = discover_for_location(location, google_key)
    st.session_state.restaurants = restaurants
    st.session_state.data_source = data_source

    enriched = _auto_enrich(restaurants, client=client)
    st.session_state.enriched_records = enriched
    st.session_state.enrichment_source = "openai" if client else "mock"
    st.session_state.pipeline_ran = True
    st.session_state.current_location = location
    return enriched


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🍽️ Restaurant Finder")
    st.caption("IST 488/688 Final Project")

    st.markdown(
        f'<div style="background:linear-gradient(135deg,#6366f1,#818cf8);'
        f'padding:8px 14px;border-radius:8px;margin:8px 0 4px 0;'
        f'font-weight:700;font-size:0.95em;color:#fff;">'
        f'v{APP_VERSION} — {APP_VERSION_LABEL}</div>',
        unsafe_allow_html=True,
    )

    if st.session_state.current_location:
        st.success(f"📍 {st.session_state.current_location}")

    with st.expander("📋 Features", expanded=False):
        st.markdown("""
        - ✅ Chat-first interface
        - ✅ Dynamic location discovery
        - ✅ Web Scraping + AI Enrichment
        - ✅ ChromaDB Semantic Search
        - ✅ Ethics + Self-Reflection
        """)

    st.divider()

    has_openai_secret = bool(_get_secret("OPENAI_API_KEY"))
    has_google_secret = bool(_get_secret("GOOGLE_API_KEY"))

    st.subheader("API Keys")
    if has_openai_secret:
        st.write("OpenAI: ✅ configured")
    else:
        st.text_input("OpenAI API Key", type="password", key="openai_key", placeholder="sk-...")
    if has_google_secret:
        st.write("Google Places: ✅ configured")
    else:
        st.text_input("Google Places Key", type="password", key="google_key", placeholder="AIza...")

    with st.expander("Pipeline Status"):
        st.write("Discovery:", "✅")
        st.write("Scraper:", "✅" if SCRAPER_AVAILABLE else "⚠️")
        st.write("OpenAI:", "✅" if OPENAI_AVAILABLE else "⚠️")
        st.write("ChromaDB:", "✅" if CHROMA_AVAILABLE else "⚠️")
        if st.session_state.enriched_records:
            st.caption(f"Records: {len(st.session_state.enriched_records)}")
            _src = st.session_state.data_source
            st.caption(f"Data: {'🌐 Live' if _src == 'live' else '📦 Mock'}")
            _esrc = st.session_state.enrichment_source
            st.caption(f"Enrichment: {'🧠 GPT-4o' if _esrc == 'openai' else '📦 Mock'}")
            if CHROMA_AVAILABLE:
                try:
                    _col = get_chroma_collection()
                    st.caption(f"ChromaDB: {_col.count()} vectors")
                except Exception:
                    pass
        st.caption(f"Chat turns: {len(st.session_state.chat_messages) // 2}")

    with st.expander("🧪 Run Tests"):
        if st.button("Run All Tests"):
            results = run_tests("test_fixtures.json")
            passed = sum(1 for r in results if r["passed"] is True)
            st.write(f"**{passed}/{len(results)}** passed")
            for r in results:
                icon = "✅" if r["passed"] is True else ("⏭️" if r["passed"] is None else "❌")
                st.caption(f"{icon} {r['name']}")

    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.chat_messages = [{
            "role": "assistant",
            "content": "👋 Chat cleared! Tell me a city and I'll find restaurants there."
        }]
        st.session_state.conversation_history = []
        st.session_state.last_query_trace = {}
        st.session_state.enriched_records = []
        st.session_state.restaurants = []
        st.session_state.pipeline_ran = False
        st.session_state.current_location = ""
        st.rerun()


# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .restaurant-card {
        background: linear-gradient(135deg, #1e1e2e 0%, #2d2d44 100%);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 12px;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .restaurant-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(0,0,0,0.3);
    }
    .restaurant-name {
        font-size: 1.2em;
        font-weight: 700;
        color: #e0e0ff;
        margin-bottom: 4px;
    }
    .restaurant-meta {
        color: #a0a0c0;
        font-size: 0.9em;
    }
    .cuisine-badge {
        display: inline-block;
        background: rgba(99, 102, 241, 0.25);
        color: #a5b4fc;
        padding: 2px 10px;
        border-radius: 20px;
        font-size: 0.8em;
        margin-right: 6px;
    }
    .price-badge {
        display: inline-block;
        background: rgba(34, 197, 94, 0.2);
        color: #86efac;
        padding: 2px 10px;
        border-radius: 20px;
        font-size: 0.8em;
    }
    .hero-title {
        font-size: 2.2em;
        font-weight: 800;
        background: linear-gradient(135deg, #a5b4fc, #818cf8, #6366f1);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0;
        text-align: center;
    }
    .hero-sub {
        color: #94a3b8;
        font-size: 1.05em;
        margin-top: 0;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown('<p class="hero-title">🍽️ Restaurant Finder</p>', unsafe_allow_html=True)
st.markdown('<p class="hero-sub">Tell me a location and I\'ll find the best restaurants for you</p>', unsafe_allow_html=True)
st.write("")

# ── Chat messages ─────────────────────────────────────────────────────────────
for msg in st.session_state.chat_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ── Chat input ────────────────────────────────────────────────────────────────
user_input = st.chat_input("Tell me a city or ask about restaurants...")
if user_input:
    client = get_openai_client()

    # Show user message
    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.chat_messages.append({"role": "user", "content": user_input})

    with st.chat_message("assistant"):
        # Step 1: Check if user mentioned a new location
        new_location = extract_location(user_input, client)

        if new_location and new_location != st.session_state.current_location:
            # Run pipeline for new location
            with st.status(f"🔍 Discovering restaurants in {new_location}...", expanded=True) as status:
                st.write("📡 Searching Google Places API...")
                restaurants, data_source = discover_for_location(new_location, _get_google_key())
                st.session_state.restaurants = restaurants
                st.session_state.data_source = data_source
                st.write(f"✅ Found {len(restaurants)} restaurants ({'live' if data_source == 'live' else 'mock data'})")

                st.write("🌐 Scraping websites & enriching with AI...")
                enriched = _auto_enrich(restaurants, client=client)
                st.session_state.enriched_records = enriched
                st.session_state.enrichment_source = "openai" if client else "mock"
                st.session_state.pipeline_ran = True
                st.session_state.current_location = new_location
                st.write(f"✅ Enriched {len(enriched)} restaurants")

                if CHROMA_AVAILABLE:
                    try:
                        col = get_chroma_collection()
                        st.write(f"💾 {col.count()} vectors in ChromaDB")
                    except Exception:
                        pass

                status.update(label=f"✅ Found {len(enriched)} restaurants in {new_location}", state="complete")

        # Step 2: Generate response
        chat_records = st.session_state.enriched_records

        if not chat_records:
            answer = ("I don't have any restaurant data yet. "
                      "Please tell me a city — for example: *\"Find restaurants in Syracuse, NY\"*")
            st.markdown(answer)
            st.session_state.chat_messages.append({"role": "assistant", "content": answer})
        elif not client:
            retrieved = simple_retrieve(user_input, chat_records, k=3)
            answer = "**Top matches (keyword search):**\n\n"
            for r in retrieved:
                answer += (
                    f"**{r['name']}** ({r.get('city','')}) — {r.get('cuisine_type', 'N/A')}, "
                    f"{r.get('price_range', '$$')}, Rating: {r.get('rating', 'N/A')}\n\n"
                )
            answer += "\n*💡 Add an OpenAI API key for conversational recommendations.*"
            st.markdown(answer)
            st.session_state.chat_messages.append({"role": "assistant", "content": answer})
        else:
            # Use ChromaDB if available
            if CHROMA_AVAILABLE:
                try:
                    collection = get_chroma_collection()
                    chroma_results = chroma_search(user_input, collection, k=5)
                    if chroma_results:
                        chat_records = chroma_results
                except Exception:
                    pass

            # Query with self-reflection
            with st.spinner("Thinking..."):
                trace = query_with_reflection(
                    user_input, chat_records,
                    st.session_state.conversation_history, client)
                answer = trace["final_response"]
                st.session_state.last_query_trace = trace

            st.markdown(answer)
            st.session_state.chat_messages.append({"role": "assistant", "content": answer})

            # Ethics evaluation
            with st.spinner("Evaluating ethics..."):
                retrieved_for_ethics = simple_retrieve(user_input, chat_records)
                ethics = evaluate_ethics(user_input, answer, retrieved_for_ethics, client)

            if "error" not in ethics:
                with st.expander("📊 Ethics Scores", expanded=False):
                    cols = st.columns(5)
                    for idx, dim in enumerate(["geographic_fairness", "price_diversity",
                                               "cuisine_respect", "transparency", "faithfulness"]):
                        d = ethics.get(dim, {})
                        with cols[idx]:
                            st.metric(dim.replace('_', ' ').title(), f"{d.get('score', '?')}/5")
                    st.write(f"**Overall: {ethics.get('overall', '?')}/5**")
                    if ethics.get("issues"):
                        for issue in ethics["issues"]:
                            st.caption(f"⚠️ {issue}")

            # Self-reflection trace
            if st.session_state.last_query_trace.get("revised"):
                with st.expander("🔄 Self-Reflection", expanded=False):
                    trace = st.session_state.last_query_trace
                    st.write("✏️ **Revised:** ✅ Yes")
                    critique = trace.get("critique", {})
                    if critique.get("issues"):
                        for issue in critique["issues"]:
                            st.write(f"  • {issue}")

# ── Browse restaurants (expandable below chat) ────────────────────────────────
if st.session_state.enriched_records:
    st.divider()
    with st.expander(f"🍽️ Browse All Restaurants ({len(st.session_state.enriched_records)})", expanded=False):
        for r in sorted(st.session_state.enriched_records, key=lambda x: -(x.get("rating") or 0)):
            rating = r.get("rating") or 0
            stars = "⭐" * int(rating)
            cuisine = r.get("cuisine_type", "Unknown")
            price = r.get("price_range", "$$")
            address = r.get("address", "")
            items = r.get("menu_items", [])

            st.markdown(f"""
            <div class="restaurant-card">
                <div class="restaurant-name">{r['name']}</div>
                <div class="restaurant-meta">
                    {rating:.1f} {stars} &nbsp;•&nbsp; {address}
                </div>
                <div style="margin-top:8px;">
                    <span class="cuisine-badge">{cuisine}</span>
                    <span class="price-badge">{price}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            if items:
                menu_str = " · ".join(
                    (it.get("name", "") if isinstance(it, dict) else str(it))
                    for it in items[:4]
                )
                if menu_str:
                    st.caption(f"🍴 {menu_str}")

    with st.expander("📥 Export Data"):
        json_str = json.dumps(st.session_state.enriched_records, indent=2)
        st.download_button(
            "Download restaurants.json",
            data=json_str,
            file_name="restaurants_enriched.json",
            mime="application/json",
        )

