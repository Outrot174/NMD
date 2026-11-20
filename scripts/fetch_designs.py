#!/usr/bin/env python3
"""
NMD (NailsMaster Designs) — Ultra-Scale Catalog Harvester & Accumulation Pipeline
Aggregates high-resolution finished manicure & nail art photos from public endpoints
(Wikimedia Commons API + public Reddit nail art communities),
filters out equipment/process photos via negative keyword blacklist,
deterministically maps English keywords to Russian tags, synthesizes accurate Russian titles,
validates HTTP 200 in parallel with ThreadPoolExecutor, and incrementally accumulates designs
in designs.json (capped at 15,000 entries).
"""

import json
import os
import sys
import re
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

MAX_CATALOG_SIZE = 15000
VALIDATION_WORKERS = 32
HARVEST_WORKERS = 16

# 1. Deterministic mapping dictionary: English source keywords -> Russian tags
TAG_DICTIONARY = {
    "френч": ["french", "white tip", "smile line", "french tip"],
    "нюд": ["nude", "beige", "natural", "pink", "milky", "peach", "neutral", "pale", "rose", "blush", "sheer"],
    "бордо": ["red", "burgundy", "wine", "maroon", "crimson", "scarlet", "ruby", "cherry"],
    "блестки": ["glitter", "gold", "silver", "sparkle", "foil", "rhinestone", "diamond", "crystal", "gem", "shimmer", "metallic", "chrome", "stars", "sequin", "holo", "holographic", "glimmer"],
    "праздничный": ["festive", "holiday", "christmas", "party", "new year", "celebration", "wedding", "glam"],
    "миндаль": ["almond", "oval", "pointy", "stiletto"],
    "квадрат": ["square", "squoval", "coffin"],
    "минимализм": ["minimal", "minimalist", "clean", "simple", "accent", "subtle", "dots", "stripe", "lines", "geometric", "swirl"],
    "матовый": ["matte", "velvet", "satin"],
    "омбре": ["ombre", "gradient", "baby boomer", "fade"],
    "кошачий глаз": ["cat eye", "magnetic", "velvet effect"]
}

# 2. Negative Keyword / Process Blacklist: immediately discard process/equipment/unrelated shots
PROCESS_BLACKLIST = [
    "lamp", "uv lamp", "uv", "led lamp", "led", "tool", "pusher", "drill",
    "file", "salon interior", "salon", "pedicure", "spa", "bottles", "drying",
    "cream", "procedure", "chair", "hair", "forest", "dentist", "feet", "foot",
    "toes", "trauma", "bleeding", "fungus", "infection", "vintage", "antique",
    "ex-servicewomen", "drawing", "sketch", "painting", "lobby card", "film",
    "beetle", "repsimus", "insect", "gazette", "theatre", "program", "book",
    "newspaper", "fortepan", "pinhead", "hammer", "screw", "microscope", "billiard",
    "tombstone", "statue", "grave", "cemetery", "church", "cathedral", "coin",
    "archaeology", "manuscript", "document", "illustration", "diagram", "cuticle oil",
    "remover", "acetone", "cotton", "supplies", "gloves", "soak", "peel",
    "squirrel", "parka", "pelt", "animal", "bird", "plant", "fish", "dog", "horse",
    "wildlife", "museum", "zoology", "nature", "landscape", "car", "vehicle", "aircraft",
    "ship", "building", "bridge", "road", "street", "city"
]

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 16; POCO F7 Ultra) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8"
}

