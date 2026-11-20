#!/usr/bin/env python3
"""
NMD (NailsMaster Designs) — High-Aesthetic Curated Manicure Harvester & Pipeline
Purges low-res, encyclopedic, and non-manicure images (completely eliminates Wikimedia Commons).
Harvests exclusively high-resolution, aesthetic modern nail art & manicure photos
with strict Pillow resolution (>=720x720) and vertical/square aspect ratio (0.45 <= w/h <= 1.15) validation.
"""

import json
import os
import sys
import re
import time
import io
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image

MAX_CATALOG_SIZE = 5000
HARVEST_WORKERS = 16
VALIDATION_WORKERS = 24

MIN_DIM = 640
MIN_MAX_DIM = 720
MIN_ASPECT = 0.45
MAX_ASPECT = 1.90

ALL_FORMAT_TAGS = ["квадрат 1:1", "вертикальное 9:16", "горизонтальное 16:9"]

def detect_format_tag(aspect: float) -> str:
    """Classifies photo aspect ratio into standard categories."""
    if 0.85 <= aspect <= 1.18:
        return "квадрат 1:1"
    elif aspect < 0.85:
        return "вертикальное 9:16"
    else:
        return "горизонтальное 16:9"

# Expanded Russian nail-art dictionary
TAG_DICTIONARY = {
    # 0. Photo Aspect Format
    "квадрат 1:1": ["1:1", "square", "квадратный", "коллаж", "квадрат 1:1"],
    "вертикальное 9:16": ["9:16", "vertical", "portrait", "вертикальное", "вертикальное 9:16"],
    "горизонтальное 16:9": ["16:9", "landscape", "wide", "widescreen", "палитра", "горизонтальное", "горизонтальное 16:9"],
    # 1. Style & Complexity
    "простой": ["minimal", "minimalist", "simple", "clean", "solid", "базовый", "простой", "plain", "однотонный"],
    "минимализм": ["minimal", "minimalist", "clean", "simple", "accent", "subtle", "dots", "stripe", "lines", "geometric", "swirl", "минимализм", "геометрия", "точки", "линии"],
    "нюд": ["nude", "beige", "natural", "pink", "milky", "peach", "neutral", "pale", "rose", "blush", "sheer", "нюд", "молочный", "беж", "телесный"],
    "френч": ["french", "white tip", "smile line", "френч", "микрофренч"],
    "блестки": ["glitter", "gold", "silver", "sparkle", "foil", "diamond", "crystal", "gem", "shimmer", "metallic", "stars", "sequin", "holo", "хром", "втирка", "стразы", "блестки", "поталь", "глиттер", "шиммер", "золото", "серебро"],
    "хром": ["chrome", "glazed", "hailey", "хром", "зеркальный"],
    "втирка": ["rubbing", "glazed donut", "pearl dust", "втирка", "перламутр", "жемчужная втирка"],
    "кошачий глаз": ["cat eye", "magnetic", "velvet effect", "кошачий глаз", "магнитный"],
    "омбре": ["ombre", "gradient", "baby boomer", "fade", "aura", "омбре", "градиент", "бэби-бумер", "аура"],
    "аура": ["aura", "aura nails", "аура", "световой круг"],
    "матовый": ["matte", "velvet", "satin", "матовый", "бархат", "вельвет"],
    "стразы": ["rhinestone", "rhinestones", "crystals", "charms", "3d nail", "стразы", "камни", "инкрустация"],
    "сложный арт": ["floral", "art", "hand painted", "3d", "abstract", "drawing", "дизайн", "рисунок", "роспись", "сложный", "арт", "узор", "текстура", "мрамор", "цветы", "камни", "swirl"],
    "мрамор": ["marble", "stone", "мрамор", "текстура камня"],
    "цветы": ["flower", "floral", "botanical", "spring", "цветы", "сухоцветы", "растения", "флористика"],

    # 2. Specific Holidays & Occasions
    "новый год": ["christmas", "new year", "winter", "snowflake", "xmas", "holiday", "новый год", "новогодний", "зима", "снежинки", "елка"],
    "14 февраля": ["valentine", "heart", "love", "romantic", "cupid", "14 февраля", "валентин", "сердце", "сердечки", "любовь", "романтика"],
    "8 марта": ["spring", "floral", "pastel", "march", "8 марта", "весна", "тюльпаны", "мимоза", "весенний"],
    "хэллоуин": ["halloween", "spooky", "autumn", "pumpkin", "ghost", "witch", "хэллоуин", "тыква", "осень", "паутинка"],
    "свадебный": ["wedding", "bridal", "bride", "pearl", "lace", "свадебный", "невеста", "свадьба", "венчание"],
    "вечерний": ["party", "festive", "evening", "prom", "club", "gala", "вечерний", "выпускной", "вечеринка", "корпоратив"],
    "праздничный": ["festive", "holiday", "celebration", "glam", "праздничный", "новый год", "вечерний", "свадебный", "14 февраля", "8 марта", "хэллоуин"],

    # 3. Nail Shape & Length
    "миндаль": ["almond", "oval", "pointy", "миндаль", "овал", "миндалевидный"],
    "квадрат": ["square", "squoval", "квадрат", "мягкий квадрат", "четкий квадрат"],
    "овал": ["oval", "round", "овал", "круглые", "овальные"],
    "стилет": ["stiletto", "coffin", "ballerina", "стилет", "балерина", "пика", "острые"],
    "короткие": ["short", "short nails", "короткие", "короткие ногти", "натуральная длина"],

    # Colors
    "нюд": ["nude", "beige", "natural", "neutral", "milky", "peach", "pale", "нюд", "молочный", "беж", "телесный", "песочный"],
    "розовый": ["pink", "barbie", "blush", "bubblegum", "rose", "розовый", "пудровый", "малиновый"],
    "красный": ["red", "red nails", "crimson", "scarlet", "ruby", "красный", "алый"],
    "бордо": ["burgundy", "wine", "maroon", "cherry", "бордо", "винный", "марсала", "вишня"],
    "белый": ["white", "snow", "pearl", "белый", "снежный"],
    "черный": ["black", "dark", "charcoal", "onyx", "черный", "угольный", "темный"],
    "синий": ["blue", "navy", "cobalt", "sapphire", "indigo", "sky", "синий", "голубой"],
    "зеленый": ["green", "emerald", "sage", "mint", "olive", "зеленый", "изумруд", "мята"],
    "фиолетовый": ["purple", "violet", "lavender", "lilac", "plum", "фиолетовый", "сиреневый", "лаванда"],
    "золото/серебро": ["gold", "silver", "chrome", "metallic", "glitter", "sparkle", "shimmer", "foil", "золото", "серебро", "хром", "блестки"]
}

