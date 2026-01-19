
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
        # Use a single client for session pooling
        self.client = httpx.AsyncClient(timeout=30.0)

    async def _request_with_retry(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        retries = 3
        backoff = 1.0
        for i in range(retries):
            try:
                response = await self.client.request(method, url, **kwargs)
                if response.status_code == 403:
                    logger.error("API Key denied access. Ensure Places API (New) is enabled.")
                    return {}
                if response.status_code == 429:
                    logger.warning(f"Rate limited. Waiting {backoff * 2}s...")
                    await asyncio.sleep(backoff * 2)
                    continue
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                if i == retries - 1:
                    logger.error(f"Request failed after {retries} retries: {e}")
                    return {}
                logger.warning(f"Request failed, retrying in {backoff}s... ({e})")
                await asyncio.sleep(backoff)
                backoff *= 2
        return {}

    async def text_search(self, query: str) -> List[Dict[str, Any]]:
        """Handles text search with Soho location bias and pagination."""
        all_places = []
        page_token = None
        
        # Soho, London coordinates
        SOHO_LAT = 51.5136
        SOHO_LNG = -0.1331

        while True:
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": "places.id,places.displayName,places.location,places.formattedAddress,nextPageToken"
            }
            body = {
                "textQuery": query,
                "locationBias": {
                    "circle": {
                        "center": {"latitude": SOHO_LAT, "longitude": SOHO_LNG},
                        "radius": 1000.0 # 1km radius
                    }
                }
            }
            if page_token:
                body["pageToken"] = page_token
            
            data = await self._request_with_retry("POST", self.SEARCH_URL, headers=headers, json=body)
            
            places = data.get("places", [])
            all_places.extend(places)
            
            page_token = data.get("nextPageToken")
            if not page_token:
                break
            
            await asyncio.sleep(1.5) # Safe pagination gap
            
        return all_places

    async def get_place_details(self, place_id: str) -> Dict[str, Any]:
        """Fetches full details including field mask for photos and website."""
        url = self.DETAILS_URL.format(id=place_id)
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": "id,name,displayName,formattedAddress,location,websiteUri,types,photos"
        }
        return await self._request_with_retry("GET", url, headers=headers)

    def get_photo_url(self, photo_name: str) -> str:
        """Constructs a Place Photo URL using the New API format."""
        if not photo_name:
            return ""
        return f"https://places.googleapis.com/v1/{photo_name}/media?maxHeightPx=1600&maxWidthPx=1600&key={self.api_key}"

    async def close(self):
        await self.client.aclose()
