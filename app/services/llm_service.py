"""LLM service using Groq API"""
import os
import json
from typing import Dict, List, Optional
from datetime import datetime
from groq import Groq
from loguru import logger
from dotenv import load_dotenv

from app.utils.key_facts_extractor import key_facts_extractor

load_dotenv()


class LLMService:
    """Service for LLM interactions using Groq"""
    
    def __init__(self):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = os.getenv("GROQ_MODEL", "llama3-8b-8192")
        self.max_rpm = int(os.getenv("GROQ_RATE_LIMIT_RPM", "30"))
        self.max_tpm = int(os.getenv("GROQ_RATE_LIMIT_TPM", "30000"))
        
        # Token counting (rough estimation)
        self._tokens_used = 0
        self._requests_count = 0
        
    async def generate_daily_summary(
        self,
        user_name: str,
        interests_data: Dict,  # {interest: search_results}
        time_of_day: str = "matin",  # matin, après-midi, soir
        language: str = "fr"
    ) -> Dict:
        """Generate unified daily summary for all user interests"""
        start_time = datetime.utcnow()
        
        try:
            # Prepare sources for all interests
            all_sources = ""
            interest_sections = []
            
            for interest, search_results in interests_data.items():
                if search_results.get("results"):
                    sources_text = self._format_sources_for_prompt(search_results)
                    all_sources += f"\n=== SOURCES {interest.upper()} ===\n{sources_text}\n"
                    interest_sections.append(interest)
            
            if not interest_sections:
                return {
                    "summary": f"Bonjour {user_name}, pas d'actualités significatives aujourd'hui. Bonne journée !",
                    "tokens_used": 0,
                    "processing_time": 0,
                    "interests_covered": []
                }
            
            # Generate greeting based on time
            greetings = {
                "matin": "Bonjour",
                "après-midi": "Bonjour", 
                "soir": "Bonsoir"
            }
            
            closings = {
                "matin": "Bonne journée",
                "après-midi": "Bon après-midi",
                "soir": "Bonne soirée"
            }
            
            greeting = greetings.get(time_of_day, "Bonjour")
            closing = closings.get(time_of_day, "Bonne journée")
            
            if language == "fr":
                prompt = f"""Génère un résumé audio quotidien des actualités pour {user_name}.

SOURCES DISPONIBLES :
{all_sources}

CENTRES D'INTÉRÊT À COUVRIR : {', '.join(interest_sections)}

FORMAT AUDIO-FRIENDLY OBLIGATOIRE :
{greeting} {user_name}, voici les actualités du 27 août.

Côté [CENTRE D'INTÉRÊT 1], [fait 1]. [Fait 2].

Pour [CENTRE D'INTÉRÊT 2], [fait 3]. [Fait 4].  

Enfin pour [CENTRE D'INTÉRÊT 3], [fait 5]. [Fait 6].

{closing} !

RÈGLES AUDIO :
- MAXIMUM 250 mots (pour audio fluide)
- 2 faits maximum par centre d'intérêt
- PAS de numérotation (1., 2., 3.)
- PAS de formatage markdown (**texte**)
- PAS de crochets [1], [2] - les sources perturbent l'audio
- Phrases fluides et naturelles pour la lecture
- Transitions douces : "Côté politique", "Pour l'économie", "Enfin pour le sport"

RÉSUMÉ AUDIO :"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=400,
                top_p=0.7
            )
            
            summary_text = response.choices[0].message.content.strip()
            
            # Clean text for audio (remove any remaining formatting)
            summary_text = self._clean_text_for_audio(summary_text)
            
            tokens_used = response.usage.total_tokens if hasattr(response, 'usage') else 0
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            
            logger.info(f"Daily summary generated - {tokens_used} tokens used")
            
            return {
                "summary": summary_text,
                "tokens_used": tokens_used,
                "processing_time": processing_time,
                "interests_covered": interest_sections,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Daily summary generation failed: {str(e)}")
            return {
                "summary": f"{greeting} {user_name}, impossible de récupérer les actualités pour le moment. {closing} !",
                "tokens_used": 0,
                "processing_time": (datetime.utcnow() - start_time).total_seconds(),
                "error": str(e),
                "interests_covered": []
            }

    async def summarize_for_whatsapp(
        self,
        search_results: Dict,
        query: str,
        style: str = "concise",
        max_length: int = 500,
        language: str = "fr",
        user_name: str = None,
        user_keywords: List[str] = None,
        noto_format: bool = False
    ) -> Dict:
        """
        Generate WhatsApp-optimized summary from search results
        
        Args:
            search_results: Search results from SearchService
            query: Original user query
            style: Summary style (concise, detailed, bullet_points)
            max_length: Maximum response length in words
            language: Response language
            
        Returns:
            Dict with summary text and metadata
        """
        start_time = datetime.utcnow()
        
        try:
            # Format sources for the prompt
            sources_text = self._format_sources_for_prompt(search_results)
            
            # Generate appropriate prompt based on style
            if noto_format:
                prompt = self._create_noto_prompt(
                    query, sources_text, user_name, user_keywords, language
                )
            else:
                prompt = self._create_summary_prompt(
                    query, sources_text, style, max_length, language
                )
            
            logger.info(f"Generating summary for query: {query}")
            
            # Call Groq API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,   # Très faible créativité
                max_tokens=200,    # Limite pour ~150 mots max
                top_p=0.3          # Très déterministe
            )
            
            # Extract response
            summary_text = response.choices[0].message.content.strip()
            
            # Track usage
            tokens_used = response.usage.total_tokens if hasattr(response, 'usage') else 0
            self._tokens_used += tokens_used
            self._requests_count += 1
            
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            
            logger.info(f"Summary generated successfully - {tokens_used} tokens used")
            
            result = {
                "summary": summary_text,
                "tokens_used": tokens_used,
                "processing_time": processing_time,
                "model": self.model,
                "style": style,
                "language": language,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Add sources separately for Noto format
            if noto_format:
                result["sources"] = self._extract_sources_list(search_results)
            
            return result
            
        except Exception as e:
            logger.error(f"LLM summarization error: {str(e)}")
            return {
                "summary": self._generate_fallback_summary(search_results, query),
                "tokens_used": 0,
                "processing_time": (datetime.utcnow() - start_time).total_seconds(),
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def _format_sources_for_prompt(self, search_results: Dict) -> str:
        """Format search results for LLM prompt, organized by interest category"""
        sources_text = ""
        
        # Group results by interest category if available
        results_by_interest = {}
        ungrouped_results = []
        
        for result in search_results.get("results", []):
            interest = result.get('interest_category')
            if interest:
                if interest not in results_by_interest:
                    results_by_interest[interest] = []
                results_by_interest[interest].append(result)
            else:
                ungrouped_results.append(result)
        
        source_counter = 1
        
        # Format by interest category
        for interest, results in results_by_interest.items():
            sources_text += f"\n=== ACTUALITÉS {interest.upper()} ===\n"
            
            for result in results[:3]:  # Max 3 per category
                sources_text += f"[{source_counter}] {result.get('title', 'Titre non disponible')}\n"
                
                # Use full content if available, otherwise use snippet
                content = result.get('full_content') or result.get('snippet', '')
                if content:
                    # Use intelligent key facts extraction instead of simple truncation
                    interest_category = result.get('interest_category', interest)
                    key_facts = key_facts_extractor.extract_key_facts(
                        content, 
                        interest_category=interest_category, 
                        max_chars=1000  # Increased from 600 to 1000 for more context
                    )
                    sources_text += f"Contenu: {key_facts}\n"
                
                if result.get('published_date'):
                    sources_text += f"Date: {result['published_date']}\n"
                
                sources_text += "\n"
                source_counter += 1
        
        # Add ungrouped results if any
        if ungrouped_results:
            sources_text += "\n=== AUTRES ACTUALITÉS ===\n"
            for result in ungrouped_results:
                sources_text += f"[{source_counter}] {result.get('title', 'Titre non disponible')}\n"
                
                content = result.get('full_content') or result.get('snippet', '')
                if content:
                    # Use key facts extraction instead of simple truncation
                    interest_category = result.get('interest_category', 'général')
                    extracted_facts = key_facts_extractor.extract_key_facts(
                        content, 
                        interest_category=interest_category, 
                        max_chars=1200  # Allow more space for key facts
                    )
                    sources_text += f"Contenu: {extracted_facts}\n"
                
                sources_text += "\n"
                source_counter += 1
        
        return sources_text.strip()
    
    def _create_summary_prompt(
        self,
        query: str,
        sources_text: str,
        style: str,
        max_length: int,
        language: str
    ) -> str:
        """Create appropriate prompt based on style and language"""
        
        language_instructions = {
            "fr": {
                "concise": "Réponds de manière concise et directe",
                "detailed": "Fournis une analyse détaillée et approfondie",
                "bullet_points": "Structure ta réponse avec des points clés"
            },
            "en": {
                "concise": "Respond concisely and directly",
                "detailed": "Provide detailed and thorough analysis", 
                "bullet_points": "Structure your response with key bullet points"
            }
        }
        
        lang_config = language_instructions.get(language, language_instructions["fr"])
        style_instruction = lang_config.get(style, lang_config["concise"])
        
        if language == "fr":
            # Limite élargie pour permettre 2-3 sujets par centre d'intérêt
            actual_max_words = min(max_length, 180)
            prompt = f"""Analyse les sources et rédige UN SEUL résumé cohérent sur : {query}