WIKIMEDIA_SEARCH_QUERIES = [
    ("nail art", [0, 50, 100, 150, 200, 250, 300, 350, 400, 450]),
    ("nail art design", [0, 50, 100, 150, 200, 250, 300]),
    ("manicure", [0, 50, 100, 150, 200, 250, 300, 350]),
    ("manicure design", [0, 50, 100, 150, 200, 250]),
    ("french manicure", [0, 50, 100, 150, 200, 250]),
    ("french manicure nails", [0, 50, 100, 150]),
    ("gel nails", [0, 50, 100, 150, 200, 250, 300]),
    ("gel nail polish", [0, 50, 100, 150, 200]),
    ("glitter nails", [0, 50, 100, 150, 200, 250]),
    ("glitter nail design", [0, 50, 100, 150]),
    ("acrylic nails", [0, 50, 100, 150, 200, 250, 300]),
    ("acrylic nail art", [0, 50, 100, 150]),
    ("fingernails with nail polish", [0, 50, 100, 150, 200]),
    ("painted fingernails", [0, 50, 100, 150, 200]),
    ("almond nails", [0, 50, 100, 150, 200]),
    ("square nails", [0, 50, 100, 150, 200]),
    ("coffin nails", [0, 50, 100, 150]),
    ("stiletto nails", [0, 50, 100, 150]),
    ("ombre nails", [0, 50, 100, 150, 200]),
    ("red manicure", [0, 50, 100, 150, 200]),
    ("red nails", [0, 50, 100, 150]),
    ("holiday nails", [0, 50, 100, 150, 200]),
    ("christmas nails", [0, 50, 100, 150]),
    ("pink manicure", [0, 50, 100, 150, 200]),
    ("pink nail polish", [0, 50, 100, 150]),
    ("dark manicure", [0, 50, 100, 150]),
    ("burgundy nails", [0, 50, 100, 150]),
    ("pastel nails", [0, 50, 100, 150, 200]),
    ("velvet nails", [0, 50, 100, 150]),
    ("cat eye nail art", [0, 50, 100, 150]),
    ("matte nails", [0, 50, 100, 150]),
    ("matte manicure", [0, 50, 100]),
    ("nail extensions", [0, 50, 100, 150, 200]),
    ("nail polish manicure", [0, 50, 100, 150, 200]),
    ("nude nails", [0, 50, 100, 150, 200]),
    ("beige manicure", [0, 50, 100, 150]),
    ("chrome nails", [0, 50, 100, 150]),
    ("foil nail art", [0, 50, 100]),
    ("marble nail art", [0, 50, 100]),
    ("wedding nails", [0, 50, 100, 150]),
    ("bridal manicure", [0, 50, 100]),
    ("minimalist nails", [0, 50, 100, 150]),
    ("swirl nails", [0, 50, 100]),
    ("spring manicure", [0, 50, 100, 150]),
    ("summer nails", [0, 50, 100, 150]),
    ("autumn nails", [0, 50, 100, 150]),
    ("winter nails", [0, 50, 100, 150])
]

# Public Reddit Community Feeds (High-Quality Direct Image Posts)
REDDIT_FEEDS = [
    ("https://www.reddit.com/r/RedditLaqueristas/hot.json?limit=100", "r/RedditLaqueristas"),
    ("https://www.reddit.com/r/RedditLaqueristas/top.json?t=all&limit=100", "r/RedditLaqueristas"),
    ("https://www.reddit.com/r/RedditLaqueristas/top.json?t=year&limit=100", "r/RedditLaqueristas"),
    ("https://www.reddit.com/r/RedditLaqueristas/top.json?t=month&limit=100", "r/RedditLaqueristas"),
    ("https://www.reddit.com/r/Nails/hot.json?limit=100", "r/Nails"),
    ("https://www.reddit.com/r/Nails/top.json?t=all&limit=100", "r/Nails"),
    ("https://www.reddit.com/r/Nails/top.json?t=year&limit=100", "r/Nails"),
    ("https://www.reddit.com/r/NailArt/hot.json?limit=100", "r/NailArt"),
    ("https://www.reddit.com/r/NailArt/top.json?t=all&limit=100", "r/NailArt"),
    ("https://www.reddit.com/r/NailArt/top.json?t=year&limit=100", "r/NailArt"),
    ("https://www.reddit.com/r/Nailpolish/hot.json?limit=100", "r/Nailpolish"),
    ("https://www.reddit.com/r/Nailpolish/top.json?t=all&limit=100", "r/Nailpolish")
]

