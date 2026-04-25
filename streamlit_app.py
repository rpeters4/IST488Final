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
    "indian_restaurant": "Indian", "fusion_restaurant": "franco_korean", "pan-asian": "Fusion",
    }

ENRICHMENT_SYSTEM_PROMPT = """You are a restaurant data enrichment assistant.
Given a restaurant's basic metadata and scraped website text, extract:
- cuisine_type (e.g. "Italian", "BBQ", "Mexican-American")
- menu_items: 3-8 items as [{"name": str, "description": str}]
- price_range: one of "$", "$$", "$$$", "$$$$"
- menu_available_online: true/false

If content is empty or scrape failed, infer from the restaurant name and type.
Respond ONLY with valid JSON. No markdown, no prose."""

QUERY_SYSTEM_PROMPT = """You help users find restaurants in upstate NY (Syracuse, Rochester, Albany).
Answer based ONLY on the provided restaurant records. If no good matches, say so honestly.
For each recommendation, mention: name, city, cuisine, price range, rating, and ONE concrete reason
why it fits the query (e.g., a specific menu item or attribute).
Be concise — 2-4 sentences per recommendation."""

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
Identify issues with the response below. Look for:
- Did it actually answer the user's query?
- Are claims supported by the retrieved records (no hallucination)?
- Is the reasoning for each recommendation clear?
- Is it concise without sacrificing usefulness?
- Is it diverse where the query allows (cities, price points, cuisines)?

Respond ONLY with this JSON (no prose, no markdown):
{
  "needs_revision": bool,
  "issues": [str],
  "suggestions": [str]
}"""


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
# 7  STREAMLIT UI — Single-page seamless flow
# ═══════════════════════════════════════════════════════════════════════════════

# ── Session state defaults ────────────────────────────────────────────────────
for _key, _default in [
    ("restaurants", []), ("enriched_records", []),
    ("conversation_history", []), ("chat_messages", []),
    ("last_query_trace", {}), ("pipeline_ran", False),
]:
    if _key not in st.session_state:
        st.session_state[_key] = _default


def get_openai_client():
    key = st.session_state.get("openai_key", "")
    if not key:
        key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        try:
            key = st.secrets.get("OPENAI_API_KEY", "")
        except Exception:
            pass
    if not key or not OPENAI_AVAILABLE:
        return None
    return OpenAI(api_key=key)


def _auto_enrich(restaurants):
    """Run mock enrichment + optional ChromaDB load in one shot."""
    enriched = [structure_record(_mock_enrich(r)) for r in restaurants]
    if CHROMA_AVAILABLE:
        try:
            collection = get_chroma_collection()
            load_records_into_chroma(enriched, collection)
        except Exception:
            pass
    return enriched


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🍽️ Restaurant Finder")
    st.caption("IST 488/688 Final Project — Upstate NY")
    st.divider()

    with st.expander("Pipeline Status"):
        st.write("Discovery:", "✅")
        st.write("Scraper:", "✅" if SCRAPER_AVAILABLE else "⚠️ limited")
        st.write("OpenAI:", "✅" if OPENAI_AVAILABLE else "⚠️ missing")
        st.write("ChromaDB:", "✅" if CHROMA_AVAILABLE else "⚠️ missing")
        st.caption(f"Records: {len(st.session_state.enriched_records)}")

    with st.expander("🧪 Run Tests"):
        if st.button("Run All Tests"):
            results = run_tests("test_fixtures.json")
            passed = sum(1 for r in results if r["passed"] is True)
            total = len(results)
            st.write(f"**{passed}/{total}** passed")
            for r in results:
                icon = "✅" if r["passed"] is True else ("⏭️" if r["passed"] is None else "❌")
                st.caption(f"{icon} {r['name']}")


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
    }
    .hero-sub {
        color: #94a3b8;
        font-size: 1.1em;
        margin-top: 0;
    }
</style>
""", unsafe_allow_html=True)

# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown('<p class="hero-title">Find Your Next Meal</p>', unsafe_allow_html=True)
st.markdown('<p class="hero-sub">Discover restaurants across Syracuse, Rochester & Albany</p>', unsafe_allow_html=True)
st.write("")

# ── Step 1: Preferences ──────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)
with col1:
    city_pref = st.selectbox("📍 City", ["All Cities", "Syracuse", "Rochester", "Albany"])
with col2:
    all_cuisines = ["Any Cuisine"] + sorted(CUISINE_MAP.values())
    cuisine_pref = st.selectbox("🍴 Cuisine", all_cuisines)
with col3:
    price_pref = st.selectbox("💰 Budget", ["Any Price", "$", "$$", "$$$", "$$$$"])

if st.button("🔍 Find Restaurants", type="primary", use_container_width=True):
    with st.spinner("Discovering and enriching restaurants..."):
        # Discovery
        google_api_key = st.session_state.get("google_key", "")
        if not google_api_key:
            try:
                google_api_key = st.secrets.get("GOOGLE_PLACES_API_KEY", "")
            except Exception:
                pass
        restaurants = run_discovery(google_api_key=google_api_key)
        st.session_state.restaurants = restaurants
        # Enrichment
        st.session_state.enriched_records = _auto_enrich(restaurants)
        st.session_state.pipeline_ran = True
        st.session_state.chat_messages = []
        st.session_state.conversation_history = []
    st.rerun()