SOURCES :
{sources_text}

DÉCISION UNIQUE - CHOISIS UN SEUL CHEMIN :

CHEMIN A - Si 2+ faits significatifs trouvés :
Rédige comme cet exemple → François Bayrou sollicite un vote de confiance le 8 septembre [1], [2]. L'inflation française recule à 2,1% en décembre [3]. Le gouvernement annonce 50 milliards d'économies budgétaires [1].

CHEMIN B - Si sources pauvres/non-significatives :  
Écris uniquement → "Aucune actualité significative sur {query} aujourd'hui."

RÈGLES ABSOLUES :
- CHOISIS UN SEUL CHEMIN - pas les deux !
- Maximum {actual_max_words} mots
- Citations [1], [2], [3] avec virgules
- INTERDIT : "Voici", listes à puces, contradiction

RÉSUMÉ UNIQUE :"""
        else:
            prompt = f"""You are an intelligent assistant that responds like Perplexity.ai on WhatsApp.

User question: {query}

Information sources:
{sources_text}

Instructions:
1. {style_instruction}
2. Use maximum {max_length} words
3. Cite sources with [1], [2], etc.
4. Use some relevant emojis but not excessively
5. Simple format for WhatsApp (no markdown)
6. Be precise, factual and up-to-date
7. Adapt tone according to question context