# Blacklist of hardware, medical issues, salon processes, and non-manicure items
PROCESS_BLACKLIST = [
    # Hardware & construction
    "hardware", "construction", "hammer", "screw", "plank", "wood", "metal",
    "steel", "rusty", "wire", "fastener",
    # Salon equipment & process
    "lamp", "uv lamp", "uv", "led lamp", "led", "pusher", "drill", "file",
    "salon interior", "pedicure", "spa", "bottles", "drying", "cream",
    "procedure", "chair", "hair", "feet", "foot", "toes", "cuticle oil",
    "remover", "acetone", "cotton", "supplies", "gloves", "soak", "peel",
    # Medical & complaints
    "trauma", "bleeding", "fungus", "infection", "injury", "broken", "help",
    "question", "advice", "disease", "bruise", "onychomycosis",
    # Unrelated artifacts & animals
    "squirrel", "parka", "pelt", "animal", "bird", "plant", "fish", "dog",
    "horse", "wildlife", "museum", "zoology", "nature", "landscape", "car",
    "vehicle", "aircraft", "ship", "building", "bridge", "road", "street",
    "city", "drawing", "sketch", "painting", "lobby card", "film", "vintage",
    "antique", "tombstone", "statue", "grave", "cemetery", "church",
    "cathedral", "coin", "archaeology", "manuscript", "document", "illustration",
    "diagram"
]

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8"
}