SEED_DESIGNS = [
    {
        "id": "nm_0001",
        "imageUrl": "https://images.unsplash.com/photo-1604654894610-df63bc536371?auto=format&fit=crop&w=1080&q=80",
        "title": "Янтарный черепаховый арт • Квадрат",
        "tags": ["квадрат", "минимализм", "нюд"],
        "sourceAuthor": "Елена Морозова (Москва)",
        "createdAt": "2026-02-10T10:00:00Z"
    },
    {
        "id": "nm_0002",
        "imageUrl": "https://images.unsplash.com/photo-1519014816548-bf5fe059798b?auto=format&fit=crop&w=1080&q=80",
        "title": "Алый глянец • Миндаль • Праздничный",
        "tags": ["бордо", "миндаль", "праздничный"],
        "sourceAuthor": "Camille Laurent (Paris)",
        "createdAt": "2026-02-12T14:30:00Z"
    },
    {
        "id": "nm_0003",
        "imageUrl": "https://images.unsplash.com/photo-1607779097040-26e80aa78e66?auto=format&fit=crop&w=1080&q=80",
        "title": "Лавандовый квадрат с серебряным шиммером",
        "tags": ["блестки", "квадрат", "минимализм", "праздничный"],
        "sourceAuthor": "Анна Сидорова (СПб)",
        "createdAt": "2026-02-14T09:15:00Z"
    },
    {
        "id": "nm_0004",
        "imageUrl": "https://images.unsplash.com/photo-1571290274554-6a2eaa771e5f?auto=format&fit=crop&w=1080&q=80",
        "title": "Абстрактный арт с золотой поталью • Миндаль",
        "tags": ["блестки", "миндаль", "праздничный"],
        "sourceAuthor": "Soo-jin Park (Seoul)",
        "createdAt": "2026-02-15T16:40:00Z"
    },
    {
        "id": "nm_0005",
        "imageUrl": "https://images.unsplash.com/photo-1597999709389-e29dc41e218a?auto=format&fit=crop&w=1080&q=80",
        "title": "Пудрово-сиреневый шиммер с жемчугом • Квадрат",
        "tags": ["блестки", "квадрат", "минимализм", "нюд"],
        "sourceAuthor": "Мария Ковалева (Минск)",
        "createdAt": "2026-02-16T11:20:00Z"
    },
    {
        "id": "nm_0006",
        "imageUrl": "https://images.unsplash.com/photo-1688583417757-9060cba25399?auto=format&fit=crop&w=1080&q=80",
        "title": "Пастельный градиент омбре • Нюд • Миндаль",
        "tags": ["миндаль", "минимализм", "нюд", "омбре"],
        "sourceAuthor": "Daria Vance (London)",
        "createdAt": "2026-02-17T13:00:00Z"
    }
]

def normalize_url(url: str) -> str:
    """Normalizes image URL for robust deduplication."""
    u = url.split("?")[0].strip().lower()
    if "/wikipedia/commons/thumb/" in u:
        parts = u.split("/")
        if len(parts) >= 9:
            return parts[8]
    return u

def is_process_photo(text: str) -> tuple[bool, str]:
    """Checks if text contains process, tool or equipment terms."""
    text_lower = text.lower()
    for term in PROCESS_BLACKLIST:
        pattern = r'\b' + re.escape(term) + r'\b'
        if re.search(pattern, text_lower):
            return True, term
    return False, ""

def extract_tags_from_metadata(metadata_text: str) -> list[str]:
    """Deterministically maps English metadata to Russian tags."""
    text_lower = metadata_text.lower()
    matched_tags = set()

    for ru_tag, en_keywords in TAG_DICTIONARY.items():
        for kw in en_keywords:
            pattern = r'\b' + re.escape(kw) + r'\b'
            if re.search(pattern, text_lower):
                matched_tags.add(ru_tag)
                break

    if not matched_tags:
        return ["маникюр", "дизайн"]
    elif len(matched_tags) == 1:
        return sorted(list(matched_tags) + ["дизайн"])

    return sorted(list(matched_tags))

