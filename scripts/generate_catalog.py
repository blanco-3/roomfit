from __future__ import annotations

import json
import random
from pathlib import Path

random.seed(42)

BASE_DIR = Path(__file__).resolve().parent.parent
OUT_PATH = BASE_DIR / "data" / "furniture_catalog.json"

brands = ["ikea", "coupang", "zarahome", "hanssem", "iloom", "marketb"]
categories = {
    "bed": {
        "names": ["Cloud Bed", "Frame Bed", "Linen Bed", "Compact Bed"],
        "dims": [(110, 205, 95), (150, 205, 100), (166, 209, 100), (180, 210, 98)],
        "price": (180000, 690000),
        "tags": ["minimal", "warm", "wood", "white", "scandinavian"],
    },
    "desk": {
        "names": ["Work Desk", "Slim Desk", "Studio Desk", "Focus Table"],
        "dims": [(100, 55, 74), (120, 60, 74), (140, 70, 74), (160, 70, 74)],
        "price": (70000, 390000),
        "tags": ["minimal", "white", "wood", "modern", "focus"],
    },
    "chair": {
        "names": ["Task Chair", "Fabric Chair", "Mesh Chair", "Ergo Chair"],
        "dims": [(56, 56, 90), (60, 60, 110), (62, 60, 128), (65, 63, 130)],
        "price": (49000, 420000),
        "tags": ["minimal", "black", "cream", "ergonomic", "modern"],
    },
    "storage": {
        "names": ["Shelf Unit", "Cabinet", "Drawer Chest", "Organizer"],
        "dims": [(60, 35, 120), (77, 39, 147), (90, 42, 160), (120, 40, 180)],
        "price": (59000, 520000),
        "tags": ["minimal", "white", "wood", "storage", "warm"],
    },
    "sofa": {
        "names": ["2-seat Sofa", "Comfy Sofa", "Soft Sofa", "Daily Sofa"],
        "dims": [(145, 82, 85), (160, 90, 88), (180, 92, 85), (200, 95, 87)],
        "price": (220000, 1100000),
        "tags": ["gray", "beige", "minimal", "modern", "warm"],
    },
    "table": {
        "names": ["Side Table", "Round Table", "Square Table", "Accent Table"],
        "dims": [(45, 45, 45), (50, 50, 45), (60, 60, 46), (70, 70, 47)],
        "price": (35000, 250000),
        "tags": ["minimal", "warm", "wood", "modern", "white"],
    },
}

moods = ["minimal", "warm", "scandinavian", "modern", "natural", "dark"]

items = []
counter = 1

for category, cfg in categories.items():
    for brand in brands:
        for _ in range(18):  # 6 category * 6 brand * 18 = 648 SKU
            w, d, h = random.choice(cfg["dims"])
            jitter = lambda x, r: max(20, x + random.randint(-r, r))
            width = jitter(w, 8)
            depth = jitter(d, 7)
            height = jitter(h, 10)
            low, high = cfg["price"]
            price = int(random.randrange(low, high, 1000))

            tags = set(random.sample(cfg["tags"], k=2))
            tags.add(random.choice(moods))

            model = f"{random.choice(cfg['names'])} {random.choice(['S', 'M', 'L', 'Pro', 'Air'])}"
            item = {
                "id": f"sku_{counter:04d}",
                "source": brand,
                "name": model,
                "category": category,
                "width_cm": width,
                "depth_cm": depth,
                "height_cm": height,
                "price_krw": price,
                "style_tags": sorted(list(tags)),
                "url": f"https://example.com/{brand}/{category}/{counter}",
            }
            items.append(item)
            counter += 1

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(items, f, ensure_ascii=False, indent=2)

print(f"generated {len(items)} SKUs -> {OUT_PATH}")