Response:"""
        
        return prompt
    
    def _create_noto_prompt(
        self,
        query: str,
        sources_text: str,
        user_name: str,
        user_keywords: List[str],
        language: str
    ) -> str:
        """Create Noto-specific personalized prompt"""
        from datetime import datetime
        
        # Get current date in French format
        current_date = datetime.now().strftime("%-d %B %Y")
        
        # Format keywords for better organization
        keywords_text = ", ".join(user_keywords) if user_keywords else "actualités"
        
        if language == "fr":
            prompt = f"""GÉNÈRE UN RÉSUMÉ AUDIO D'ACTUALITÉS à partir des sources ci-dessous.

SOURCES D'ACTUALITÉS :
{sources_text}

FORMAT EXACT À RESPECTER :
Bonjour {user_name or 'cher utilisateur'}, voici les actualités du {current_date}. [Résumé des faits extraits des sources]. Bonne journée.

RÈGLES ABSOLUES :
- Commence par "Bonjour {user_name or 'cher utilisateur'}, voici les actualités du {current_date}."
- Résume UNIQUEMENT les FAITS concrets trouvés dans les sources
- N'ajoute AUCUNE note, explication, ou commentaire personnel
- Finis par "Bonne journée."
- Maximum 150 mots
- Aucun formatage [1][2][3] ou "Note :"
- Si plusieurs centres d'intérêt : sépare par des phrases fluides

RÉSUMÉ :"""
        else:
            prompt = f"""You are Noto, a personalized news assistant.

TASK: Generate personalized daily news summary.

SOURCES:
{sources_text}

REQUIRED FORMAT:
"Good morning {user_name or 'dear user'}, here are today's news from {current_date}: [Interest 1], [news 1], [news 2], [news 3]; [Interest 2], [news 4], [news 5], [news 6]"

RULES:
1. Start with greeting and date
2. Organize by interests: {keywords_text}
3. Max 3 news per interest
4. Separate interests with ";"
5. NO [1][2][3] references
6. Conversational for voice synthesis
7. Under 200 words

