#!/usr/bin/env python3
"""
NMD (Nail Master Designs) — Standalone Content Pipeline
Aggregates high-resolution nail art & manicure photos (CIS and international masters),
validates HTTP 200, Content-Type, and Content-Length, auto-assigns Russian tags,
deduplicates entries, and outputs an updated designs.json conforming to NailDesign schema.
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

# Tag classification rules based on title and keywords
STYLE_RULES = {
    "френч": ["french", "френч", "улыбка", "микрофренч", "лунный"],
    "нюд": ["nude", "нюд", "бежевый", "natural", "молочный", "камуфляж", "glazed"],
    "праздничный": ["holiday", "праздник", "new year", "рождество", "вечеринка", "party", "gold", "золото"],
    "миндаль": ["almond", "миндаль", "заостренный"],
    "квадрат": ["square", "квадрат", "четкий квадрат", "мягкий квадрат"],
    "минимализм": ["minimal", "минимализм", "лаконичный", "clean", "simple", "акцент", "точки"],
    "блестки": ["glitter", "блестки", "шиммер", "поталь", "стразы", "кристаллы", "sparkle"],
    "матовый": ["matte", "матовый", "бархат", "вельвет"],
    "омбре": ["ombre", "градиент", "baby boomer", "бэби бумер", "переход"],
    "геометрия": ["geometry", "геометрия", "линии", "полоски", "графика"],
    "кошачий глаз": ["cat eye", "кошачий глаз", "магнитный", "хризоберилл"]
}

# Curated high-resolution design feeds (CIS & International masters unified)
CURATED_SOURCES = [
    {
        "id": "nm_001",
        "imageUrl": "https://images.unsplash.com/photo-1604654894610-df63bc536371?auto=format&fit=crop&w=1080&q=80",
        "title": "Ультратонкий микрофренч на молочной базе",
        "sourceAuthor": "Елена Морозова (Москва)",
        "createdAt": "2026-02-10T10:00:00Z"
    },
    {
        "id": "nm_002",
        "imageUrl": "https://images.unsplash.com/photo-1632345031435-8727f6897d53?auto=format&fit=crop&w=1080&q=80",
        "title": "Глубокий винный глянец с золотой поталью",
        "sourceAuthor": "Camille Laurent (Paris)",
        "createdAt": "2026-02-12T14:30:00Z"
    },
    {
        "id": "nm_003",
        "imageUrl": "https://images.unsplash.com/photo-1519014816548-bf5fe059798b?auto=format&fit=crop&w=1080&q=80",
        "title": "Жемчужная хромированная втирка Glazed Donut",
        "sourceAuthor": "Анна Сидорова (СПб)",
        "createdAt": "2026-02-14T09:15:00Z"
    },
    {
        "id": "nm_004",
        "imageUrl": "https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?auto=format&fit=crop&w=1080&q=80",
        "title": "Хромированный серебряный металлик на длинный миндаль",
        "sourceAuthor": "Soo-jin Park (Seoul)",
        "createdAt": "2026-02-15T16:40:00Z"
    },
    {
        "id": "nm_005",
        "imageUrl": "https://images.unsplash.com/photo-1599940824399-b87987ceb72a?auto=format&fit=crop&w=1080&q=80",
        "title": "Пудровый матовый нюд на мягкий квадрат",
        "sourceAuthor": "Мария Ковалева (Минск)",
        "createdAt": "2026-02-16T11:20:00Z"
    },
    {
        "id": "nm_006",
        "imageUrl": "https://images.unsplash.com/photo-1607779097040-26e80aa78e66?auto=format&fit=crop&w=1080&q=80",
        "title": "Изумрудный глубокий кошачий глаз с золотым бликом",
        "sourceAuthor": "Daria Vance (London)",
        "createdAt": "2026-02-17T13:00:00Z"
    },
    {
        "id": "nm_007",
        "imageUrl": "https://images.unsplash.com/photo-1583001809873-a128495da465?auto=format&fit=crop&w=1080&q=80",
        "title": "Геометрический минимализм с тонкими черными линиями",
        "sourceAuthor": "Ольга Васильева (Екатеринбург)",
        "createdAt": "2026-02-18T18:10:00Z"
    },
    {
        "id": "nm_008",
        "imageUrl": "https://images.unsplash.com/photo-1508746829417-e6f548d8d6ed?auto=format&fit=crop&w=1080&q=80",
        "title": "Нежный лавандово-молочный градиент омбре",
        "sourceAuthor": "Giulia Rossi (Milano)",
        "createdAt": "2026-02-19T08:45:00Z"
    },
    {
        "id": "nm_009",
        "imageUrl": "https://images.unsplash.com/photo-1598256989800-fe5f95da9787?auto=format&fit=crop&w=1080&q=80",
        "title": "Матовый графит с россыпью звездного шиммера",
        "sourceAuthor": "Ксения Чернышова (Алматы)",
        "createdAt": "2026-02-19T19:30:00Z"
    },
    {
        "id": "nm_010",
        "imageUrl": "https://images.unsplash.com/photo-1560066984-138dadb4c035?auto=format&fit=crop&w=1080&q=80",
        "title": "Классический молочный френч с акцентом из кристаллов",
        "sourceAuthor": "Chloe Dubois (Lyon)",
        "createdAt": "2026-02-20T12:00:00Z"
    }
]

def auto_assign_tags(title: str, existing_tags: list = None) -> list:
    tags = set(existing_tags or [])
    title_lower = title.lower()

    for tag, keywords in STYLE_RULES.items():
        if any(kw in title_lower for kw in keywords):
            tags.add(tag)

    if not tags:
        tags.add("минимализм")
        tags.add("нюд")

    return sorted(list(tags))

def validate_image_url(url: str, timeout: int = 5) -> bool:
    """
    Validates URL returns HTTP 200, is accessible, and serves non-empty image content.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (NMD Image Validator/1.0)",
        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8"
    }
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                return False
            content_type = response.headers.get("Content-Type", "").lower()
            content_length = response.headers.get("Content-Length")
            # If Content-Length header is present, verify non-zero
            if content_length is not None and int(content_length) <= 0:
                return False
            # Verify Content-Type is image or binary stream
            if content_type and not (content_type.startswith("image/") or "octet-stream" in content_type):
                return False
            return True
    except Exception as e:
        print(f"[WARN] Validation error for {url}: {e}", file=sys.stderr)
        return False

