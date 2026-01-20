import os
import csv
import asyncio
import logging
import re
import json
import datetime
from dotenv import load_dotenv
from typing import List

from google_places import GooglePlacesClient
from crawler import MenuDiscoveryCrawler

load_dotenv()

# -----------------------
# CONFIG — CHANGE PER AREA
# -----------------------
AREA_NAME = "Soho"
CITY_NAME = "London"
COUNTRY_NAME = "UK"

CENTER_LAT = 51.5136
CENTER_LNG = -0.1331
RADIUS_METERS = 1000

SCAN_RADIUS_METERS = 350
SOHO_SCAN_POINTS = [
    (51.5152, -0.1321),  # North Soho
    (51.5140, -0.1363),  # Northwest Soho
    (51.5132, -0.1320),  # Central Soho
    (51.5130, -0.1355),  # West Soho
    (51.5122, -0.1327),  # South Central
    (51.5120, -0.1357),  # Southwest Soho
    (51.5128, -0.1297),  # East Soho
    (51.5144, -0.1294),  # Northeast Soho
    (51.5116, -0.1305),  # Southeast Soho
    (51.5150, -0.1289),  # Far East Soho
]

SEARCH_QUERY = "restaurants"

# -----------------------
# LOGGING
# -----------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

CSV_FILENAME = "soho_restaurants_final.csv"
SCAN_HISTORY_FILENAME = "scan_history.json"

CSV_COLUMNS = [
    "google_place_id",
    "name",
    "latitude",
    "longitude",
    "address",
    "postcode",
    "city",
    "country",
    "area",
    "category_name",
    "category",
    "website",
    "phone",
    "rating",
    "reviews_count",
    "price_level",
    "cover_image",
    "gallery_image_urls",
    "menu_url",
    "description"
]

CUISINE_MAPPING = {
    "italian_restaurant": "Italian",
    "chinese_restaurant": "Chinese",
    "indian_restaurant": "Indian",
    "japanese_restaurant": "Japanese",
    "thai_restaurant": "Thai",
    "french_restaurant": "French",
    "mexican_restaurant": "Mexican",
    "american_restaurant": "American",
    "pizza_restaurant": "Pizza",
    "cafe": "Cafe",
    "bakery": "Bakery",
}

def extract_postcode(address: str) -> str:
    pattern = r'([A-Z]{1,2}[0-9][0-9A-Z]?\s?[0-9][A-Z]{2})'
    match = re.search(pattern, address.upper())
    return match.group(0) if match else ""

def derive_cuisine(types: List[str]) -> str:
    for t in types:
        if t in CUISINE_MAPPING:
            return CUISINE_MAPPING[t]
    return "Restaurant"

def sanitize_one_line(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.replace("\r", " ").replace("\n", " ")).strip()

def generate_description_fallback(
    name: str,
    cuisine: str,
    area: str,
    city: str,
    price_level: str | None
) -> str:
    description = f"{cuisine} restaurant in {area} {city} offering casual dining"
    pricing_map = {
        "PRICE_LEVEL_INEXPENSIVE": "with affordable pricing",
        "PRICE_LEVEL_MODERATE": "with moderately priced dishes",
        "PRICE_LEVEL_EXPENSIVE": "with an upscale dining style",
        "PRICE_LEVEL_VERY_EXPENSIVE": "with a fine dining focus"
    }
    pricing_phrase = pricing_map.get(price_level)
    if pricing_phrase:
        description = f"{description} {pricing_phrase}"
    description = sanitize_one_line(description)
    if not description.endswith("."):
        description = f"{description}."
    return description

def load_existing_places(csv_filename: str) -> dict[str, dict]:
    if not os.path.exists(csv_filename):
        return {}

    with open(csv_filename, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {
            row.get("google_place_id"): row
            for row in reader
            if row.get("google_place_id")
        }

def load_scan_history(history_filename: str) -> list[dict]:
    if not os.path.exists(history_filename):
        return []

    try:
        with open(history_filename, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []

def persist_scan_history(history_filename: str, history: list[dict]) -> None:
    with open(history_filename, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

async def run_pipeline():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("❌ GOOGLE_API_KEY missing.")
        return

    google = GooglePlacesClient(api_key)
    crawler = MenuDiscoveryCrawler()

    logger.info(f"Discovering restaurants in {AREA_NAME}, {CITY_NAME}...")
    existing_places: dict[str, dict] = load_existing_places(CSV_FILENAME)
    logger.info("Loaded %s existing restaurants.", len(existing_places))

    scan_history = load_scan_history(SCAN_HISTORY_FILENAME)
    next_scan_number = (scan_history[-1]["scan_number"] + 1) if scan_history else 1
    total_new_found = 0

    for idx, (lat, lng) in enumerate(SOHO_SCAN_POINTS, start=1):
        logger.info("Scan %s/%s started", idx, len(SOHO_SCAN_POINTS))
        raw_places = await google.text_search(
            SEARCH_QUERY,
            lat,
            lng,
            SCAN_RADIUS_METERS
        )

        new_count = 0
        for place in raw_places:
            place_id = place.get("id")
            if not place_id or place_id in existing_places:
                continue

            name = place.get("displayName", {}).get("text", "Unknown")
            logger.info("NEW: %s", name)

            details = await google.get_place_details(place_id)
            if not details:
                continue

            loc = details.get("location", {})
            address = details.get("formattedAddress", "")

            images = google.extract_images(details.get("photos", []))
            website = details.get("websiteUri", "")
            category_name = derive_cuisine(details.get("types", []))
            menu_url = await crawler.find_menu(website) if website else ""
            description = generate_description_fallback(
                name,
                category_name,
                AREA_NAME,
                CITY_NAME,
                details.get("priceLevel")
            )

            existing_places[place_id] = {
                "google_place_id": place_id,
                "name": name,
                "latitude": loc.get("latitude"),
                "longitude": loc.get("longitude"),
                "address": address,
                "postcode": extract_postcode(address),
                "city": CITY_NAME,
                "country": COUNTRY_NAME,
                "area": AREA_NAME,
                "category_name": category_name,
                "category": ",".join(details.get("types", [])),
                "website": website,
                "phone": details.get("nationalPhoneNumber", ""),
                "rating": details.get("rating"),
                "reviews_count": details.get("userRatingCount"),
                "price_level": details.get("priceLevel"),
                "cover_image": images["hero_image_url"],
                "gallery_image_urls": json.dumps(images["gallery_image_urls"]),
                "menu_url": menu_url,
                "description": description
            }

            new_count += 1
            total_new_found += 1

            await asyncio.sleep(0.25)

        logger.info("Scan %s/%s complete — %s new restaurants", idx, len(SOHO_SCAN_POINTS), new_count)

    total_restaurants = len(existing_places)
    logger.info("Total restaurants known: %s", total_restaurants)

    if total_new_found == 0:
        logger.info("No new restaurants found — coverage likely complete")

    scan_history.append({
        "scan_number": next_scan_number,
        "new_found": total_new_found,
        "total": total_restaurants,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    })
    persist_scan_history(SCAN_HISTORY_FILENAME, scan_history)

    with open(CSV_FILENAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=CSV_COLUMNS,
            quoting=csv.QUOTE_ALL
        )
        writer.writeheader()
        writer.writerows(existing_places.values())

    await google.close()
    logger.info(f"✅ SUCCESS: Generated {CSV_FILENAME}")

if __name__ == "__main__":
    asyncio.run(run_pipeline())