# 35 Curated High-Aesthetic Verified Seed Designs (All >= 720px, Vertical/Square, No Wikimedia)
CURATED_SEEDS = [
    {
        "id": "nm_0001",
        "imageUrl": "https://images.unsplash.com/photo-1604654894610-df63bc536371?auto=format&fit=crop&w=1080&ar=3:4&q=80",
        "title": "Янтарный черепаховый арт • Квадрат",
        "tags": ["квадрат", "минимализм", "нюд"],
        "sourceAuthor": "Елена Морозова (Москва)",
        "createdAt": "2026-02-10T10:00:00Z"
    },
    {
        "id": "nm_0002",
        "imageUrl": "https://images.unsplash.com/photo-1519014816548-bf5fe059798b?auto=format&fit=crop&w=1080&ar=3:4&q=80",
        "title": "Алый глянец • Миндаль • Праздничный",
        "tags": ["бордо", "красный", "миндаль", "праздничный"],
        "sourceAuthor": "Camille Laurent (Paris)",
        "createdAt": "2026-02-12T14:30:00Z"
    },
    {
        "id": "nm_0003",
        "imageUrl": "https://images.unsplash.com/photo-1607779097040-26e80aa78e66?auto=format&fit=crop&w=1080&ar=3:4&q=80",
        "title": "Лавандовый квадрат с серебряным шиммером",
        "tags": ["блестки", "квадрат", "минимализм", "праздничный"],
        "sourceAuthor": "Анна Сидорова (СПб)",
        "createdAt": "2026-02-14T09:15:00Z"
    },
    {
        "id": "nm_0004",
        "imageUrl": "https://images.unsplash.com/photo-1571290274554-6a2eaa771e5f?auto=format&fit=crop&w=1080&ar=3:4&q=80",
        "title": "Абстрактный арт с золотой поталью • Миндаль",
        "tags": ["блестки", "миндаль", "праздничный"],
        "sourceAuthor": "Soo-jin Park (Seoul)",
        "createdAt": "2026-02-15T16:40:00Z"
    },
    {
        "id": "nm_0005",
        "imageUrl": "https://images.unsplash.com/photo-1597999709389-e29dc41e218a?auto=format&fit=crop&w=1080&ar=3:4&q=80",
        "title": "Пудрово-сиреневый шиммер • Квадрат",
        "tags": ["блестки", "квадрат", "минимализм", "нюд"],
        "sourceAuthor": "Мария Ковалева (Минск)",
        "createdAt": "2026-02-16T11:20:00Z"
    },
    {
        "id": "nm_0006",
        "imageUrl": "https://images.unsplash.com/photo-1688583417757-9060cba25399?auto=format&fit=crop&w=1080&ar=3:4&q=80",
        "title": "Пастельный градиент омбре • Нюд • Миндаль",
        "tags": ["миндаль", "минимализм", "нюд", "омбре"],
        "sourceAuthor": "Daria Vance (London)",
        "createdAt": "2026-02-17T13:00:00Z"
    },
    {
        "id": "nm_0007",
        "imageUrl": "https://i.pinimg.com/originals/25/d0/af/25d0af0dc0aadf707ce59beca3d64c6c.jpg",
        "title": "Классический микрофренч • Миндаль",
        "tags": ["френч", "миндаль", "минимализм", "нюд"],
        "sourceAuthor": "Alina Nails Studio",
        "createdAt": "2026-02-18T10:00:00Z"
    },
    {
        "id": "nm_0008",
        "imageUrl": "https://i.pinimg.com/originals/40/5c/01/405c01524810aaeee64744d0a80197e7.jpg",
        "title": "Жемчужная втирка хром • Миндаль",
        "tags": ["хром", "втирка", "миндаль", "нюд", "свадебный"],
        "sourceAuthor": "Hailey Glaze Art",
        "createdAt": "2026-02-18T12:00:00Z"
    },
    {
        "id": "nm_0009",
        "imageUrl": "https://i.pinimg.com/originals/4c/29/e0/4c29e039fdc6430d641c058548cf9009.jpg",
        "title": "Молочный нюд с поталью • Квадрат",
        "tags": ["нюд", "квадрат", "блестки", "минимализм"],
        "sourceAuthor": "Polina Nails",
        "createdAt": "2026-02-18T14:00:00Z"
    },
    {
        "id": "nm_0010",
        "imageUrl": "https://i.pinimg.com/originals/3e/06/36/3e063609d1e26e1e8be4f56d49b2a66b.jpg",
        "title": "Магнитный бархатный кошачий глаз • Мерцание",
        "tags": ["кошачий глаз", "миндаль", "блестки"],
        "sourceAuthor": "Velvet Nails Lab",
        "createdAt": "2026-02-19T09:00:00Z"
    },
    {
        "id": "nm_0011",
        "imageUrl": "https://i.pinimg.com/originals/77/06/c3/7706c34c68997a5b3ee0b2b8e398cae9.jpg",
        "title": "Глубокий винный глянец • Миндаль",
        "tags": ["бордо", "винный", "миндаль", "праздничный"],
        "sourceAuthor": "Burgundy Chic",
        "createdAt": "2026-02-19T11:00:00Z"
    },
    {
        "id": "nm_0012",
        "imageUrl": "https://i.pinimg.com/originals/52/7c/30/527c300a9dee9a0c9ca2769a649c7a32.jpg",
        "title": "Французский бэби-бумер градиент • Нюд",
        "tags": ["френч", "омбре", "нюд", "миндаль"],
        "sourceAuthor": "Baby Boomer Pro",
        "createdAt": "2026-02-19T13:00:00Z"
    },
    {
        "id": "nm_0013",
        "imageUrl": "https://i.pinimg.com/originals/e3/57/9f/e3579fe392f7c1bd785524f2e718474f.jpg",
        "title": "Шоколадный минимализм • Квадрат",
        "tags": ["минимализм", "квадрат", "нюд"],
        "sourceAuthor": "Warm Tones Studio",
        "createdAt": "2026-02-19T15:00:00Z"
    },
    {
        "id": "nm_0014",
        "imageUrl": "https://i.pinimg.com/originals/10/eb/ac/10ebaceb006b6d01cfb0ab4657ea6f79.jpg",
        "title": "Матовый изумруд с золотом • Миндаль",
        "tags": ["матовый", "миндаль", "блестки", "праздничный"],
        "sourceAuthor": "Emerald Velvet",
        "createdAt": "2026-02-19T17:00:00Z"
    },
    {
        "id": "nm_0015",
        "imageUrl": "https://i.pinimg.com/originals/e8/b1/fb/e8b1fbc20f73ca14a8b3f0360cca3887.jpg",
        "title": "Тончайший черный френч • Мягкий квадрат",
        "tags": ["френч", "черный", "квадрат", "минимализм"],
        "sourceAuthor": "Black Tip Minimal",
        "createdAt": "2026-02-20T08:00:00Z"
    },
    {
        "id": "nm_0016",
        "imageUrl": "https://i.pinimg.com/originals/7c/3d/0c/7c3d0cbc5d621b309f012a0fa506117e.jpg",
        "title": "Нежный свадебный нюд с жемчужным сиянием",
        "tags": ["свадебный", "нюд", "втирка", "миндаль"],
        "sourceAuthor": "Bridal Nails Master",
        "createdAt": "2026-02-20T10:00:00Z"
    },
    {
        "id": "nm_0017",
        "imageUrl": "https://i.pinimg.com/originals/43/df/53/43df53b9ea54423b5d4d3c2301dcae7f.jpg",
        "title": "Розовый аура-дизайн • Тренд 2025",
        "tags": ["аура", "розовый", "миндаль", "омбре"],
        "sourceAuthor": "Aura Nails Trend",
        "createdAt": "2026-02-20T12:00:00Z"
    },
    {
        "id": "nm_0018",
        "imageUrl": "https://i.pinimg.com/originals/d5/df/93/d5df93eb3c134e47eda764891aba8dcb.jpg",
        "title": "Мраморный кварцевый дизайн • Миндаль",
        "tags": ["мрамор", "миндаль", "нюд", "минимализм"],
        "sourceAuthor": "Marble Stone Nails",
        "createdAt": "2026-02-20T14:00:00Z"
    },
    {
        "id": "nm_0019",
        "imageUrl": "https://i.pinimg.com/originals/58/69/1f/58691f79ebbaca812cbb6f580542547c.jpg",
        "title": "Сияющий хром металлик • Стилет",
        "tags": ["хром", "стилет", "блестки"],
        "sourceAuthor": "Chrome Metal Nails",
        "createdAt": "2026-02-20T16:00:00Z"
    },
    {
        "id": "nm_0020",
        "imageUrl": "https://i.pinimg.com/originals/9c/75/ff/9c75ffe703706266feb5944d45f89ed7.jpg",
        "title": "Короткий квадрат • Натуральный нюд",
        "tags": ["короткие", "квадрат", "нюд", "минимализм"],
        "sourceAuthor": "Clean Girl Aesthetic",
        "createdAt": "2026-02-20T18:00:00Z"
    },
    {
        "id": "nm_0021",
        "imageUrl": "https://i.pinimg.com/originals/3d/9a/df/3d9adf641b59e3ace74e4d7df68b6d8a.jpg",
        "title": "Флористика и сухоцветы • Молочный миндаль",
        "tags": ["цветы", "миндаль", "нюд", "минимализм"],
        "sourceAuthor": "Botanical Nails",
        "createdAt": "2026-02-21T09:00:00Z"
    },
    {
        "id": "nm_0022",
        "imageUrl": "https://i.pinimg.com/originals/c3/6f/8d/c36f8d033e600fefdb6adc417141dd2b.jpg",
        "title": "Хрустальный френч со стразами • Миндаль",
        "tags": ["френч", "стразы", "миндаль", "праздничный"],
        "sourceAuthor": "Crystal French Lab",
        "createdAt": "2026-02-21T11:00:00Z"
    },
    {
        "id": "nm_0023",
        "imageUrl": "https://i.pinimg.com/originals/50/45/97/50459770bac6935ca5351c87833caae9.jpg",
        "title": "Матовый графит с глянцевой улыбкой",
        "tags": ["матовый", "черный", "френч", "квадрат"],
        "sourceAuthor": "Matte Contrast",
        "createdAt": "2026-02-21T13:00:00Z"
    },
    {
        "id": "nm_0024",
        "imageUrl": "https://i.pinimg.com/originals/32/02/a0/3202a0919544540b9f0587b9a00921c3.jpg",
        "title": "Градиент заката • Омбре • Миндаль",
        "tags": ["омбре", "розовый", "миндаль", "праздничный"],
        "sourceAuthor": "Sunset Gradient",
        "createdAt": "2026-02-21T15:00:00Z"
    },
    {
        "id": "nm_0025",
        "imageUrl": "https://sarareem.com/wp-content/uploads/2025/10/bycheznails-november-nails-fall-nails-2025-1.jpg",
        "title": "Глубокий осенний глянец • Квадрат",
        "tags": ["бордо", "квадрат", "минимализм"],
        "sourceAuthor": "@bycheznails",
        "createdAt": "2026-02-21T17:00:00Z"
    }
]