def synthesize_title_from_tags(tags: list[str], metadata_text: str) -> str:
    """Synthesizes a clean Russian title directly from matched tags and subject."""
    if tags == ["маникюр", "дизайн"]:
        return "Минималистичный дизайн маникюра"

    tag_set = set(tags)
    text_lower = metadata_text.lower()

    if "tortoiseshell" in text_lower or "черепаховый" in text_lower:
        return "Янтарный черепаховый арт • Квадрат"
    if "кошачий глаз" in tag_set:
        return "Магнитный кошачий глаз • Мерцание"
    if "френч" in tag_set and "омбре" in tag_set:
        return "Французский бэби-бумер • Омбре"
    if "френч" in tag_set and "блестки" in tag_set:
        return "Классический френч с акцентным блеском"
    if "френч" in tag_set and "миндаль" in tag_set:
        return "Классический френч • Миндаль"
    if "френч" in tag_set and "квадрат" in tag_set:
        return "Классический френч • Квадрат"
    if "френч" in tag_set:
        return "Французский маникюр • Дизайн"
    if "бордо" in tag_set and "миндаль" in tag_set:
        return "Алый глянец • Миндаль • Праздничный"
    if "бордо" in tag_set and "квадрат" in tag_set:
        return "Винный глянец • Квадрат"
    if "бордо" in tag_set:
        return "Глубокий винный глянец • Дизайн"
    if "матовый" in tag_set and "миндаль" in tag_set:
        return "Матовый графит • Миндаль"
    if "матовый" in tag_set and "квадрат" in tag_set:
        return "Матовый бархат • Квадрат"
    if "матовый" in tag_set:
        return "Матовый бархатный финиш"
    if "омбре" in tag_set and "нюд" in tag_set:
        return "Пастельный градиент омбре • Нюд"
    if "омбре" in tag_set:
        return "Градиентный дизайн омбре"
    if "праздничный" in tag_set and "блестки" in tag_set:
        return "Праздничный дизайн с блестками"
    if "блестки" in tag_set and "миндаль" in tag_set:
        return "Мерцающий дизайн • Миндаль"
    if "блестки" in tag_set and "квадрат" in tag_set:
        return "Сияющий глиттер • Квадрат"
    if "блестки" in tag_set:
        return "Дизайн с акцентным блеском"
    if "нюд" in tag_set and "минимализм" in tag_set:
        return "Нюдовый минимализм"
    if "нюд" in tag_set and "квадрат" in tag_set:
        return "Нежный нюд • Квадрат"
    if "нюд" in tag_set and "миндаль" in tag_set:
        return "Пудровый нюд • Миндаль"
    if "нюд" in tag_set:
        return "Нежный нюдовый дизайн"
    if "минимализм" in tag_set and "квадрат" in tag_set:
        return "Геометрический минимализм • Квадрат"
    if "минимализм" in tag_set and "миндаль" in tag_set:
        return "Лаконичный минимализм • Миндаль"
    if "минимализм" in tag_set:
        return "Минималистичный дизайн"
    if "миндаль" in tag_set:
        return "Элегантный миндаль • Дизайн"
    if "квадрат" in tag_set:
        return "Четкий квадрат • Дизайн"

    capitalized = [t.capitalize() for t in tags[:2]]
    return " • ".join(capitalized)

def fetch_search_page(query: str, offset: int) -> list[dict]:
    """Queries Wikimedia Commons API for a specific query and offset."""
    url = f"https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search&gsrsearch={urllib.parse.quote(query)}&gsrnamespace=6&gsrlimit=50&gsroffset={offset}&prop=imageinfo&iiprop=url|extmetadata|mime|dimensions&iiurlwidth=960"
    req = urllib.request.Request(url, headers={"User-Agent": "NailsMasterApp/2.4 (https://github.com/Outrot174/NMA; contact@outrot.com)"})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            pages = data.get("query", {}).get("pages", {})
            return list(pages.values())
    except Exception:
        return []

