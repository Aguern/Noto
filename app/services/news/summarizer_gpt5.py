"""PASS 2 - News Summarization Service using GPT-5 mini"""
import os
import json
from typing import Dict, List, Optional
from datetime import datetime
import httpx
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


class NewsSummarizer:
    """Generates news briefs using GPT-5 mini"""
    
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not configured")
            
        self.base_url = "https://api.openai.com/v1"
        self.timeout = 30.0
        self.model = "gpt-5-nano-2025-08-07"  # GPT-5 nano
        
    async def brief_from_items(
        self,
        items: List[Dict],
        first_name: str,
        max_words: int = 250,
        audio_words: int = 140,
        lang: str = "fr"
    ) -> Dict:
        """
        Generate brief from news items
        
        Args:
            items: List of news items from PASS 1
            first_name: User's first name
            max_words: Maximum words for text brief
            audio_words: Target words for TTS script (90-140)
            lang: Language code
            
        Returns:
            Dict with brief_text, tts_script, and citations
        """
        try:
            from app.utils.validate import NewsValidator
            validator = NewsValidator()
            
            # Filter items to ensure they're within 72h
            valid_items = validator.filter_news_items(items, "72h")
            
            if len(valid_items) < 3:
                # Not enough news
                return self._generate_low_coverage_response(first_name, valid_items)
            
            # Build summarization prompt
            prompt = self._build_summary_prompt(
                valid_items, first_name, max_words, audio_words, lang
            )
            
            # Call GPT-5 mini API
            result = await self._call_gpt5_api(prompt)
            
            if result:
                # Validate output
                validated_result = validator.validate_brief_output(result, max_words)
                
                # Ensure citations are from provided items
                validated_result["citations"] = self._filter_citations(
                    validated_result.get("citations", []), valid_items
                )
                
                return validated_result
            else:
                return self._generate_fallback_response(first_name, valid_items)
                
        except Exception as e:
            logger.error(f"Brief generation error: {e}")
            return self._generate_fallback_response(first_name, items)
    
    def _build_summary_prompt(
        self,
        items: List[Dict],
        first_name: str,
        max_words: int,
        audio_words: int,
        lang: str
    ) -> str:
        """Build prompt for news summarization"""
        from app.services.news.prompts import SUMMARY_PROMPT_TEMPLATE
        
        # Format items for prompt
        items_text = json.dumps(items, ensure_ascii=False, indent=2)
        
        return SUMMARY_PROMPT_TEMPLATE.format(
            first_name=first_name,
            items=items_text,
            max_words=max_words,
            audio_words=audio_words,
            lang=lang
        )
    
    async def _call_gpt5_api(self, prompt: str) -> Optional[Dict]:
        """Call OpenAI GPT-5 mini API"""
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a news brief assistant. Generate ONLY valid JSON output with brief_text, tts_script, and citations array. Use ONLY the provided news items. Style: oral, short sentences, no markdown."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 1500,
            "response_format": {"type": "json_object"}
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
                        
                        # Parse JSON
                        try:
                            parsed = json.loads(content)
                            return parsed
                        except json.JSONDecodeError:
                            logger.error("Failed to parse JSON from GPT-5 response")
                            return None
                    
                    return None
                    
                else:
                    logger.error(f"GPT-5 API error: {response.status_code}")
                    return None
                    
        except Exception as e:
            logger.error(f"GPT-5 API call failed: {e}")
            return None
    
    def _filter_citations(self, citations: List[Dict], valid_items: List[Dict]) -> List[Dict]:
        """Ensure citations are only from provided items"""
        valid_urls = {item.get("url") for item in valid_items if item.get("url")}
        
        filtered_citations = []
        for citation in citations:
            if citation.get("url") in valid_urls:
                filtered_citations.append(citation)
        
        return filtered_citations
    
    def _generate_low_coverage_response(self, first_name: str, items: List[Dict]) -> Dict:
        """Generate response when coverage is low"""
        if items:
            sources_text = " ".join([f"selon {item.get('source', 'une source')}" for item in items[:2]])
            brief_text = f"Bonjour {first_name}, peu d'actualités confirmées aujourd'hui. {sources_text}. À surveiller dans les prochaines heures."
        else:
            brief_text = f"Bonjour {first_name}, aucune actualité significative trouvée pour le moment. Je continuerai à surveiller."
        
        tts_script = brief_text[:140] if len(brief_text) > 140 else brief_text
        
        return {
            "brief_text": brief_text,
            "tts_script": tts_script,
            "citations": items[:3] if items else []
        }
    
    def _generate_fallback_response(self, first_name: str, items: List[Dict]) -> Dict:
        """Generate fallback response on error"""
        brief_text = f"Bonjour {first_name}, j'ai rencontré une difficulté technique. Voici les dernières actualités disponibles."
        
        if items:
            # Add first 2-3 headlines
            for item in items[:3]:
                title = item.get("title", "")
                source = item.get("source", "")
                if title:
                    brief_text += f" {title} selon {source}."
        
        # Ensure max 250 words
        words = brief_text.split()
        if len(words) > 250:
            brief_text = " ".join(words[:250])
        
        # TTS script (shorter)
        tts_words = brief_text.split()[:140]
        tts_script = " ".join(tts_words)
        
        return {
            "brief_text": brief_text,
            "tts_script": tts_script,
            "citations": items[:5] if items else []
        }