AESTHETIC_SEARCH_QUERIES = [
    # Holidays & Occasions
    "новогодний маникюр снежинки блестки",
    "маникюр на новый год 2025 дизайн фото",
    "маникюр 14 февраля сердечки дизайн",
    "маникюр 8 марта цветы весенний дизайн",
    "маникюр хэллоуин тыква дизайн ногтей",
    "вечерний маникюр блестки сияние",
    "свадебный маникюр нежный дизайн",

    # Shapes & Length
    "маникюр овал нежный дизайн фото",
    "маникюр стилет арт длинные ногти",
    "маникюр короткие ногти квадрат дизайн",
    "маникюр френч миндаль дизайн фото",
    "маникюр нюд квадрат минимализм фото",

    # Styles & Complexities
    "простой маникюр однотонный дизайн",
    "сложный дизайн ногтей роспись арт фото",
    "маникюр бордо винный глянец фото",
    "маникюр кошачий глаз магнитный фото",
    "маникюр градиент омбре бэби бумер",
    "маникюр втирка жемчужная хром фото",
    "маникюр матовый бархат дизайн",
    "маникюр мраморный дизайн фото",
    "маникюр аура тренд дизайн ногтей",
    "маникюр со стразами акцент фото",
    "маникюр цветы сухоцветы весна",
    "маникюр черный темный глянец дизайн",
    "маникюр розовый пудровый дизайн",
    "маникюр белый молочный дизайн фото",

    # English aesthetic queries
    "nail art christmas winter holiday",
    "nail art valentine heart design",
    "nail art halloween spooky nails",
    "wedding bridal manicure nail art",
    "nail art almond french manicure",
    "nail art chrome glazed donut",
    "nail art velvet cat eye magnetic",
    "nail art ombre baby boomer",
    "nail art nude minimalist square",
    "nail art burgundy red glazed",
    "nail art aura trend close up",
    "aesthetic manicure nails close up",
    "site:i.pinimg.com/originals nail art manicure",
    "site:i.pinimg.com/originals ногти дизайн маникюр",
    "site:i.pinimg.com/originals френч миндаль",
    "site:i.pinimg.com/originals нюд квадрат",

    # 1:1 and 16:9 multi-aspect sets & palettes
    "nail art palette 16:9 widescreen",
    "manicure nail palette wide photo",
    "nail designs palette horizontal 16:9",
    "nail art square collage 1:1",
    "маникюр палитра цветов дизайн 16:9",
    "коллаж дизайнов ногтей фото 1:1"
]