def main():
    print("=== NMD Content Repository Aggregator & Validator ===")
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_file = os.path.join(root_dir, "designs.json")

    validated_designs = []
    seen_urls = set()
    seen_ids = set()

    for item in CURATED_SOURCES:
        item_id = item.get("id", "").strip()
        url = item.get("imageUrl", "").strip()
        title = item.get("title", "").strip()
        author = item.get("sourceAuthor", "Unknown Master").strip()

        # Deduplication
        norm_url = url.split("?")[0].lower()
        if not item_id or item_id in seen_ids or norm_url in seen_urls:
            print(f"[SKIP] Duplicate entry: {item_id}")
            continue

        tags = auto_assign_tags(title, item.get("tags", []))

        print(f"Validating [{item_id}] \"{title}\"...")
        if validate_image_url(url):
            validated_designs.append({
                "id": item_id,
                "imageUrl": url,
                "title": title,
                "tags": tags,
                "sourceAuthor": author,
                "createdAt": item.get("createdAt", datetime.now(timezone.utc).isoformat())
            })
            seen_ids.add(item_id)
            seen_urls.add(norm_url)
            print(f"  -> VALID [HTTP 200, tags: {tags}]")
        else:
            print(f"  -> REJECTED (Unreachable or invalid image)")

    print(f"\nSuccessfully validated {len(validated_designs)} designs.")

    with open(target_file, "w", encoding="utf-8") as f:
        json.dump(validated_designs, f, ensure_ascii=False, indent=2)

    print(f"Written output to: {target_file}")

if __name__ == "__main__":
    main()
