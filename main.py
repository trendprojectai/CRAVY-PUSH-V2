
import os
import csv
import asyncio
import logging
import re
from typing import List, Dict, Any
from dotenv import load_dotenv

# Local imports
from google_places import GooglePlacesClient
from crawler import MenuDiscoveryCrawler

load_dotenv()

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

CSV_FILENAME = "soho_restaurants_final.csv"
CSV_COLUMNS = [
    "google_place_id", "name", "latitude", "longitude", 
    "address_full", "postcode", "cuisine", "categories", 
    "website", "hero_image_url", "menu_url"
]

# Enhanced cuisine mapping for London/Soho specific types
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

def extract_postcode(address: str) -> str:
    """Extracts UK postcode using standard pattern (e.g., W1F 0RN)."""
    # Pattern matches W1D, W1F, W1B, etc typical of Soho
    pattern = r'([Gg][Ii][Rr] 0[Aa]{2})|((([A-Za-z][0-9]{1,2})|(([A-Za-z][A-Ha-hJ-Yj-y][0-9]{1,2})|(([A-Za-z][0-9][A-Za-z])|([A-Za-z][A-Ha-hJ-Yj-y][0-9][A-Za-z]?))))\s?[0-9][A-Za-z]{2})'
    match = re.search(pattern, address)
    return match.group(0) if match else ""

def derive_cuisine(types: List[str]) -> str:
    """Derives best-fit cuisine from Google Place types."""
    for t in types:
        if t in CUISINE_MAPPING:
            return CUISINE_MAPPING[t]
    return "Restaurant"

async def run_pipeline():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GOOGLE_API_KEY missing. Update .env file.")
        return

    google = GooglePlacesClient(api_key)
    crawler = MenuDiscoveryCrawler()
    
    logger.info("Step 1: Discovering all restaurants in Soho circle...")
    raw_places = await google.text_search("restaurants in Soho London")
    
    # Deduplicate by ID
    unique_places = {}
    for p in raw_places:
        unique_places[p['id']] = p
    
    logger.info(f"Found {len(unique_places)} unique Soho locations.")

    final_results = []
    processed_count = 0
    total = len(unique_places)

    for place_id, summary in unique_places.items():
        processed_count += 1
        name = summary.get('displayName', {}).get('text', 'Unknown')
        
        logger.info(f"[{processed_count}/{total}] Enriching: {name}")
        
        # Step 2: Full Detail Fetch
        details = await google.get_place_details(place_id)
        if not details:
            logger.warning(f"Could not fetch details for {name}")
            continue
            
        # Data Extraction
        loc = details.get('location', {})
        lat, lng = loc.get('latitude'), loc.get('longitude')
        address = details.get('formattedAddress', '')
        postcode = extract_postcode(address)
        website = details.get('websiteUri', '')
        types = details.get('types', [])
        cuisine = derive_cuisine(types)
        
        # Hero Image (First Photo)
        hero_url = ""
        photos = details.get('photos', [])
        if photos:
            hero_url = google.get_photo_url(photos[0].get('name'))
        
        # Step 3: Menu Discovery
        menu_url = ""
        if website:
            menu_url = await crawler.find_menu(website)
            if menu_url:
                logger.info(f"   Menu detected: {menu_url}")
        
        final_results.append({
            "google_place_id": place_id,
            "name": name,
            "latitude": lat,
            "longitude": lng,
            "address_full": address,
            "postcode": postcode,
            "cuisine": cuisine,
            "categories": ",".join(types),
            "website": website,
            "hero_image_url": hero_url,
            "menu_url": menu_url
        })
        
        # Throttle to stay under 5 req/s (0.2s delay)
        await asyncio.sleep(0.25)

    # Step 4: Final CSV Write
    logger.info(f"Pipeline finished. Exporting {len(final_results)} records...")
    with open(CSV_FILENAME, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(final_results)
    
    await google.close()
    logger.info(f"SUCCESS: Generated {CSV_FILENAME}")

if __name__ == "__main__":
    try:
        asyncio.run(run_pipeline())
    except KeyboardInterrupt:
        logger.info("Pipeline stopped by user.")