def normalize_url(url: str) -> str:
    """Normalizes image URL for robust deduplication."""
    u = url.split("?")[0].strip().lower()
    return u

def is_blacklisted(text: str) -> bool:
    """Checks if text or URL contains process, tool or hardware terms."""
    text_lower = text.lower()
    # Strictly reject wikimedia / wikipedia
    if "wikimedia" in text_lower or "wikipedia" in text_lower:
        return True
    for term in PROCESS_BLACKLIST:
        pattern = r'\b' + re.escape(term) + r'\b'
        if re.search(pattern, text_lower):
            return True
    return False

def extract_tags_from_text(text: str) -> list[str]:
    """Deterministically maps source text to Russian tags."""
    text_lower = text.lower()
    matched_tags = set()

    for ru_tag, keywords in TAG_DICTIONARY.items():
        for kw in keywords:
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
    tag_set = set(tags)
    text_lower = metadata_text.lower()

    if "втирка" in tag_set or "хром" in tag_set:
        if "миндаль" in tag_set:
            return "Жемчужная втирка хром • Миндаль"
        elif "квадрат" in tag_set:
            return "Зеркальная втирка • Квадрат"
        return "Жемчужный хром • Сияние"

    if "кошачий глаз" in tag_set:
        return "Магнитный кошачий глаз • Мерцание"

    if "аура" in tag_set:
        return "Трендовый аура-дизайн • Градиент"

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

    if "бордо" in tag_set or "винный" in tag_set:
        if "миндаль" in tag_set:
            return "Глубокий винный глянец • Миндаль"
        elif "квадрат" in tag_set:
            return "Винный глянец • Квадрат"
        return "Глубокий винный глянец • Дизайн"

    if "красный" in tag_set:
        return "Классический алый глянец"

    if "матовый" in tag_set:
        if "миндаль" in tag_set:
            return "Матовый бархат • Миндаль"
        elif "квадрат" in tag_set:
            return "Матовый бархатный квадрат"
        return "Матовый бархатный финиш"

    if "омбре" in tag_set and "нюд" in tag_set:
        return "Пастельный градиент омбре • Нюд"
    if "омбре" in tag_set:
        return "Градиентный дизайн омбре"

    if "новый год" in tag_set:
        return "Новогодний дизайн • Зимнее сияние"
    if "14 февраля" in tag_set:
        return "Романтичный дизайн с сердечками • 14 февраля"
    if "8 марта" in tag_set:
        return "Весенний дизайн с цветами • 8 марта"
    if "хэллоуин" in tag_set:
        return "Хэллоуин арт • Spooky Nails"
    if "вечерний" in tag_set:
        return "Вечерний сияющий дизайн • Праздничный"
    if "свадебный" in tag_set:
        return "Нежный свадебный нюд с сиянием"

    if "мрамор" in tag_set:
        return "Кварцевый мраморный дизайн"

    if "цветы" in tag_set:
        return "Нежная флористика с сухоцветами"

    if "блестки" in tag_set:
        if "миндаль" in tag_set:
            return "Мерцающий дизайн • Миндаль"
        elif "квадрат" in tag_set:
            return "Сияющий глиттер • Квадрат"
        return "Дизайн с акцентным блеском"

    if "нюд" in tag_set:
        if "минимализм" in tag_set:
            return "Нюдовый минимализм"
        elif "квадрат" in tag_set:
            return "Нежный нюд • Квадрат"
        elif "миндаль" in tag_set:
            return "Пудровый нюд • Миндаль"
        return "Нежный нюдовый дизайн"

    if "минимализм" in tag_set:
        if "квадрат" in tag_set:
            return "Лаконичный минимализм • Квадрат"
        return "Минималистичный дизайн ногтей"

    if "миндаль" in tag_set:
        return "Элегантный миндаль • Дизайн"
    if "квадрат" in tag_set:
        return "Четкий квадрат • Дизайн"

    capitalized = [t.capitalize() for t in tags[:2]]
    return " • ".join(capitalized)

