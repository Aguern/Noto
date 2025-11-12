"""Validation utilities for news briefing pipeline"""
import re
from typing import Dict, List
from datetime import datetime, timedelta
from loguru import logger


class NewsValidator:
    """Validates and filters news items and briefs"""
    
    def __init__(self):
        self.max_age_hours = 72
        self.max_brief_words = 250
        self.max_brief_chars = 1000  # Approximate
        
    def filter_news_items(self, items: List[Dict], time_range: str) -> List[Dict]:
        """
        Filter and validate news items
        
        Args:
            items: Raw news items
            time_range: "24h" or "72h"
            
        Returns:
            Filtered and deduplicated items
        """
        if not items:
            return []
        
        # Determine max age based on time range
        max_age = 24 if time_range == "24h" else 72
        cutoff_date = datetime.utcnow() - timedelta(hours=max_age)
        
        valid_items = []
        seen_domains = set()
        seen_titles = set()
        
        for item in items:
            # Skip if missing required fields
            if not all(k in item for k in ["source", "title", "url", "published_at_ISO"]):
                continue
            
            # Parse and validate date
            try:
                pub_date = datetime.fromisoformat(
                    item["published_at_ISO"].replace("Z", "+00:00")
                )
                
                # Skip if too old
                if pub_date < cutoff_date:
                    continue
                    
                # Special case: Allow weekend sports news on Monday morning
                if time_range == "72h" and datetime.utcnow().weekday() == 0:  # Monday
                    weekend_cutoff = datetime.utcnow() - timedelta(hours=96)
                    if pub_date < weekend_cutoff:
                        continue
                        
            except (ValueError, AttributeError):
                logger.warning(f"Invalid date format: {item.get('published_at_ISO')}")
                continue
            
            # Deduplicate by domain
            domain = self._extract_domain(item["url"])
            if domain in seen_domains:
                continue
            seen_domains.add(domain)
            
            # Deduplicate by title (case-insensitive)
            title_key = item["title"].lower().strip()
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            
            valid_items.append(item)
        
        return valid_items
    
    def validate_brief_output(self, brief: Dict, max_words: int = 250) -> Dict:
        """
        Validate and fix brief output
        
        Args:
            brief: Brief dictionary from PASS 2
            max_words: Maximum allowed words
            
        Returns:
            Validated and potentially truncated brief
        """
        if not brief:
            return {"brief_text": "", "tts_script": "", "citations": []}
        
        # Validate brief_text length
        brief_text = brief.get("brief_text", "")
        words = brief_text.split()
        
        if len(words) > max_words:
            # Truncate to max words
            brief_text = " ".join(words[:max_words])
            logger.warning(f"Brief truncated from {len(words)} to {max_words} words")
        
        # Validate TTS script (90-140 words)
        tts_script = brief.get("tts_script", "")
        tts_words = tts_script.split()
        
        if len(tts_words) < 90:
            # Extend if too short
            tts_script = brief_text[:500] if len(brief_text) > 500 else brief_text
            tts_words = tts_script.split()[:140]
            tts_script = " ".join(tts_words)
        elif len(tts_words) > 140:
            # Truncate if too long
            tts_script = " ".join(tts_words[:140])
        
        # Validate citations
        citations = brief.get("citations", [])
        valid_citations = []
        cutoff_date = datetime.utcnow() - timedelta(hours=72)
        
        for citation in citations:
            if not isinstance(citation, dict):
                continue
                
            # Check required fields
            if not all(k in citation for k in ["source", "title", "url"]):
                continue
            
            # Check date if present
            if "published_at_ISO" in citation:
                try:
                    pub_date = datetime.fromisoformat(
                        citation["published_at_ISO"].replace("Z", "+00:00")
                    )
                    if pub_date < cutoff_date:
                        continue
                except (ValueError, AttributeError):
                    pass
            
            valid_citations.append(citation)
        
        # Check minimum citations
        if len(valid_citations) < 3:
            brief_text += " Peu de nouvelles confirmées aujourd'hui. À surveiller."
        
        return {
            "brief_text": brief_text,
            "tts_script": tts_script,
            "citations": valid_citations
        }
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL"""
        import re
        match = re.search(r'https?://([^/]+)', url)
        if match:
            return match.group(1).lower()
        return url.lower()
    
    def is_news_query(self, text: str) -> bool:
        """
        Check if a query is asking for news/current events
        
        Args:
            text: User query text
            
        Returns:
            True if query contains temporal markers
        """
        temporal_markers = [
            "aujourd'hui", "aujourd hui", "today",
            "hier", "yesterday", "ayer",
            "dernière", "dernières", "latest", "recent",
            "ce matin", "this morning", "esta mañana",
            "depuis", "since", "desde",
            "24h", "24 h", "24 heures",
            "actualité", "actualités", "news", "nouvelles"
        ]
        
        text_lower = text.lower()
        return any(marker in text_lower for marker in temporal_markers)