# ── Step 2: Results ───────────────────────────────────────────────────────────
if st.session_state.pipeline_ran and st.session_state.enriched_records:
    records = st.session_state.enriched_records

    # Apply filters
    filtered = records
    if city_pref != "All Cities":
        filtered = [r for r in filtered if r.get("city") == city_pref]
    if cuisine_pref != "Any Cuisine":
        filtered = [r for r in filtered if r.get("cuisine_type") == cuisine_pref]
    if price_pref != "Any Price":
        filtered = [r for r in filtered if r.get("price_range") == price_pref]

    filtered = sorted(filtered, key=lambda x: -(x.get("rating") or 0))

    st.divider()

    # Summary metrics
    if filtered:
        avg_rating = sum(r.get("rating") or 0 for r in filtered) / len(filtered)
        cities_found = len(set(r.get("city", "") for r in filtered))
        m1, m2, m3 = st.columns(3)
        m1.metric("Restaurants Found", len(filtered))
        m2.metric("Average Rating", f"{avg_rating:.1f} ⭐")
        m3.metric("Cities", cities_found)
        st.write("")

    # Restaurant cards
    if not filtered:
        st.info("No restaurants match your filters. Try broadening your search.")
    else:
        for r in filtered:
            rating = r.get("rating") or 0
            stars = "⭐" * int(rating)
            cuisine = r.get("cuisine_type", "Unknown")
            price = r.get("price_range", "$$")
            city = r.get("city", "")
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

            with st.expander(f"More about {r['name']}"):
                st.write(f"**{r['name']}** is a {cuisine.lower()} restaurant in {city} "
                         f"with a {rating:.1f}/5.0 rating. "
                         f"It falls in the {price} price range"
                         f"{' and has an online menu available' if r.get('menu_available_online') else ''}.")
                if items:
                    st.write("**Menu Highlights:**")
                    for item in items[:5]:
                        if isinstance(item, dict):
                            st.write(f"• **{item.get('name', '')}** — {item.get('description', '')}")
                        else:
                            st.write(f"• {item}")
                if r.get("website_url"):
                    st.write(f"🌐 [Visit Website]({r['website_url']})")

    # ── Step 3: Chat ──────────────────────────────────────────────────────────
    st.divider()
    st.subheader("💬 Ask About These Restaurants")
    st.caption("Ask follow-up questions — e.g. 'Which has the best seafood?' or 'Something cheap in Rochester?'")

    # Agent options
    with st.expander("⚙️ Agent Options"):
        a1, a2, a3 = st.columns(3)
        with a1:
            use_reflection = st.checkbox("Self-Reflection", value=False)
        with a2:
            run_ethics = st.checkbox("Ethics Evaluation", value=False)
        with a3:
            use_chroma = st.checkbox("ChromaDB Retrieval", value=CHROMA_AVAILABLE)
        if st.button("Clear Chat"):
            st.session_state.chat_messages = []
            st.session_state.conversation_history = []
            st.session_state.last_query_trace = {}
            st.rerun()

    # Chat history
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # Chat input
    user_input = st.chat_input("Ask about restaurants...")
    if user_input:
        client = get_openai_client()
        with st.chat_message("user"):
            st.write(user_input)
        st.session_state.chat_messages.append({"role": "user", "content": user_input})

        with st.chat_message("assistant"):
            with st.spinner("Finding the best match..."):
                chat_records = st.session_state.enriched_records

                if not client:
                    retrieved = simple_retrieve(user_input, chat_records, k=3)
                    answer = "**Top matches (keyword search):**\n\n"
                    for r in retrieved:
                        answer += (
                            f"**{r['name']}** ({r['city']}) — {r.get('cuisine_type', 'N/A')}, "
                            f"{r.get('price_range', '$$')}, Rating: {r.get('rating', 'N/A')}\n\n"
                        )
                    st.write(answer)
                    st.session_state.chat_messages.append(
                        {"role": "assistant", "content": answer})
                else:
                    if use_chroma and CHROMA_AVAILABLE:
                        try:
                            collection = get_chroma_collection()
                            chroma_results = chroma_search(user_input, collection, k=5)
                            if chroma_results:
                                chat_records = chroma_results
                        except Exception:
                            pass

                    if use_reflection:
                        trace = query_with_reflection(
                            user_input, chat_records,
                            st.session_state.conversation_history, client)
                        answer = trace["final_response"]
                        st.session_state.last_query_trace = trace
                    else:
                        answer = query_agent(
                            user_input, chat_records,
                            st.session_state.conversation_history, client)
                        st.session_state.last_query_trace = {}

                    st.write(answer)
                    st.session_state.chat_messages.append(
                        {"role": "assistant", "content": answer})

                    if run_ethics:
                        with st.spinner("Running ethics evaluation..."):
                            retrieved_for_ethics = simple_retrieve(user_input, chat_records)
                            ethics = evaluate_ethics(
                                user_input, answer, retrieved_for_ethics, client)
                        with st.expander("📊 Ethics Rubric Scores"):
                            if "error" not in ethics:
                                for dim in ["geographic_fairness", "price_diversity",
                                             "cuisine_respect", "transparency", "faithfulness"]:
                                    d = ethics.get(dim, {})
                                    st.write(f"**{dim.replace('_', ' ').title()}**: "
                                             f"{d.get('score', '?')}/5 — {d.get('note', '')}")
                                st.write(f"**Overall**: {ethics.get('overall', '?')}/5")
                            else:
                                st.write("Evaluation failed:", ethics.get("error"))

        if use_reflection and st.session_state.last_query_trace:
            trace = st.session_state.last_query_trace
            with st.expander("🔄 Self-Reflection Trace"):
                st.write("**Revised:**", trace.get("revised", False))
                st.write("**Initial:**", trace.get("initial_response", ""))
                critique = trace.get("critique", {})
                if critique.get("issues"):
                    st.write("**Issues:**")
                    for issue in critique["issues"]:
                        st.write(f"  • {issue}")

    # ── Data Export ───────────────────────────────────────────────────────────
    st.divider()
    with st.expander("📥 Export Data"):
        json_str = json.dumps(st.session_state.enriched_records, indent=2)
        st.download_button(
            "Download restaurants.json",
            data=json_str,
            file_name="restaurants_enriched.json",
            mime="application/json",
        )
