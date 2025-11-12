"""PASS 1 - News Collection Service using Perplexity Sonar"""
import os
import json
import hashlib
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import httpx
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


class NewsCollector:
    """Collects news articles using Perplexity Sonar API"""
    
    def __init__(self):
        self.api_key = os.getenv("PPLX_API_KEY")
        if not self.api_key:
            raise ValueError("PPLX_API_KEY not configured")
            
        self.base_url = "https://api.perplexity.ai"
        self.timeout = 30.0
        self.model = "sonar"
        
    async def collect_news(
        self,
        topic: str,
        time_range: str = "24h",
        limit: int = 10,
        lang: str = "fr"
    ) -> Dict:
        """
        Collect news articles on a topic
        
        Args:
            topic: Topic to search for
            time_range: "24h" or "72h"
            limit: Maximum number of items (6-10)
            lang: Language code
            
        Returns:
            Dict with items list and optional note
        """
        try:
            # Import cache and validate utilities
            from app.utils.cache import MemoryCache
            from app.utils.validate import NewsValidator
            
            cache = MemoryCache()
            validator = NewsValidator()
            
            # Generate cache key
            cache_key = self._generate_cache_key(topic, time_range, lang)
            
            # Check cache first
            cached_result = await cache.get(cache_key)
            if cached_result:
                logger.info(f"Using cached news for {topic}")
                return json.loads(cached_result)
            
            # Build search prompt
            prompt = self._build_collection_prompt(topic, time_range, lang)
            
            # Call Sonar API
            items = await self._call_sonar_api(prompt, time_range)
            
            # Validate and filter items
            validated_items = validator.filter_news_items(items, time_range)
            
            # Check if we need fallback to 72h
            if len(validated_items) < 5 and time_range == "24h":
                logger.info(f"Only {len(validated_items)} items in 24h, falling back to 72h")
                return await self.collect_news(topic, "72h", limit, lang)
            
            # Sort by date descending
            validated_items.sort(key=lambda x: x.get("published_at_ISO", ""), reverse=True)
            
            # Limit to requested number
            validated_items = validated_items[:limit]
            
            result = {
                "items": validated_items,
                "topic": topic,
                "time_range": time_range,
                "collected_at": datetime.utcnow().isoformat()
            }
            
            # Add note if coverage is low
            if len(validated_items) < 3:
                result["note"] = "coverage_low"
            
            # Cache the result for 1 hour
            await cache.set(cache_key, json.dumps(result), ttl=3600)
            
            logger.info(f"Collected {len(validated_items)} news items for {topic}")
            return result
            
        except Exception as e:
            logger.error(f"News collection error: {e}")
            return {
                "items": [],
                "note": "collection_failed",
                "error": str(e)
            }
    
    def _generate_cache_key(self, topic: str, time_range: str, lang: str) -> str:
        """Generate cache key for news collection"""
        date_slot = datetime.now().strftime("%Y%m%d_%H")
        key_string = f"news_{topic}_{time_range}_{lang}_{date_slot}"
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _build_collection_prompt(self, topic: str, time_range: str, lang: str) -> str:
        """Build prompt for news collection"""
        from app.services.news.prompts import COLLECTION_PROMPT_TEMPLATE
        
        time_window = "dernières 24 heures" if time_range == "24h" else "derniers 3 jours"
        
        return COLLECTION_PROMPT_TEMPLATE.format(
            topic=topic,
            time_window=time_window,
            lang=lang
        )
    
    async def _call_sonar_api(self, prompt: str, time_range: str) -> List[Dict]:
        """Call Perplexity Sonar API"""
        
        # Map time range to recency filter
        recency_filter = "day" if time_range == "24h" else "week"
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a news collection assistant. Return ONLY valid JSON with news items."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 2000,
            "search_recency_filter": recency_filter,
            "return_citations": True,
            "search_domain_filter": [
                "lemonde.fr", "lefigaro.fr", "liberation.fr",
                "franceinfo.fr", "bfmtv.com", "reuters.com",
                "lesechos.fr", "latribune.fr", "challenges.fr"
            ]
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers
                )
                
                if response.is_success:
                    result = response.json()
                    
                    # Extract content from response
                    if "choices" in result and result["choices"]:
                        content = result["choices"][0]["message"]["content"]
                        
                        # Parse JSON from content
                        try:
                            # Find JSON in the response
                            import re
                            json_match = re.search(r'\{.*\}', content, re.DOTALL)
                            if json_match:
                                parsed = json.loads(json_match.group())
                                return parsed.get("items", [])
                        except json.JSONDecodeError:
                            logger.error("Failed to parse JSON from Sonar response")
                            return []
                    
                    return []
                    
                else:
                    logger.error(f"Sonar API error: {response.status_code}")
                    return []
                    
        except Exception as e:
            logger.error(f"Sonar API call failed: {e}")
            return []