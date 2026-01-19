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
# LOGGING
# -----------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# -----------------------
# OUTPUT CONFIG (SUPABASE-READY)
# -----------------------
CSV_FILENAME = "soho_restaurants_final.csv"

CSV_COLUMNS = [
    "google_place_id",
    "name",
    "latitude",
    "longitude",
    "address",
    "postcode",
    "category_name",
    "category",
    "website",
    "rating",
    "reviews_count",
    "price_level",
    "cover_image",
    "gallery_image_urls",
    "menu_url"
]

# -----------------------
# CUISINE MAPPING
# -----------------------
CUISINE_MAPPING = {
    "italian_restaurant": "Italian",
    "chinese_restaurant": "Chinese",
    "indian_restaurant": "Indian",
    "japanese_restaurant": "Japanese",
    "thai_restaurant": "Thai",
    "french_restaurant": "French",
    "spanish_restaurant": "Spanish",
    "mexican_restaurant": "Mexican",
    "middle_eastern_restaurant": "Middle Eastern",
    "american_restaurant": "American",
    "mediterranean_restaurant": "Mediterranean",
    "seafood_restaurant": "Seafood",
    "steak_house": "Steakhouse",
    "sushi_restaurant": "Sushi",
    "vietnamese_restaurant": "Vietnamese",
    "korean_restaurant": "Korean",
    "greek_restaurant": "Greek",
    "turkish_restaurant": "Turkish",
    "brazilian_restaurant": "Brazilian",
    "pizza_restaurant": "Pizza",
    "hamburger_restaurant": "Burgers",
    "bakery": "Bakery",
    "cafe": "Cafe",
    "wine_bar": "Wine Bar",
    "pub": "Gastropub",
    "brasserie": "Brasserie",
    "lebanese_restaurant": "Lebanese",
    "ethiopian_restaurant": "Ethiopian",
    "israeli_restaurant": "Israeli"
}

# -----------------------
# HELPERS
# -----------------------
def extract_postcode(address: str) -> str:
    pattern = r'([A-Z]{1,2}[0-9][0-9A-Z]?\s?[0-9][A-Z]{2})'
    match = re.search(pattern, address.upper())
    return match.group(0) if match else ""

def derive_cuisine(types: List[str]) -> str:
    for t in types:
        if t in CUISINE_MAPPING:
            return CUISINE_MAPPING[t]
    return "Restaurant"

# -----------------------
# PIPELINE
# -----------------------
async def run_pipeline():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("❌ GOOGLE_API_KEY missing.")
        return

    google = GooglePlacesClient(api_key)
    crawler = MenuDiscoveryCrawler()

    logger.info("Step 1: Discovering Soho restaurants...")
    raw_places = await google.text_search("restaurants in Soho London")

    unique_places = {p["id"]: p for p in raw_places}
    logger.info(f"Found {len(unique_places)} unique Soho locations.")

    results = []
    total = len(unique_places)

    for idx, (place_id, summary) in enumerate(unique_places.items(), start=1):
        name = summary.get("displayName", {}).get("text", "Unknown")
        logger.info(f"[{idx}/{total}] Enriching: {name}")

        details = await google.get_place_details(place_id)
        if not details:
            continue

        loc = details.get("location", {})
        address = details.get("formattedAddress", "")

        photos = details.get("photos", [])
        image_data = google.extract_images(photos)

        website = details.get("websiteUri", "")
        menu_url = await crawler.find_menu(website) if website else ""

        results.append({
            # --- SUPABASE COLUMN NAMES ---
            "google_place_id": place_id,
            "name": name,
            "latitude": loc.get("latitude"),
            "longitude": loc.get("longitude"),
            "address": address,
            "postcode": extract_postcode(address),
            "category_name": derive_cuisine(details.get("types", [])),
            "category": ",".join(details.get("types", [])),
            "website": website,
            "rating": details.get("rating"),
            "reviews_count": details.get("userRatingCount"),
            "price_level": details.get("priceLevel"),
            "cover_image": image_data["hero_image_url"],
            "gallery_image_urls": json.dumps(image_data["gallery_image_urls"]),
            "menu_url": menu_url
        })

        await asyncio.sleep(0.25)

    # -----------------------
    # WRITE CSV (READY FOR SUPABASE)
    # -----------------------
    logger.info(f"Exporting {len(results)} rows...")
    with open(CSV_FILENAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(results)

    await google.close()
    logger.info(f"✅ SUCCESS: Generated {CSV_FILENAME}")

# -----------------------
# ENTRY POINT
# -----------------------
if __name__ == "__main__":
    asyncio.run(run_pipeline())