PERSONALIZED SUMMARY:"""
        
        return prompt
    
    def _extract_sources_list(self, search_results: Dict) -> List[Dict]:
        """Extract formatted sources list for separate message"""
        sources = []
        results = search_results.get("results", [])
        
        for i, result in enumerate(results[:5], 1):  # Top 5 sources
            source = {
                "number": i,
                "title": result.get("title", "Titre non disponible"),
                "url": result.get("url", ""),
                "domain": result.get("url", "").split("//")[-1].split("/")[0] if result.get("url") else "Source inconnue"
            }
            sources.append(source)
        
        return sources
    
    def format_sources_message(self, sources: List[Dict]) -> str:
        """Format sources into WhatsApp message"""
        if not sources:
            return ""
        
        message = "*Sources :*\n\n"
        for source in sources:
            message += f"[{source['number']}] {source['title']}\n{source['domain']}\n\n"
        
        return message.strip()
    
    def _calculate_max_tokens(self, max_words: int) -> int:
        """Estimate max tokens from max words (rough approximation)"""
        # Rough estimate: 1 token ≈ 0.75 words
        return int(max_words / 0.75) + 200  # Add buffer for prompt
    
    def _generate_fallback_summary(self, search_results: Dict, query: str) -> str:
        """Generate a simple fallback summary when LLM fails"""
        results = search_results.get("results", [])
        
        if not results:
            return f"❌ Désolé, je n'ai pas pu trouver d'informations récentes sur '{query}'. Essayez de reformuler votre question."
        
        # Create simple summary from top results
        summary = f"📊 Voici ce que j'ai trouvé sur '{query}':\n\n"
        
        for i, result in enumerate(results[:3], 1):
            title = result.get('title', 'Titre non disponible')
            snippet = result.get('snippet', '')[:150] + "..."
            summary += f"[{i}] {title}\n{snippet}\n\n"
        
        summary += f"Sources: {len(results)} résultats trouvés"
        
        return summary
    
    async def analyze_intent(self, message: str) -> Dict:
        """Analyze user message to determine intent and extract parameters"""
        try:
            prompt = f"""Analyse ce message WhatsApp et détermine l'intention de l'utilisateur :

Message: "{message}"

Réponds uniquement avec ce JSON (pas d'autre texte) :
{{
  "intent": "search|command|greeting|help|other",
  "confidence": 0.0-1.0,
  "parameters": {{
    "query": "requête de recherche extraite",
    "language": "fr|en",
    "urgency": "low|medium|high",
    "topic_category": "tech|news|sports|health|finance|other"
  }}
}}"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200
            )
            
            # Parse JSON response
            result_text = response.choices[0].message.content.strip()
            return json.loads(result_text)
            
        except Exception as e:
            logger.error(f"Intent analysis error: {e}")
            # Fallback intent classification
            return {
                "intent": "search",
                "confidence": 0.7,
                "parameters": {
                    "query": message,
                    "language": "fr",
                    "urgency": "medium",
                    "topic_category": "other"
                }
            }
    
    def _clean_text_for_audio(self, text: str) -> str:
        """Clean text for audio synthesis by removing formatting"""
        import re
        
        # Remove markdown formatting
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)  # **bold** -> bold
        text = re.sub(r'\*(.*?)\*', r'\1', text)      # *italic* -> italic
        
        # Remove numbered lists
        text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
        
        # Remove source citations [1], [2], etc.
        text = re.sub(r'\[\d+\]', '', text)
        
        # Remove bullet points
        text = re.sub(r'^\s*[•\-\*]\s+', '', text, flags=re.MULTILINE)
        
        # Clean up extra whitespace and line breaks
        text = re.sub(r'\n\s*\n', '. ', text)  # Double line breaks -> ". "
        text = re.sub(r'\s+', ' ', text)       # Multiple spaces -> single space
        
        # Ensure proper sentence flow
        text = text.replace('. .', '.').replace('..', '.')
        
        return text.strip()

    def get_usage_stats(self) -> Dict:
        """Get current usage statistics"""
        return {
            "total_requests": self._requests_count,
            "total_tokens": self._tokens_used,
            "average_tokens_per_request": (
                self._tokens_used / self._requests_count if self._requests_count > 0 else 0
            ),
            "model": self.model,
            "rate_limits": {
                "rpm": self.max_rpm,
                "tpm": self.max_tpm
            }
        }
    
    async def health_check(self) -> Dict:
        """Check Groq API health"""
        try:
            # Simple test request
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=10
            )
            
            return {
                "status": "healthy",
                "model": self.model,
                "api_available": True
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "model": self.model,
                "api_available": False,
                "error": str(e)
            }
    
    async def brief_from_items(
        self,
        items: list,
        first_name: str,
        max_words: int = 250,
        audio_words: int = 140,
        lang: str = "fr"
    ) -> Dict:
        """Generate brief from news items using LLM
        
        This method bridges to the NewsSummarizer for consistency,
        but could also use Groq directly if needed.
        """
        from app.services.news.summarizer_gpt5 import NewsSummarizer
        
        summarizer = NewsSummarizer()
        return await summarizer.brief_from_items(
            items=items,
            first_name=first_name,
            max_words=max_words,
            audio_words=audio_words,
            lang=lang
        )