import httpx
import logging
import asyncio
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class GooglePlacesClient:
    SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
    DETAILS_URL = "https://places.googleapis.com/v1/places/{id}"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=30.0)

    async def _request_with_retry(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        retries = 3
        backoff = 1.0

        for attempt in range(retries):
            try:
                response = await self.client.request(method, url, **kwargs)

                if response.status_code == 403:
                    logger.error("❌ Google API key rejected (403). Check Places API (New) is enabled.")
                    return {}

                if response.status_code == 429:
                    logger.warning(f"⚠️ Rate limited. Sleeping {backoff}s...")
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue

                response.raise_for_status()
                return response.json()

            except Exception as e:
                if attempt == retries - 1:
                    logger.error(f"❌ Request failed after retries: {e}")
                    return {}
                await asyncio.sleep(backoff)
                backoff *= 2

        return {}

    # -----------------------------
    # STEP 1: DISCOVER PLACES (SOHO)
    # -----------------------------
    async def text_search(self, query: str) -> List[Dict[str, Any]]:
        SOHO_LAT = 51.5136
        SOHO_LNG = -0.1331

        all_places = []
        page_token = None

        while True:
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": (
                    "places.id,"
                    "places.displayName,"
                    "places.location,"
                    "places.formattedAddress,"
                    "nextPageToken"
                ),
            }

            body = {
                "textQuery": query,
                "locationBias": {
                    "circle": {
                        "center": {"latitude": SOHO_LAT, "longitude": SOHO_LNG},
                        "radius": 1000.0,
                    }
                },
            }

            if page_token:
                body["pageToken"] = page_token

            data = await self._request_with_retry(
                "POST",
                self.SEARCH_URL,
                headers=headers,
                json=body,
            )

            places = data.get("places", [])
            all_places.extend(places)

            page_token = data.get("nextPageToken")
            if not page_token:
                break

            await asyncio.sleep(1.5)

        return all_places

    # -----------------------------
    # STEP 2: ENRICH PLACE DETAILS
    # -----------------------------
    async def get_place_details(self, place_id: str) -> Dict[str, Any]:
        url = self.DETAILS_URL.format(id=place_id)

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": (
                "id,"
                "displayName,"
                "formattedAddress,"
                "location,"
                "websiteUri,"
                "types,"
                "rating,"
                "userRatingCount,"
                "priceLevel,"
                "photos"
            ),
        }

        return await self._request_with_retry("GET", url, headers=headers)

    # -----------------------------
    # STEP 3: IMAGE URL HELPERS
    # -----------------------------
    def build_photo_url(self, photo_name: str, height: int = 1600) -> str:
        if not photo_name:
            return ""
        return (
            f"https://places.googleapis.com/v1/"
            f"{photo_name}/media"
            f"?maxHeightPx={height}&key={self.api_key}"
        )

    def extract_images(self, photos: List[Dict[str, Any]]) -> Dict[str, Any]:
        photo_names = [p.get("name") for p in photos if p.get("name")]

        hero = self.build_photo_url(photo_names[0]) if photo_names else ""
        gallery = [
            self.build_photo_url(name, height=1200)
            for name in photo_names[:5]
        ]

        return {
            "hero_image_url": hero,
            "gallery_image_urls": gallery,
        }

    async def close(self):
        await self.client.aclose()
