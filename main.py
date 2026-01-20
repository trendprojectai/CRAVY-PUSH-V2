import os
import csv
import asyncio
import logging
import re
import json
import datetime
import math
import argparse
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from google_places import GooglePlacesClient
from crawler import MenuDiscoveryCrawler

load_dotenv()

# -----------------------
# CONFIG
# -----------------------
SEARCH_QUERY = "restaurants"
SCAN_RADIUS_METERS = 350
ZONES_FILENAME = "zones.json"
MASTER_CSV_FILENAME = "master_restaurants.csv"
SCAN_EVENTS_FILENAME = "scan_events.json"

# -----------------------
# LOGGING
# -----------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

CSV_COLUMNS = [
    "google_place_id",
    "name",
    "latitude",
    "longitude",
    "zone_id",
    "discovered_at",
    "rating",
    "reviews_count",
    "price_level",
    "website",
    "menu_url",
    "cover_image",
    "gallery_image_urls",
    "logo_url"
]

def load_zones(zones_filename: str) -> list[dict]:
    if not os.path.exists(zones_filename):
        logger.error("❌ zones.json missing at %s", zones_filename)
        return []

    try:
        with open(zones_filename, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        logger.error("❌ zones.json malformed")
        return []

def save_zones(zones_filename: str, zones: list[dict]) -> None:
    with open(zones_filename, "w", encoding="utf-8") as f:
        json.dump(zones, f, indent=2)

def clear_scan_events(events_filename: str) -> None:
    with open(events_filename, "w", encoding="utf-8"):
        pass

def append_scan_event(events_filename: str, event: dict) -> None:
    with open(events_filename, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")

def load_existing_places(csv_filename: str) -> dict[str, dict]:
    if not os.path.exists(csv_filename):
        return {}

    with open(csv_filename, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        existing: dict[str, dict] = {}
        for row in reader:
            place_id = row.get("google_place_id")
            if not place_id:
                continue
            existing[place_id] = normalize_existing_row(row)
        return existing

def normalize_existing_row(row: dict) -> dict:
    return {
        "google_place_id": row.get("google_place_id", ""),
        "name": row.get("name", ""),
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
        "zone_id": row.get("zone_id", ""),
        "discovered_at": row.get("discovered_at", ""),
        "rating": row.get("rating"),
        "reviews_count": row.get("reviews_count"),
        "price_level": row.get("price_level"),
        "website": row.get("website", ""),
        "menu_url": row.get("menu_url", ""),
        "cover_image": row.get("cover_image", ""),
        "gallery_image_urls": row.get("gallery_image_urls", ""),
        "logo_url": row.get("logo_url", "")
    }

def meters_to_lat(meters: float) -> float:
    return meters / 111320

def meters_to_lng(meters: float, lat: float) -> float:
    denominator = 111320 * math.cos(math.radians(lat))
    if denominator == 0:
        return 0
    return meters / denominator

def generate_scan_points(
    center_lat: float,
    center_lng: float,
    radius_meters: float,
    scan_radius_meters: float
) -> list[tuple[float, float]]:
    step = max(scan_radius_meters * 1.4, 200)
    points: list[tuple[float, float]] = []

    for x in range(int(-radius_meters), int(radius_meters) + 1, int(step)):
        for y in range(int(-radius_meters), int(radius_meters) + 1, int(step)):
            if x * x + y * y > radius_meters * radius_meters:
                continue
            lat = center_lat + meters_to_lat(y)
            lng = center_lng + meters_to_lng(x, center_lat)
            points.append((lat, lng))

    if not points:
        points = [(center_lat, center_lng)]

    return points

def sanitize_one_line(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.replace("\r", " ").replace("\n", " ")).strip()

def normalize_website(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme:
        return url
    return f"https://{url}"

async def url_has_image(client: httpx.AsyncClient, url: str) -> bool:
    try:
        response = await client.head(url, follow_redirects=True)
        if response.status_code == 405:
            response = await client.get(url, follow_redirects=True, headers={"Range": "bytes=0-0"})
    except Exception:
        return False

    if response.status_code >= 400:
        return False

    content_type = response.headers.get("content-type", "").lower()
    return "image" in content_type

async def fetch_icon_from_html(client: httpx.AsyncClient, website: str) -> str:
    try:
        response = await client.get(website, follow_redirects=True)
    except Exception:
        return ""

    if response.status_code >= 400:
        return ""

    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type:
        return ""

    soup = BeautifulSoup(response.text, "html.parser")
    for link in soup.find_all("link", href=True, rel=True):
        rel_value = " ".join(link.get("rel", [])).lower()
        if "icon" in rel_value:
            href = link.get("href")
            if href:
                return urljoin(str(response.url), href)

    return ""

async def fetch_logo_url(client: httpx.AsyncClient, website: str) -> str:
    normalized = normalize_website(website)
    if not normalized:
        return ""

    favicon_url = urljoin(normalized.rstrip("/") + "/", "favicon.ico")
    if await url_has_image(client, favicon_url):
        return favicon_url

    icon_url = await fetch_icon_from_html(client, normalized)
    if icon_url and await url_has_image(client, icon_url):
        return icon_url

    return ""

def ensure_csv(path: str, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=CSV_COLUMNS,
            quoting=csv.QUOTE_ALL
        )
        writer.writeheader()
        writer.writerows(rows)

def count_zone_total(existing_places: dict[str, dict], zone_id: str) -> int:
    return sum(1 for place in existing_places.values() if place.get("zone_id") == zone_id)

async def run_zone_scan(zone_id: str | None = None) -> None:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("❌ GOOGLE_API_KEY missing.")
        return

    zones = load_zones(ZONES_FILENAME)
    if not zones:
        logger.error("❌ No zones available to scan.")
        return

    if zone_id:
        zones = [zone for zone in zones if zone.get("zone_id") == zone_id]
        if not zones:
            logger.error("❌ Zone %s not found.", zone_id)
            return

    clear_scan_events(SCAN_EVENTS_FILENAME)
    append_scan_event(
        SCAN_EVENTS_FILENAME,
        {
            "type": "scan_start",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "zones": [zone.get("zone_id") for zone in zones]
        }
    )

    google = GooglePlacesClient(api_key)
    crawler = MenuDiscoveryCrawler()
    favicon_client = httpx.AsyncClient(timeout=12.0, follow_redirects=True)

    existing_places: dict[str, dict] = load_existing_places(MASTER_CSV_FILENAME)
    known_place_ids = set(existing_places.keys())

    for zone in zones:
        zone_key = zone.get("zone_id")
        if not zone_key:
            continue

        zone_new_places: list[dict] = []
        zone_new_count = 0
        logger.info("Running zone scanner for %s", zone_key)

        scan_points = generate_scan_points(
            zone.get("center_lat"),
            zone.get("center_lng"),
            zone.get("radius_meters"),
            SCAN_RADIUS_METERS
        )

        for idx, (lat, lng) in enumerate(scan_points, start=1):
            logger.info("Zone %s scan %s/%s started", zone_key, idx, len(scan_points))
            raw_places = await google.text_search(
                SEARCH_QUERY,
                lat,
                lng,
                SCAN_RADIUS_METERS
            )

            for place in raw_places:
                place_id = place.get("id")
                if not place_id or place_id in known_place_ids:
                    continue

                name = place.get("displayName", {}).get("text", "Unknown")
                logger.info("NEW: %s", name)

                details = await google.get_place_details(place_id)
                if not details:
                    continue

                loc = details.get("location", {})
                website = sanitize_one_line(details.get("websiteUri", ""))

                images = google.extract_images(details.get("photos", []))
                menu_url = await crawler.find_menu(website) if website else ""
                logo_url = await fetch_logo_url(favicon_client, website) if website else ""
                discovered_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

                row = {
                    "google_place_id": place_id,
                    "name": name,
                    "latitude": loc.get("latitude"),
                    "longitude": loc.get("longitude"),
                    "zone_id": zone_key,
                    "discovered_at": discovered_at,
                    "rating": details.get("rating"),
                    "reviews_count": details.get("userRatingCount"),
                    "price_level": details.get("priceLevel"),
                    "website": website,
                    "menu_url": menu_url,
                    "cover_image": images["hero_image_url"],
                    "gallery_image_urls": json.dumps(images["gallery_image_urls"]),
                    "logo_url": logo_url or ""
                }

                existing_places[place_id] = row
                zone_new_places.append(row)
                known_place_ids.add(place_id)
                zone_new_count += 1

                append_scan_event(
                    SCAN_EVENTS_FILENAME,
                    {
                        "type": "restaurant_found",
                        "zone_id": zone_key,
                        "name": name,
                        "place_id": place_id
                    }
                )

                await asyncio.sleep(0.25)

            logger.info(
                "Zone %s scan %s/%s complete — %s new restaurants",
                zone_key,
                idx,
                len(scan_points),
                zone_new_count
            )

        zone["scan_count"] = int(zone.get("scan_count", 0)) + 1
        zone["last_scanned_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        zone["last_scan_new_found"] = zone_new_count
        zone["total_discovered"] = count_zone_total(existing_places, zone_key)

        recent_counts = zone.get("recent_new_counts", [])
        if not isinstance(recent_counts, list):
            recent_counts = []
        recent_counts = (recent_counts + [zone_new_count])[-2:]
        zone["recent_new_counts"] = recent_counts
        zone["likely_complete"] = len(recent_counts) == 2 and all(count < 2 for count in recent_counts)

        scan_filename = f"zone_{zone_key}_scan_{zone['scan_count']}.csv"
        ensure_csv(scan_filename, zone_new_places)

        append_scan_event(
            SCAN_EVENTS_FILENAME,
            {
                "type": "zone_scan_complete",
                "zone_id": zone_key,
                "new_found": zone_new_count,
                "total_discovered": zone["total_discovered"],
                "scan_number": zone["scan_count"]
            }
        )

    ensure_csv(MASTER_CSV_FILENAME, list(existing_places.values()))
    save_zones(ZONES_FILENAME, zones)

    await google.close()
    await favicon_client.aclose()

    logger.info("✅ SUCCESS: Generated %s", MASTER_CSV_FILENAME)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Zone scanner")
    parser.add_argument("--zone-id", dest="zone_id", help="Zone id to scan")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run_zone_scan(args.zone_id))