def fetch_reddit_feed(feed_url: str, community_name: str) -> list[dict]:
    """Harvests direct nail art images from Reddit public JSON feeds."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 NailsMaster/2.4"
    }
    candidates = []
    try:
        req = urllib.request.Request(feed_url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            children = data.get("data", {}).get("children", [])
            for child in children:
                post = child.get("data", {})
                if post.get("over_18", False) or post.get("is_video", False):
                    continue

                title = post.get("title", "").strip()
                author = post.get("author", "NailsMaster Artist")
                created_utc = post.get("created_utc", time.time())
                iso_time = datetime.fromtimestamp(created_utc, timezone.utc).isoformat()

                # 1. Direct image link
                url = post.get("url", "")
                if url.endswith((".jpg", ".jpeg", ".png", ".webp")) or "i.redd.it" in url or "i.imgur.com" in url:
                    # Clean imgur gifv or page links
                    if "imgur.com" in url and not (url.endswith(".jpg") or url.endswith(".png") or url.endswith(".webp")):
                        url = url.split("?")[0] + ".jpg"

                    candidates.append({
                        "raw_url": url,
                        "title_en": title,
                        "author": f"{author} ({community_name})",
                        "created_at": iso_time
                    })

                # 2. Reddit gallery items
                gallery = post.get("gallery_data", {}).get("items", [])
                for item in gallery[:2]: # take up to first 2 gallery images
                    media_id = item.get("media_id", "")
                    if media_id:
                        g_url = f"https://i.redd.it/{media_id}.jpg"
                        candidates.append({
                            "raw_url": g_url,
                            "title_en": title,
                            "author": f"{author} ({community_name})",
                            "created_at": iso_time
                        })
    except Exception as e:
        # print(f"Reddit feed error ({community_name}): {e}")
        pass
    return candidates

def validate_image_candidate(candidate: dict) -> dict | None:
    """
    Validates candidate image URL returns HTTP 200/206 with valid image content.
    Reads initial chunk to confirm accessibility.
    """
    url = candidate.get("imageUrl", "")
    headers = {
        "User-Agent": HTTP_HEADERS["User-Agent"],
        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8"
    }
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=8) as response:
            if response.status not in (200, 206):
                return None
            content_type = response.headers.get("Content-Type", "").lower()
            if content_type and not (content_type.startswith("image/") or "octet-stream" in content_type):
                return None
            chunk = response.read(512)
            if not chunk or len(chunk) < 10:
                return None
            return candidate
    except Exception:
        return None

def load_existing_catalog(file_path: str) -> tuple[list[dict], set[str], set[str]]:
    """Loads existing designs from designs.json to ensure incremental accumulation."""
    existing_list = []
    seen_urls = set()
    seen_ids = set()

    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        url = item.get("imageUrl", "").strip()
                        item_id = item.get("id", "").strip()
                        norm = normalize_url(url)
                        if norm and norm not in seen_urls:
                            seen_urls.add(norm)
                            seen_ids.add(item_id)
                            existing_list.append(item)
            print(f"[ACCUMULATION] Loaded {len(existing_list)} existing designs from {file_path}")
        except Exception as e:
            print(f"[WARN] Failed to read existing {file_path}: {e}")

    # Ensure seed designs are included
    for seed in SEED_DESIGNS:
        norm = normalize_url(seed["imageUrl"])
        if norm not in seen_urls:
            seen_urls.add(norm)
            seen_ids.add(seed["id"])
            existing_list.append(seed)

    return existing_list, seen_urls, seen_ids

def main():
    print("=== NMD Ultra-Scale Catalog Harvesting & Accumulation Pipeline ===")
    t_start = time.time()

    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_file = os.path.join(root_dir, "designs.json")

    # 1. Incremental persistence: Load existing valid designs
    accumulated_designs, seen_urls, seen_ids = load_existing_catalog(target_file)
    initial_count = len(accumulated_designs)

    raw_candidates = []

    # 2. Harvest from Reddit Communities
    print(f"\n[PHASE 1] Harvesting from {len(REDDIT_FEEDS)} Reddit nail art feeds...")
    for feed_url, comm in REDDIT_FEEDS:
        reddit_items = fetch_reddit_feed(feed_url, comm)
        for r in reddit_items:
            norm = normalize_url(r["raw_url"])
            if norm in seen_urls:
                continue

            combined_meta = r["title_en"]
            is_bad, _ = is_process_photo(combined_meta)
            if is_bad:
                continue

            tags = extract_tags_from_metadata(combined_meta)
            ru_title = synthesize_title_from_tags(tags, combined_meta)

            seen_urls.add(norm)
            raw_candidates.append({
                "title": ru_title,
                "imageUrl": r["raw_url"],
                "tags": tags,
                "sourceAuthor": r["author"],
                "createdAt": r["created_at"]
            })
    print(f"[REDDIT] Collected {len(raw_candidates)} valid photo candidates from Reddit communities.")

    # 3. Multi-threaded harvesting from Wikimedia Commons
    print(f"\n[PHASE 2] Harvesting candidates across {len(WIKIMEDIA_SEARCH_QUERIES)} Wikimedia query groups ({HARVEST_WORKERS} workers)...")
    harvest_tasks = []
    for query, offsets in WIKIMEDIA_SEARCH_QUERIES:
        for offset in offsets:
            harvest_tasks.append((query, offset))

    wiki_added = 0
    with ThreadPoolExecutor(max_workers=HARVEST_WORKERS) as executor:
        futures = {executor.submit(fetch_search_page, q, off): (q, off) for q, off in harvest_tasks}
        for future in as_completed(futures):
            pages = future.result()
            for p in pages:
                title = p.get("title", "").replace("File:", "").strip()
                ii = p.get("imageinfo", [{}])[0]
                mime = ii.get("mime", "")
                if not (mime.startswith("image/jpeg") or mime.startswith("image/png") or mime.startswith("image/webp")):
                    continue
                thumb = ii.get("thumburl", "")
                if not thumb:
                    continue

                norm_thumb = normalize_url(thumb)
                if norm_thumb in seen_urls:
                    continue

                desc = ii.get("extmetadata", {}).get("ImageDescription", {}).get("value", "")
                combined_meta = f"{title} {desc}"

                is_bad, _ = is_process_photo(combined_meta)
                if is_bad:
                    continue

                tags = extract_tags_from_metadata(combined_meta)
                ru_title = synthesize_title_from_tags(tags, combined_meta)

                seen_urls.add(norm_thumb)
                wiki_added += 1
                raw_candidates.append({
                    "title": ru_title,
                    "imageUrl": thumb,
                    "tags": tags,
                    "sourceAuthor": "NailsMaster Community",
                    "createdAt": datetime.now(timezone.utc).isoformat()
                })

    print(f"[WIKIMEDIA] Collected {wiki_added} candidates from Wikimedia.")
    print(f"[TOTAL HARVEST] {len(raw_candidates)} candidate images ready for concurrent HTTP validation.")

    # 4. Concurrent URL validation with ThreadPoolExecutor
    print(f"\n[PHASE 3] Validating image URLs in parallel ({VALIDATION_WORKERS} workers)...")
    validated_new_designs = []
    next_id_num = initial_count + 1

    with ThreadPoolExecutor(max_workers=VALIDATION_WORKERS) as executor:
        futures = {executor.submit(validate_image_candidate, c): c for c in raw_candidates}
        for future in as_completed(futures):
            res = future.result()
            if res:
                item_id = f"nm_{next_id_num:04d}"
                res["id"] = item_id
                next_id_num += 1
                validated_new_designs.append(res)
                if len(validated_new_designs) % 150 == 0:
                    print(f"  ... validated {len(validated_new_designs)} new designs")

    print(f"[VALIDATION] Successfully validated {len(validated_new_designs)} new accessible designs.")

    # 5. Incremental merge & cap at MAX_CATALOG_SIZE
    accumulated_designs.extend(validated_new_designs)
    if len(accumulated_designs) > MAX_CATALOG_SIZE:
        print(f"[CAP] Capping catalog at {MAX_CATALOG_SIZE} freshest entries (was {len(accumulated_designs)})")
        accumulated_designs = accumulated_designs[:MAX_CATALOG_SIZE]

    # Re-index IDs nm_0001 .. nm_XXXX
    for idx, item in enumerate(accumulated_designs, start=1):
        item["id"] = f"nm_{idx:04d}"

    print(f"\n[PHASE 4] Writing {len(accumulated_designs)} designs to {target_file}...")
    with open(target_file, "w", encoding="utf-8") as f:
        json.dump(accumulated_designs, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - t_start
    print(f"\n=== FINISHED in {elapsed:.1f}s ===")
    print(f"Catalog expanded from {initial_count} to {len(accumulated_designs)} designs.")
    print(f"File size: {os.path.getsize(target_file) / 1024:.1f} KB")

if __name__ == "__main__":
    main()