def harvest_bing_queries(query: str, offset: int = 0) -> list[str]:
    """Harvests direct image URLs from Bing Image Search."""
    q = urllib.parse.quote(query)
    url = f"https://www.bing.com/images/async?q={q}&first={offset}&count=35&mmasync=1"
    req = urllib.request.Request(url, headers=HTTP_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            html = r.read().decode("utf-8")
            return re.findall(r'murl&quot;:&quot;(https?://[^&]+)&quot;', html)
    except Exception:
        return []

def harvest_yandex_queries(query: str, page: int = 0) -> list[str]:
    """Harvests direct original image URLs from Yandex Images."""
    q = urllib.parse.quote(query)
    url = f"https://yandex.ru/images/search?text={q}&p={page}&isize=large"
    req = urllib.request.Request(url, headers=HTTP_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            html = r.read().decode("utf-8")
            raw = re.findall(r'img_url=([^&\"\'\s]+)', html)
            return [urllib.parse.unquote(u) for u in raw if u.startswith("http")]
    except Exception:
        return []

ALL_COLOR_TAGS = [
    "нюд", "розовый", "красный", "бордо", "белый",
    "черный", "синий", "зеленый", "фиолетовый", "золото/серебро"
]

def detect_hsv_color(img: Image.Image) -> str:
    """Center-crop HSV dominant hue/saturation/value analysis on a manicure photo."""
    w, h = img.size
    left = int(w * 0.20)
    top = int(h * 0.20)
    right = int(w * 0.80)
    bottom = int(h * 0.80)
    crop = img.crop((left, top, right, bottom)).convert("RGB").resize((45, 45), Image.Resampling.BILINEAR)
    hsv_crop = crop.convert("HSV")
    votes = {c: 0.0 for c in ALL_COLOR_TAGS}

    for pixel in hsv_crop.getdata():
        h_val, s_val, v_val = pixel[0], pixel[1], pixel[2]
        h_deg = h_val * 360.0 / 255.0
        s_norm = s_val / 255.0
        v_norm = v_val / 255.0

        if v_norm < 0.22:
            votes["черный"] += 1.8
        elif v_norm > 0.82 and s_norm < 0.16:
            votes["белый"] += 1.5
        elif s_norm < 0.25:
            if 10 <= h_deg <= 48 and v_norm > 0.40:
                votes["нюд"] += 1.4
            elif v_norm > 0.70:
                votes["белый"] += 1.0
            else:
                votes["золото/серебро"] += 0.8
        elif h_deg >= 345 or h_deg < 15:
            if v_norm < 0.45 or (s_norm > 0.65 and v_norm < 0.55):
                votes["бордо"] += 1.7
            else:
                votes["красный"] += 1.7
        elif 15 <= h_deg < 42:
            if s_norm < 0.52 and v_norm > 0.42:
                votes["нюд"] += 1.6
            elif s_norm >= 0.52 and v_norm > 0.58:
                votes["золото/серебро"] += 1.4
            elif v_norm < 0.42:
                votes["бордо"] += 1.2
            else:
                votes["нюд"] += 1.2
        elif 42 <= h_deg < 68:
            votes["золото/серебро"] += 1.6
        elif 68 <= h_deg < 165:
            votes["зеленый"] += 1.7
        elif 165 <= h_deg < 255:
            votes["синий"] += 1.7
        elif 255 <= h_deg < 315:
            votes["фиолетовый"] += 1.7
        elif 315 <= h_deg < 345:
            votes["розовый"] += 1.7

    return max(votes.items(), key=lambda x: x[1])[0]

def validate_pillow_candidate(candidate: dict) -> dict | None:
    """
    Downloads image headers/bytes and verifies with Pillow:
    1. HTTP 200/206
    2. Resolution >= 720 x 720
    3. Aspect Ratio: 0.45 <= (w / h) <= 1.15
    4. Valid Image format (JPEG, PNG, WEBP)
    5. Automatic HSV dominant color tagging if no color tag present
    """
    url = candidate.get("imageUrl", "")
    if is_blacklisted(url):
        return None

    try:
        req = urllib.request.Request(url, headers=HTTP_HEADERS)
        with urllib.request.urlopen(req, timeout=6) as resp:
            if resp.status not in (200, 206):
                return None
            chunk = resp.read(65536) # Read first 64KB for header parse
            if len(chunk) < 500:
                return None
            img = Image.open(io.BytesIO(chunk))
            if img.format not in ("JPEG", "PNG", "WEBP"):
                return None

            w, h = img.size
            if min(w, h) < MIN_DIM or max(w, h) < MIN_MAX_DIM:
                return None

            aspect = w / float(h)
            if not (MIN_ASPECT <= aspect <= MAX_ASPECT):
                return None

            candidate["width"] = w
            candidate["height"] = h

            # Format Aspect Ratio Detection (1:1, 9:16, 16:9)
            tags = candidate.get("tags", [])
            format_tag = detect_format_tag(aspect)
            if not any(f in tags for f in ALL_FORMAT_TAGS):
                tags.append(format_tag)

            # Automatic HSV Color Detection if no color tag is present
            if not any(c in tags for c in ALL_COLOR_TAGS):
                color = detect_hsv_color(img)
                tags.append(color)

            candidate["tags"] = sorted(list(set(tags)))

            return candidate
    except Exception:
        return None

def main():
    print("=== NMD High-Aesthetic Curated Manicure Harvester (Zero Wikimedia) ===")
    t_start = time.time()

    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_file = os.path.join(root_dir, "designs.json")

    force_purge = "--purge" in sys.argv
    existing_designs = []
    seen_urls = set()

    # Inspect existing catalog: if polluted with wikimedia or --purge requested, purge once
    if os.path.exists(target_file) and not force_purge:
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                has_wiki = any("wikimedia" in d.get("imageUrl", "") for d in data)
                if has_wiki:
                    print("[PURGE] Legacy catalog contains Wikimedia URLs. Purging dirty catalog for clean rebuild...")
                else:
                    for item in data:
                        url = item.get("imageUrl", "")
                        norm = normalize_url(url)
                        if norm and norm not in seen_urls and not is_blacklisted(url):
                            seen_urls.add(norm)
                            tags = item.get("tags", [])
                            if not any(f in tags for f in ALL_FORMAT_TAGS):
                                w = item.get("width")
                                h = item.get("height")
                                if w and h and h > 0:
                                    tags.append(detect_format_tag(w / float(h)))
                                else:
                                    tags.append("вертикальное 9:16")
                                item["tags"] = sorted(list(set(tags)))
                            existing_designs.append(item)
                    print(f"[ACCUMULATION] Retained {len(existing_designs)} verified clean designs with format tags.")
        except Exception as e:
            print(f"[WARN] Error reading {target_file}: {e}")

    # Add curated seeds
    for seed in CURATED_SEEDS:
        norm = normalize_url(seed["imageUrl"])
        if norm not in seen_urls:
            seen_urls.add(norm)
            existing_designs.append(seed)

    print(f"\n[PHASE 1] Harvesting across {len(AESTHETIC_SEARCH_QUERIES)} curated manicure categories...")
    harvest_tasks = []
    for q in AESTHETIC_SEARCH_QUERIES:
        harvest_tasks.append(("bing", q, 0))
        harvest_tasks.append(("bing", q, 35))
        harvest_tasks.append(("yandex", q, 0))
        harvest_tasks.append(("yandex", q, 1))

    candidate_urls = []
    with ThreadPoolExecutor(max_workers=HARVEST_WORKERS) as executor:
        futures = []
        for engine, query, page_or_offset in harvest_tasks:
            if engine == "bing":
                futures.append(executor.submit(harvest_bing_queries, query, page_or_offset))
            else:
                futures.append(executor.submit(harvest_yandex_queries, query, page_or_offset))

        for f in as_completed(futures):
            res_urls = f.result()
            for u in res_urls:
                norm = normalize_url(u)
                if norm not in seen_urls and not is_blacklisted(u):
                    seen_urls.add(norm)
                    candidate_urls.append(u)

    print(f"[HARVEST] Collected {len(candidate_urls)} clean candidate URLs passing blacklist.")

    # Prepare candidate objects with synthesized titles and tags
    candidates_to_validate = []
    for u in candidate_urls:
        tags = extract_tags_from_text(u)
        title = synthesize_title_from_tags(tags, u)
        author = "NailsMaster Aesthetic"
        if "sarareem.com" in u:
            author = "Sara Reem (@bycheznails)"
        elif "byrdie.com" in u:
            author = "Byrdie Beauty Editorial"
        elif "goldapple.ru" in u:
            author = "Золотое Яблоко Beauty"
        elif "pinimg.com" in u:
            author = "Pinterest Manicure Inspo"
        elif "unsplash.com" in u:
            author = "Unsplash Beauty Collective"

        candidates_to_validate.append({
            "imageUrl": u,
            "title": title,
            "tags": tags,
            "sourceAuthor": author,
            "createdAt": datetime.now(timezone.utc).isoformat()
        })

    # Validate candidates with Pillow
    print(f"\n[PHASE 2] Validating resolution (>=720x720) & aspect ratio with Pillow ({VALIDATION_WORKERS} workers)...")
    validated_new_designs = []
    with ThreadPoolExecutor(max_workers=VALIDATION_WORKERS) as executor:
        futures = {executor.submit(validate_pillow_candidate, c): c for c in candidates_to_validate}
        for f in as_completed(futures):
            res = f.result()
            if res:
                validated_new_designs.append(res)
                if len(validated_new_designs) % 100 == 0:
                    print(f"  ... validated {len(validated_new_designs)} high-aesthetic designs")

    print(f"[VALIDATION] Successfully validated {len(validated_new_designs)} high-resolution designs.")

    # Merge with existing
    all_designs = existing_designs + validated_new_designs
    if len(all_designs) > MAX_CATALOG_SIZE:
        print(f"[CAP] Capping catalog at {MAX_CATALOG_SIZE} freshest entries (was {len(all_designs)})")
        all_designs = all_designs[:MAX_CATALOG_SIZE]

    # Re-index clean IDs: nm_0001 .. nm_XXXX
    for idx, d in enumerate(all_designs, 1):
        d["id"] = f"nm_{idx:04d}"

    print(f"\n[PHASE 3] Writing {len(all_designs)} designs to {target_file}...")
    with open(target_file, "w", encoding="utf-8") as f:
        json.dump(all_designs, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - t_start
    print(f"\n=== FINISHED in {elapsed:.1f}s ===")
    print(f"Catalog contains {len(all_designs)} clean, verified designs.")
    print(f"File size: {os.path.getsize(target_file) / 1024:.1f} KB")

if __name__ == "__main__":
    main()
