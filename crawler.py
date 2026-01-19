
import httpx
import logging
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

class MenuDiscoveryCrawler:
    def __init__(self, max_depth=2):
        self.max_depth = max_depth
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        }
        self.menu_keywords = [
            "menu", "food", "drink", "brunch", "dinner", "breakfast", "lunch", 
            "carte", "prix-fixe", "wine-list", "cocktails", "a-la-carte"
        ]

    def is_menu_link(self, href: str, text: str) -> bool:
        """Determines if a link likely points to a menu or PDF menu."""
        href = href.lower()
        text = text.lower()
        
        # Priority 1: Direct PDF links
        if href.endswith(".pdf"):
            return True
            
        # Priority 2: Keyword match in URL or Text
        combined = f"{href} {text}"
        if any(kw in combined for kw in self.menu_keywords):
            # Exclude common false positives
            exclude = ["instagram", "facebook", "twitter", "login", "booking", "reservation"]
            if not any(ex in href for ex in exclude):
                return True
            
        return False

    async def find_menu(self, base_url: str) -> str:
        """Asynchronously crawls a restaurant website to find a menu."""
        if not base_url:
            return ""

        visited = set()
        queue = [(base_url, 0)]
        
        async with httpx.AsyncClient(headers=self.headers, timeout=12.0, follow_redirects=True) as client:
            while queue:
                url, depth = queue.pop(0)
                if url in visited or depth > self.max_depth:
                    continue
                
                visited.add(url)
                try:
                    response = await client.get(url)
                    if response.status_code != 200:
                        continue

                    # Check if the response is actually HTML
                    content_type = response.headers.get("content-type", "").lower()
                    if "text/html" not in content_type:
                        continue

                    soup = BeautifulSoup(response.text, 'html.parser')
                    links = soup.find_all('a', href=True)
                    
                    for link in links:
                        href = link['href']
                        text = link.get_text(strip=True)
                        
                        # Handle relative URLs
                        full_url = urljoin(url, href)
                        
                        # Stay within the same domain
                        if urlparse(full_url).netloc != urlparse(base_url).netloc:
                            continue

                        if self.is_menu_link(href, text):
                            return full_url
                        
                        # Queue internal links for depth search
                        if depth < self.max_depth:
                            queue.append((full_url, depth + 1))
                            
                except Exception as e:
                    logger.debug(f"Crawl error at {url}: {e}")
                    continue
                    
        return ""
