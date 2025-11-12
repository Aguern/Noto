"""Perplexica integration service - High-quality AI-powered search"""
import json
import asyncio
from typing import Dict, List, Optional
from datetime import datetime
import httpx
from loguru import logger
from dotenv import load_dotenv

# 2025 AI Content Filtering
from .content_filter import ContentFilter

load_dotenv()


class PerplexicaService:
    """Service for integrating Perplexica AI-powered search"""
    
    def __init__(self):
        self.base_url = "http://localhost:3003"  # Fixed port - Perplexica runs on 3003
        self.timeout = 45.0  # Timeout optimisé pour extractions complètes sans échec
        self.content_filter = ContentFilter()  # 2025 AI content filtering
        self.default_chat_model = {
            "provider": "groq",
            "name": "llama-3.1-8b-instant"  # Updated Groq model - using 'name' field per API docs
        }
        self.default_embedding_model = {
            "provider": "transformers", 
            "name": "xenova-bge-small-en-v1.5"  # Smaller, faster embeddings model
        }
    
    async def search_with_ai(
        self,
        query: str,
        focus_mode: str = "webSearch",
        language: str = "fr"
    ) -> Dict:
        """
        Perform AI-powered search using Perplexica
        
        Args:
            query: Search query
            focus_mode: webSearch, academic, news, etc.
            language: Language preference
            
        Returns:
            Dict with AI response and sources
        """
        start_time = datetime.utcnow()
        
        try:
            logger.info(f"Perplexica AI search for: {query}")
            
            # Ensure proper UTF-8 encoding for French queries
            
            payload = {
                "query": query,
                "focusMode": focus_mode,
                "chatModel": self.default_chat_model,
                "embeddingModel": self.default_embedding_model,
                "optimizationMode": "balanced",  # Équilibre qualité/vitesse
                "systemInstructions": "Chercher prioritairement sources françaises (Le Figaro, Libération, BFM, France Info). Éviter versions anglaises /en/. Actualités récentes 48h." if language == "fr" else "",
                "history": [],  # Vide pour recherche fraîche
                "stream": False
            }
            
            # Call Perplexica API
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/search",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                if not response.is_success:
                    logger.error(f"Perplexica API error: {response.status_code} - {response.text}")
                    return self._create_error_response(f"API Error: {response.status_code}")
                
                result = response.json()
                
                processing_time = (datetime.utcnow() - start_time).total_seconds()
                logger.info(f"Perplexica search completed in {processing_time:.2f}s")
                
                # Rerank and enrich top sources
                sources = result.get("sources", [])
                ranked_sources = self._rerank_sources(sources)
                enriched_sources = await self._enrich_top_sources(ranked_sources)
                
                return {
                    "success": True,
                    "message": result.get("message", ""),
                    "sources": enriched_sources,
                    "processing_time": processing_time,
                    "timestamp": datetime.utcnow().isoformat(),
                    "query": query,
                    "focus_mode": focus_mode
                }
                
        except httpx.TimeoutException:
            logger.warning(f"Perplexica search timeout for: {query} - skipping")
            return {
                "success": False,
                "error": "Timeout - sources indisponibles",
                "message": "",
                "sources": [],
                "processing_time": self.timeout
            }
            
        except Exception as e:
            logger.warning(f"Perplexica search error: {str(e)} - skipping")
            return {
                "success": False,
                "error": str(e),
                "message": "",
                "sources": [],
                "processing_time": (datetime.utcnow() - start_time).total_seconds()
            }
    
    def _rerank_sources(self, sources: List[Dict]) -> List[Dict]:
        """Rerank sources by quality, accessibility and relevance"""
        
        # TESTED extraction-friendly sources only (no blocked sites)
        quality_scores = {
            # French VERIFIED WORKING (tested extraction)
            'france24.com': 10,  # ✅ 664 chars
            'rfi.fr': 10,  # ✅ 3553 chars
            'lci.fr': 10,  # ✅ 8886 chars - excellent!
            '20minutes.fr': 9,  # ✅ 1369 chars
            'europe1.fr': 9,  # ✅ 1689 chars
            'rtl.fr': 9,  # ✅ 2924 chars  
            'franceinter.fr': 9,  # ✅ 3020 chars
            'sudouest.fr': 9,  # ✅ 4830 chars
            'ladepeche.fr': 8,  # ✅ 1818 chars
            'lexpress.fr': 9,  # ✅ 1833 chars
            'lepoint.fr': 10,  # ✅ 8230 chars - excellent!
            'nouvelobs.com': 8,  # ✅ 588 chars (slow 4.6s)
            'marianne.net': 8,  # ✅ 524 chars
            'challenges.fr': 9,  # ✅ 4000 chars
            'huffingtonpost.fr': 9,  # ✅ 2477 chars
            'slate.fr': 9,  # ✅ 3687 chars
            'cnews.fr': 7,  # ✅ 510 chars (short but works)
            
            # International TESTED working
            'apnews.com': 9,  # Usually works
            'bbc.com': 8,  # Sometimes works
            'theguardian.com': 8,  # Sometimes works
            'euronews.com': 8,  # Usually works
            'politico.eu': 7,  # Sometimes works
            
            # DO NOT USE - Blocked/Failed in tests
            # franceinfo.fr, francetvinfo.fr, bfmtv.com - extraction vide
            # ouest-france.fr, lavoixdunord.fr - téléchargement échoué
            # reuters.com, lemonde.fr, lefigaro.fr - bloqués/paywall
            # aljazeera.com - retiré sur demande
        }
        
        def score_source(source):
            url = source.get('metadata', {}).get('url', '')
            content = source.get('pageContent', '')
            
            # Domain score - priority to extraction-friendly sites
            domain_score = 0
            for domain, points in quality_scores.items():
                if domain in url:
                    domain_score = points
                    break
            
            # Penalize blocked sites heavily
            blocked_domains = ['lemonde.fr', 'lefigaro.fr', 'reuters.com', 'bfmtv.com', 
                             'franceinfo.fr', 'ouest-france.fr', 'leparisien.fr']
            if any(blocked in url for blocked in blocked_domains):
                domain_score = 1  # Very low score for blocked sites
            
            # Freshness bonus
            freshness = 4 if any(fresh in content.lower() for fresh in ['il y a 1 jour', 'today', 'hier']) else 0
            
            # Content length bonus (small)
            length_bonus = min(len(content) / 200, 2)
            
            return domain_score + freshness + length_bonus
        
        ranked = sorted(sources, key=score_source, reverse=True)
        logger.info(f"Reranked {len(sources)} sources")
        return ranked
    
    async def _enrich_top_sources(self, sources: List[Dict]) -> List[Dict]:
        """Enrich only top 3-5 sources with full content"""
        import asyncio
        
        try:
            import trafilatura
        except ImportError:
            logger.warning("Trafilatura not installed")
            return sources
        
        # Take top 3 for enrichment (fast)
        top_sources = sources[:3]
        other_sources = sources[3:]
        
        async def enrich_source(source):
            url = source.get('metadata', {}).get('url', '')
            if not url:
                return source
                
            try:
                # Fetch with timeout
                downloaded = await asyncio.get_event_loop().run_in_executor(
                    None, trafilatura.fetch_url, url
                )
                
                if downloaded:
                    text = trafilatura.extract(
                        downloaded,
                        include_comments=False,
                        target_language='fr'
                    )
                    
                    if text and len(text) > 300:
                        enriched = source.copy()
                        enriched['pageContent'] = text[:1000] + "..." if len(text) > 1000 else text
                        enriched['enriched'] = True
                        logger.info(f"✅ Enriched: {url[:40]}...")
                        return enriched
                        
            except Exception as e:
                logger.warning(f"Failed enriching: {str(e)[:30]}")
                
            return source
        
        # Parallel enrichment with longer timeout for better success rate
        tasks = [asyncio.wait_for(enrich_source(s), timeout=8.0) for s in top_sources]
        
        try:
            enriched_top = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Handle errors
            final_top = []
            for i, result in enumerate(enriched_top):
                if isinstance(result, Exception):
                    final_top.append(top_sources[i])
                else:
                    final_top.append(result)
                    
            return final_top + other_sources
            
        except Exception as e:
            logger.error(f"Enrichment error: {e}")
            return sources
    
    async def _enrich_sources_with_trafilatura(self, sources: List[Dict]) -> List[Dict]:
        """Enrich source snippets with full article content using trafilatura"""
        try:
            import trafilatura
        except ImportError:
            logger.warning("Trafilatura not installed, returning original sources")
            return sources
        
        enriched = []
        max_sources_to_enrich = 5  # Limite pour éviter timeout
        
        logger.info(f"Enriching {len(sources)} sources (max {max_sources_to_enrich})")
        
        for idx, source in enumerate(sources):
            url = source.get('metadata', {}).get('url', '')
            
            # Skip non-URLs or keep original for sources beyond limit
            if not url or 'http' not in url or idx >= max_sources_to_enrich:
                enriched.append(source)
                continue
            
            try:
                # Quick download with short timeout
                downloaded = trafilatura.fetch_url(url)
                if downloaded:
                    # Fast extraction
                    full_text = trafilatura.extract(
                        downloaded, 
                        include_comments=False, 
                        include_tables=False,
                        target_language='fr'  # Force French extraction
                    )
                    
                    if full_text and len(full_text) > 200:
                        # Keep first 800 chars for speed
                        enriched_content = full_text[:800] + "..." if len(full_text) > 800 else full_text
                        
                        # Update source with enriched content
                        enriched_source = source.copy()
                        enriched_source['pageContent'] = enriched_content
                        enriched_source['enriched'] = True
                        enriched.append(enriched_source)
                        logger.info(f"✅ Enriched source {idx+1}: {url[:40]}... ({len(full_text)} chars)")
                    else:
                        # Keep original if extraction too short
                        enriched.append(source)
                        logger.debug(f"⚠️ Source {idx+1} content too short, keeping original")
                else:
                    enriched.append(source)
                    logger.debug(f"⚠️ Source {idx+1} download failed, keeping original")
                    
            except Exception as e:
                logger.warning(f"❌ Failed to enrich source {idx+1}: {str(e)[:50]}")
                enriched.append(source)
        
        logger.info(f"Enrichment complete: {len([s for s in enriched if s.get('enriched')])} sources enriched")
        return enriched
    
    async def search_multi_interests(
        self,
        interests: List[str],
        base_query: str = "actualités",
        max_results_per_interest: int = 1
    ) -> Dict:
        """
        Perform parallel searches for multiple interests (like our current system)
        
        Args:
            interests: List of user interests (e.g., ["économie", "sport", "tech"])
            base_query: Base query template
            max_results_per_interest: Limit results per interest
            
        Returns:
            Dict with aggregated results by interest
        """
        try:
            logger.info(f"Multi-interest Perplexica search: {interests}")
            
            # Create search tasks for each interest with proper encoding and date filtering
            def remove_accents(text):
                import unicodedata
                return ''.join(c for c in unicodedata.normalize('NFD', text) 
                             if unicodedata.category(c) != 'Mn')
            
            tasks = []
            for interest in interests:
                # Remove accents from interest
                clean_interest = remove_accents(interest)
                # Build intelligent query based on interest type and temporal context
                from datetime import datetime
                import urllib.parse
                
                # Build French query: actualité + centre d'intérêt + date du jour
                from datetime import datetime
                import locale
                
                # Set French locale for date formatting
                try:
                    locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
                except:
                    try:
                        locale.setlocale(locale.LC_TIME, 'fr_FR')
                    except:
                        pass  # Fallback to default locale
                
                # Format date in French: "29 août 2025"
                today_french = datetime.now().strftime("%d %B %Y")
                
                # Normalize interest to French
                clean_interest_french = self._normalize_french_interest(clean_interest)
                
                # Build simple French query: actualité + intérêt + date
                interest_query = f"actualité {clean_interest_french} {today_french}"
                task = self.search_with_ai(interest_query, focus_mode="webSearch")
                tasks.append(task)
            
            # Execute searches SEQUENTIALLY to avoid overloading Perplexica/SearxNG
            results = []
            for task in tasks:
                try:
                    result = await task
                    results.append(result)
                    # Small pause between requests to prevent overload
                    await asyncio.sleep(0.5)
                except Exception as e:
                    results.append(e)
            
            # Aggregate successful results
            aggregated_results = {
                "success": True,
                "interests_covered": [],
                "all_sources": [],
                "combined_message": "",
                "processing_time": 0,
                "errors": []
            }
            
            for i, result in enumerate(results):
                interest = interests[i]
                
                if isinstance(result, Exception):
                    logger.error(f"Error for interest {interest}: {result}")
                    aggregated_results["errors"].append(f"{interest}: {str(result)}")
                    continue
                
                if result.get("success"):
                    aggregated_results["interests_covered"].append(interest)
                    aggregated_results["all_sources"].extend(result.get("sources", []))
                    
                    # Add interest context to message
                    message = result.get("message", "")
                    if message:
                        aggregated_results["combined_message"] += f"\n\n**{interest.title()}:**\n{message}"
                    
                    aggregated_results["processing_time"] += result.get("processing_time", 0)
                else:
                    aggregated_results["errors"].append(f"{interest}: {result.get('error', 'Unknown error')}")
            
            # Clean up combined message
            aggregated_results["combined_message"] = aggregated_results["combined_message"].strip()
            
            logger.info(f"Multi-interest search completed - {len(aggregated_results['interests_covered'])} interests covered")
            
            return aggregated_results
            
        except Exception as e:
            logger.error(f"Multi-interest search error: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "interests_covered": [],
                "all_sources": [],
                "combined_message": ""
            }
    
    def format_for_whatsapp(self, perplexica_result: Dict, user_name: str = "Nicolas", user_interests: List[str] = None) -> Dict:
        """
        Format Perplexica results for WhatsApp/audio consumption
        
        Args:
            perplexica_result: Result from Perplexica search
            user_name: User's name for personalization
            
        Returns:
            Dict formatted for WhatsApp pipeline
        """
        try:
            if not perplexica_result.get("success"):
                return {
                    "summary": "Désolé, impossible de récupérer les actualités pour le moment.",
                    "sources": [],
                    "tokens_used": 0,
                    "processing_time": perplexica_result.get("processing_time", 0)
                }
            
            # Extract message and clean for audio
            message = perplexica_result.get("combined_message") or perplexica_result.get("message", "")
            
            # Get interests covered for better formatting
            interests_covered = perplexica_result.get("interests_covered", [])
            
            # Clean message for audio synthesis
            audio_text = self._clean_for_audio(message, user_name, interests_covered, user_interests)
            
            # Format sources for WhatsApp
            sources = self._format_sources_for_whatsapp(
                perplexica_result.get("all_sources") or perplexica_result.get("sources", [])
            )
            
            return {
                "summary": audio_text,
                "sources": sources,
                "tokens_used": 0,  # Perplexica doesn't expose token usage
                "processing_time": perplexica_result.get("processing_time", 0),
                "interests_covered": perplexica_result.get("interests_covered", []),
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"WhatsApp formatting error: {str(e)}")
            return {
                "summary": "Erreur lors du formatage des résultats.",
                "sources": [],
                "tokens_used": 0,
                "processing_time": 0
            }
    
    def _clean_for_audio(self, text: str, user_name: str, interests_covered: List[str] = None, all_user_interests: List[str] = None) -> str:
        """Clean text for natural audio synthesis - Format Noto français générique"""
        from datetime import datetime
        import re
        
        if not text or len(text.strip()) < 10:
            return f"Bonjour {user_name}, aucune actualité significative trouvée aujourd'hui."
        
        # Remove source references BUT KEEP ** markers for parsing
        text = re.sub(r'\([Ss]ource[^)]*\)', '', text)
        text = re.sub(r'\(article \d+\)', '', text)
        # Don't remove ** yet - we need them for parsing!
        
        # Remove common English structural words
        english_patterns = [
            "Background:", "Key Players:", "A Deep Dive into", "In this response", 
            "We will delve", "This move", "The current", "Background", "Key Players"
        ]
        for pattern in english_patterns:
            text = text.replace(pattern, "")
        
        # Clean and extract meaningful sentences
        sentences = []
        for sentence in text.split('.'):
            sentence = sentence.strip()
            if len(sentence) < 15:  # Skip very short fragments
                continue
                
            # Skip numbered lists and structural elements
            if sentence.startswith(('1.', '2.', '3.', '4.', '5.', 'In ', 'The ', 'This ')):
                continue
                
            sentences.append(sentence)
        
        # Create Noto format with dynamic interests
        months_fr = {
            'January': 'janvier', 'February': 'février', 'March': 'mars',
            'April': 'avril', 'May': 'mai', 'June': 'juin',
            'July': 'juillet', 'August': 'août', 'September': 'septembre',
            'October': 'octobre', 'November': 'novembre', 'December': 'décembre'
        }
        current_date = datetime.now().strftime("%-d %B")
        for en, fr in months_fr.items():
            current_date = current_date.replace(en, fr)
        noto_summary = f"Bonjour {user_name}, voici les actualités du {current_date}."
        
        # Simple approach: just extract key sentences from the text
        if interests_covered and text:
            # Parse content by interest from combined message
            content_by_interest = {}
            seen_content = set()  # Track to avoid duplicates
            
            # Extract content for each interest
            for interest in interests_covered:
                interest_pattern = f"**{interest.title()}:**"
                if interest_pattern in text:
                    # Extract content after this interest marker
                    start_idx = text.find(interest_pattern) + len(interest_pattern)
                    
                    # Find next INTEREST marker (not just any **), or end of text
                    next_interest_idx = len(text)  # Default to end of text
                    for other_interest in interests_covered:
                        if other_interest != interest:
                            other_pattern = f"**{other_interest.title()}:**"
                            other_idx = text.find(other_pattern, start_idx)
                            if other_idx != -1 and other_idx < next_interest_idx:
                                next_interest_idx = other_idx
                    
                    interest_text = text[start_idx:next_interest_idx]
                    
                    # AI-powered content filtering (2025 approach)
                    sentences = []
                    for sentence in interest_text.split('.'):
                        sentence = sentence.strip()
                        # Remove interest name if it appears at the start
                        if sentence.lower().startswith(interest.lower() + ':'):
                            sentence = sentence[len(interest)+1:].strip()
                        
                        # Clean English words and poor translations
                        sentence = self._clean_english_and_translations(sentence)
                        
                        if len(sentence) > 20:
                            sentences.append(sentence)
                    
                    # Use AI content filter to get high-quality, relevant sentences
                    filtered_sentences = self.content_filter.get_top_content(
                        sentences=sentences,
                        interest=interest,
                        max_items=4,  # Max 4 per interest for detailed content
                        min_score=0.6  # Balanced threshold - keeps legitimate content while filtering noise
                    )
                    
                    # Track filtered content to avoid cross-section duplication
                    interest_sentences = []
                    for sentence in filtered_sentences:
                        if not self._is_similar_content(sentence, seen_content):
                            interest_sentences.append(sentence)
                            seen_content.add(sentence.lower())
                    
                    if interest_sentences:
                        content_by_interest[interest] = interest_sentences[:4]  # Max 4 per interest for more detail
            
            # Build summary by interest
            processed_interests = 0
            for i, interest in enumerate(interests_covered):
                if interest in content_by_interest and content_by_interest[interest]:
                    content = ". ".join(content_by_interest[interest])
                    
                    # Add natural transitions based on position among PROCESSED interests
                    total_with_content = len([k for k in content_by_interest.keys() if content_by_interest[k]])
                    
                    if processed_interests == 0:
                        # First section - more natural openings based on topic
                        if 'politique' in interest.lower():
                            transition = "Côté politique française,"
                        elif 'économie' in interest.lower():
                            transition = "Sur le plan économique,"
                        elif 'sport' in interest.lower() or 'football' in interest.lower() or 'NBA' in interest.upper():
                            transition = "Dans le sport,"
                        elif 'actualités générales' in interest.lower() or 'général' in interest.lower():
                            transition = "Dans l'actualité,"
                        else:
                            transition = f"Concernant {interest},"
                    elif processed_interests == total_with_content - 1:
                        # Last section
                        if 'football' in interest.lower() or 'sport' in interest.lower():
                            transition = "Enfin, côté sport,"
                        else:
                            transition = f"Enfin, pour {interest},"
                    else:
                        # Middle sections
                        if 'économie' in interest.lower():
                            transition = "Sur le plan économique,"
                        elif 'international' in interest.lower():
                            transition = "À l'international,"
                        else:
                            transition = f"Concernant {interest},"
                    
                    # Clean the content from any remaining markers
                    content_clean = content.replace("**", "").replace("*", "")
                    noto_summary += f" {transition} {content_clean.lower()}."
                    processed_interests += 1
                
                # If no content found for this interest, skip it silently (more natural)
            
                
        else:
            # Fallback: use first few sentences
            if sentences:
                main_content = ". ".join(sentences[:2])
                noto_summary += f" {main_content}."
        
        # Add closing
        noto_summary += " Bonne journée."
        
        # Allow longer content if quality information is available
        # Only cut if extremely long (5+ minutes audio would be ~300 words)
        words = noto_summary.split()
        if len(words) > 300:
            noto_summary = " ".join(words[:300]) + ". Bonne journée."
        
        return noto_summary
    

    def _clean_english_and_translations(self, sentence: str) -> str:
        """Clean English words and poor translations from sentence"""
        # Common English to French replacements
        replacements = {
            'crisis politique': 'crise politique',
            'breaking news': '',
            'latest update': '',
            'sentiments économiques': 'confiance économique',
            'sentiment économique': 'confiance économique',
            'economic sentiment': 'confiance économique',
            'government': 'gouvernement',
            'parliament': 'parlement',
            'minister': 'ministre',
            'economy': 'économie'
        }
        
        sentence_clean = sentence
        for english, french in replacements.items():
            sentence_clean = sentence_clean.replace(english, french)
        
        # Remove questions that often come from titles
        import re
        sentence_clean = re.sub(r'\s*:\s*quel.*?\?\s*', ' ', sentence_clean, flags=re.IGNORECASE)
        sentence_clean = re.sub(r'\s*:\s*que.*?\?\s*', ' ', sentence_clean, flags=re.IGNORECASE)
        sentence_clean = re.sub(r'\s*:\s*comment.*?\?\s*', ' ', sentence_clean, flags=re.IGNORECASE)
        
        # Clean extra spaces
        sentence_clean = ' '.join(sentence_clean.split())
        
        return sentence_clean.strip()

    def _is_similar_content(self, sentence: str, seen_content: set) -> bool:
        """Check if sentence is too similar to already seen content"""
        sentence_words = set(sentence.lower().split())
        
        for seen in seen_content:
            seen_words = set(seen.split())
            
            # Calculate similarity based on common words
            if len(sentence_words) > 0 and len(seen_words) > 0:
                common_words = sentence_words.intersection(seen_words)
                similarity = len(common_words) / min(len(sentence_words), len(seen_words))
                
                # If more than 60% similar, consider it a duplicate
                if similarity > 0.6:
                    return True
        
        return False

    def _sentence_relates_to_interest(self, sentence: str, interest: str) -> bool:
        """Check if a sentence relates to a specific interest"""
        sentence_lower = sentence.lower()
        interest_lower = interest.lower()
        
        # Direct keyword match
        if interest_lower in sentence_lower:
            return True
        
        # Semantic mapping for common interests
        semantic_map = {
            'politique': ['gouvernement', 'ministre', 'assemblée', 'élection', 'parti', 'député', 'sénat'],
            'économie': ['croissance', 'inflation', 'marché', 'banque', 'euro', 'pib', 'emploi'],
            'football': ['match', 'équipe', 'joueur', 'championnat', 'ligue', 'but', 'entraîneur'],
            'sport': ['match', 'équipe', 'joueur', 'championnat', 'compétition', 'athlète'],
            'technologie': ['intelligence artificielle', 'ai', 'numérique', 'startup', 'innovation'],
            'santé': ['médecin', 'hôpital', 'traitement', 'vaccin', 'maladie', 'santé publique'],
        }
        
        # Check semantic keywords
        for key, keywords in semantic_map.items():
            if key in interest_lower:
                return any(keyword in sentence_lower for keyword in keywords)
        
        # Fallback: check if sentence contains any word from the interest
        interest_words = interest_lower.split()
        return any(word in sentence_lower for word in interest_words if len(word) > 3)
        
        return False
    
    def _format_sources_for_whatsapp(self, sources: List[Dict]) -> List[Dict]:
        """Format sources for WhatsApp display"""
        formatted_sources = []
        
        for i, source in enumerate(sources[:5], 1):  # Limit to 5 sources
            formatted_source = {
                "number": i,
                "title": source.get("metadata", {}).get("title", "Source inconnue"),
                "url": source.get("metadata", {}).get("url", ""),
                "domain": self._extract_domain(source.get("metadata", {}).get("url", ""))
            }
            formatted_sources.append(formatted_source)
        
        return formatted_sources
    
    def _extract_domain(self, url: str) -> str:
        """Extract clean domain from URL"""
        try:
            if not url:
                return "Source inconnue"
            
            # Remove protocol
            domain = url.replace("https://", "").replace("http://", "")
            
            # Extract domain part
            domain = domain.split("/")[0]
            
            # Remove www.
            if domain.startswith("www."):
                domain = domain[4:]
            
            return domain
        except:
            return "Source inconnue"
    
    def _normalize_french_interest(self, interest: str) -> str:
        """Normalize interest keywords to French"""
        # Simple mapping to ensure French terms
        french_mapping = {
            'politics': 'politique',
            'economy': 'économie', 
            'economics': 'économie',
            'sport': 'sport',
            'sports': 'sport',
            'tech': 'technologie',
            'technology': 'technologie',
            'crypto': 'cryptomonnaies',
            'health': 'santé',
            'cinema': 'cinéma',
            'music': 'musique',
            'football': 'football',
            'basketball': 'basketball',
            'nba': 'NBA'
        }
        
        interest_lower = interest.lower().strip()
        return french_mapping.get(interest_lower, interest_lower)

    def _create_error_response(self, error_msg: str) -> Dict:
        """Create standardized error response"""
        return {
            "success": False,
            "error": error_msg,
            "message": "",
            "sources": [],
            "processing_time": 0,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def health_check(self) -> Dict:
        """Check if Perplexica service is available"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/models")
                
                if response.is_success:
                    return {
                        "status": "healthy",
                        "perplexica_url": self.base_url,
                        "models_available": True
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "perplexica_url": self.base_url,
                        "error": f"HTTP {response.status_code}"
                    }
        except Exception as e:
            return {
                "status": "unhealthy",
                "perplexica_url": self.base_url,
                "error": str(e)
            }