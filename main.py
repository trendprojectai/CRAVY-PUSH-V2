import os
import csv
import asyncio
import logging
import re
import json
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
    "menu_url"
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

async def run_pipeline():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("❌ GOOGLE_API_KEY missing.")
        return

    google = GooglePlacesClient(api_key)
    crawler = MenuDiscoveryCrawler()

    logger.info(f"Discovering restaurants in {AREA_NAME}, {CITY_NAME}...")
    raw_places = await google.text_search(
        SEARCH_QUERY,
        CENTER_LAT,
        CENTER_LNG,
        RADIUS_METERS
    )

    unique_places = {p["id"]: p for p in raw_places}
    logger.info(f"Found {len(unique_places)} places.")

    results = []

    for idx, (place_id, summary) in enumerate(unique_places.items(), start=1):
        name = summary.get("displayName", {}).get("text", "Unknown")
        logger.info(f"[{idx}] Enriching {name}")

        details = await google.get_place_details(place_id)
        if not details:
            continue

        loc = details.get("location", {})
        address = details.get("formattedAddress", "")

        images = google.extract_images(details.get("photos", []))
        website = details.get("websiteUri", "")
        menu_url = await crawler.find_menu(website) if website else ""

        results.append({
            "google_place_id": place_id,
            "name": name,
            "latitude": loc.get("latitude"),
            "longitude": loc.get("longitude"),
            "address": address,
            "postcode": extract_postcode(address),
            "city": CITY_NAME,
            "country": COUNTRY_NAME,
            "area": AREA_NAME,
            "category_name": derive_cuisine(details.get("types", [])),
            "category": ",".join(details.get("types", [])),
            "website": website,
            "phone": details.get("nationalPhoneNumber", ""),
            "rating": details.get("rating"),
            "reviews_count": details.get("userRatingCount"),
            "price_level": details.get("priceLevel"),
            "cover_image": images["hero_image_url"],
            "gallery_image_urls": json.dumps(images["gallery_image_urls"]),
            "menu_url": menu_url
        })

        await asyncio.sleep(0.25)

    with open(CSV_FILENAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(results)

    await google.close()
    logger.info(f"✅ SUCCESS: Generated {CSV_FILENAME}")

if __name__ == "__main__":
    asyncio.run(run_pipeline())
