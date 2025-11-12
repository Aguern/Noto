"""Advanced Content Extractor with multiple fallback methods"""
import asyncio
import re
import hashlib
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from loguru import logger
from abc import ABC, abstractmethod

from .modern_user_agent import ua_manager


class BaseExtractor(ABC):
    """Base class for content extractors"""
    
    @abstractmethod
    async def extract(self, url: str, title: str = "") -> Optional[Dict[str, Any]]:
        """Extract content from URL"""
        pass
    
    def _clean_french_text(self, text: str) -> str:
        """Clean and optimize text for French content"""
        if not text:
            return ""
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove common noise patterns
        noise_patterns = [
            r'Accepter et fermer',
            r'Accepter les cookies',
            r'Politique de confidentialité',
            r'Mentions légales',
            r'S\'abonner à la newsletter',
            r'Suivez-nous sur',
            r'Partager sur.*?(?=\s)',
            r'©.*?\d{4}',
            r'Tous droits réservés',
            r'La question du jour',
            r'Top news',
            r'Vos émissions en replay',
            r'UTMB \d{4}',
            r'Eurobasket \d{4}',
            r'note salée',
            r'Taxe d\'entrée(?!.*?Paris)',  # Remove unless part of Paris context
            r'^\w+\s*:\s*',  # Remove category prefixes like "Sport: " 
            r'REPLAY\..*?(?=\s)',
            r'Lire la suite.*?(?=\s)',
            r'- \w+.*?:.*?(?=\s)',  # Remove navigation elements
        ]
        
        for pattern in noise_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # Remove standalone fragments (less than 4 words before first period)
        sentences = text.split('.')
        if sentences and len(sentences[0].split()) < 4:
            sentences = sentences[1:]  # Remove first fragment
            text = '. '.join(sentences)
        
        # Remove very short ending fragments
        if text and text.split()[-1:] and len(text.split()[-1]) < 3:
            words = text.split()
            text = ' '.join(words[:-1])
        
        # Clean up extra spaces and punctuation
        text = ' '.join(text.split())
        text = re.sub(r'\.{2,}', '.', text)  # Multiple periods to single
        text = re.sub(r'\s*\.\s*', '. ', text)  # Clean period spacing
        
        return text.strip()
    
    def _calculate_quality_score(self, content: str, url: str, title: str) -> float:
        """Calculate content quality score"""
        if not content:
            return 0.0
            
        score = 0.0
        content_lower = content.lower()
        
        # Length score (optimal: 500-3000 chars)
        length = len(content)
        if 500 <= length <= 3000:
            score += 0.3
        elif 300 <= length < 500:
            score += 0.2
        elif length > 3000:
            score += 0.1
        
        # French content indicators
        french_words = ['le', 'la', 'les', 'de', 'du', 'des', 'et', 'est', 'dans', 'pour', 'avec', 'sur']
        french_count = sum(1 for word in french_words if f' {word} ' in content_lower)
        french_ratio = french_count / len(french_words)
        score += french_ratio * 0.2
        
        # News article indicators
        news_indicators = ['selon', 'a déclaré', 'a annoncé', 'rapporte', 'affirme', 'précise']
        news_count = sum(1 for indicator in news_indicators if indicator in content_lower)
        if news_count > 0:
            score += min(news_count * 0.05, 0.2)
        
        # Error/block indicators (negative score)
        error_indicators = ['403', '404', 'access denied', 'blocked', 'error', 'forbidden', 'not found']
        if any(error in content_lower for error in error_indicators):
            score -= 0.5
        
        # Title relevance
        if title and len(title) > 5:
            title_words = set(title.lower().split())
            content_words = set(content_lower.split())
            relevance = len(title_words.intersection(content_words)) / len(title_words)
            score += relevance * 0.1
        
        return max(0.0, min(score, 1.0))


class TrafilaturaExtractor(BaseExtractor):
    """Trafilatura-based extractor with French optimization"""
    
    def __init__(self):
        self.name = "trafilatura"
        try:
            import trafilatura
            from trafilatura.settings import use_config
            self.trafilatura = trafilatura
            
            # Configuration optimisée pour sites français
            self.config = use_config()
            self.config.set('DEFAULT', 'EXTRACTION_TIMEOUT', '15')
            self.config.set('DEFAULT', 'MIN_EXTRACT_SIZE', '200')
            self.config.set('DEFAULT', 'MIN_OUTPUT_SIZE', '100')
            self.config.set('DEFAULT', 'MIN_OUTPUT_COMM_SIZE', '50')
            self.available = True
            logger.info("Trafilatura extractor initialized")
        except ImportError:
            logger.warning("Trafilatura not available")
            self.available = False
    
    async def extract(self, url: str, title: str = "") -> Optional[Dict[str, Any]]:
        """Extract content using Trafilatura"""
        if not self.available:
            return None
            
        try:
            start_time = datetime.utcnow()
            
            # Headers optimisés pour sites français
            headers = ua_manager.get_headers_for_french_sites()
            
            # Téléchargement avec configuration optimisée (sans headers pour éviter l'erreur)
            downloaded = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.trafilatura.fetch_url(url, config=self.config)
            )
            
            if not downloaded:
                return None
            
            # Extraction avec paramètres optimisés français
            text = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.trafilatura.extract(
                    downloaded,
                    config=self.config,
                    include_comments=False,
                    include_tables=False,
                    target_language='fr',
                    favor_precision=True,
                    favor_recall=False
                )
            )
            
            if not text or len(text) < 200:
                return None
            
            # Nettoyage et validation
            cleaned_text = self._clean_french_text(text)
            quality_score = self._calculate_quality_score(cleaned_text, url, title)
            
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            
            return {
                'content': cleaned_text,
                'method': self.name,
                'quality_score': quality_score,
                'length': len(cleaned_text),
                'processing_time': processing_time
            }
            
        except Exception as e:
            logger.warning(f"Trafilatura extraction failed for {url}: {e}")
            return None


class Newspaper3kExtractor(BaseExtractor):
    """Newspaper3k-based extractor"""
    
    def __init__(self):
        self.name = "newspaper3k"
        try:
            from newspaper import Article, Config
            self.Article = Article
            
            # Configuration pour sites français
            self.config = Config()
            self.config.browser_user_agent = ua_manager.get_chrome_ua()
            self.config.request_timeout = 12
            self.config.number_threads = 1
            self.config.language = 'fr'
            self.config.keep_article_html = True
            self.config.fetch_images = False
            self.available = True
            logger.info("Newspaper3k extractor initialized")
        except ImportError:
            logger.warning("Newspaper3k not available")
            self.available = False
    
    async def extract(self, url: str, title: str = "") -> Optional[Dict[str, Any]]:
        """Extract content using Newspaper3k"""
        if not self.available:
            return None
            
        try:
            start_time = datetime.utcnow()
            
            # Mise à jour du user-agent
            self.config.browser_user_agent = ua_manager.get_random_ua()
            
            article = self.Article(url, config=self.config)
            
            # Téléchargement
            await asyncio.get_event_loop().run_in_executor(
                None, article.download
            )
            
            if not article.html:
                return None
            
            # Parsing
            await asyncio.get_event_loop().run_in_executor(
                None, article.parse
            )
            
            if not article.text or len(article.text) < 200:
                return None
            
            # Nettoyage et validation
            cleaned_text = self._clean_french_text(article.text)
            quality_score = self._calculate_quality_score(cleaned_text, url, title)
            
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            
            return {
                'content': cleaned_text,
                'method': self.name,
                'quality_score': quality_score,
                'length': len(cleaned_text),
                'processing_time': processing_time
            }
            
        except Exception as e:
            logger.warning(f"Newspaper3k extraction failed for {url}: {e}")
            return None


class ReadabilityExtractor(BaseExtractor):
    """ReadabiliPy-based extractor"""
    
    def __init__(self):
        self.name = "readability"
        try:
            from readabilipy import simple_json_from_html_string
            import httpx
            self.simple_json = simple_json_from_html_string
            self.httpx = httpx
            self.available = True
            logger.info("Readability extractor initialized")
        except ImportError:
            logger.warning("ReadabiliPy not available")
            self.available = False
    
    async def extract(self, url: str, title: str = "") -> Optional[Dict[str, Any]]:
        """Extract content using ReadabiliPy"""
        if not self.available:
            return None
            
        try:
            start_time = datetime.utcnow()
            
            # Téléchargement avec headers optimisés
            headers = ua_manager.get_headers_for_french_sites()
            
            async with self.httpx.AsyncClient(timeout=12.0, headers=headers, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                html_content = response.text
            
            # Extraction en mode Python pur (plus rapide)
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.simple_json(html_content, use_readability=False)
            )
            
            if not result or not result.get('content'):
                return None
            
            text = result['content']
            if len(text) < 200:
                return None
            
            # Nettoyage et validation
            cleaned_text = self._clean_french_text(text)
            quality_score = self._calculate_quality_score(cleaned_text, url, title)
            
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            
            return {
                'content': cleaned_text,
                'method': self.name,
                'quality_score': quality_score,
                'length': len(cleaned_text),
                'processing_time': processing_time
            }
            
        except Exception as e:
            logger.warning(f"Readability extraction failed for {url}: {e}")
            return None


class BeautifulSoupExtractor(BaseExtractor):
    """BeautifulSoup fallback extractor"""
    
    def __init__(self):
        self.name = "beautifulsoup"
        try:
            from bs4 import BeautifulSoup
            import httpx
            self.BeautifulSoup = BeautifulSoup
            self.httpx = httpx
            self.available = True
            logger.info("BeautifulSoup extractor initialized")
        except ImportError:
            logger.warning("BeautifulSoup not available")
            self.available = False
    
    async def extract(self, url: str, title: str = "") -> Optional[Dict[str, Any]]:
        """Extract content using BeautifulSoup"""
        if not self.available:
            return None
            
        try:
            start_time = datetime.utcnow()
            
            headers = ua_manager.get_headers_for_french_sites()
            
            async with self.httpx.AsyncClient(timeout=10.0, headers=headers, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                html_content = response.text
            
            soup = self.BeautifulSoup(html_content, 'html.parser')
            
            # Supprimer éléments non désirés
            for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe']):
                element.decompose()
            
            # Sélecteurs optimisés pour sites français
            content_selectors = [
                'article .content',
                'article .article-content', 
                '.post-content',
                '.entry-content',
                'article',
                'main .content',
                '.article-body',
                '.story-body',
                'main'
            ]
            
            content = ""
            for selector in content_selectors:
                element = soup.select_one(selector)
                if element:
                    content = element.get_text(strip=True, separator=' ')
                    break
            
            if not content:
                # Fallback vers le body
                body = soup.find('body')
                if body:
                    content = body.get_text(strip=True, separator=' ')
            
            if not content or len(content) < 200:
                return None
            
            # Nettoyage et validation
            cleaned_text = self._clean_french_text(content)
            quality_score = self._calculate_quality_score(cleaned_text, url, title)
            
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            
            return {
                'content': cleaned_text,
                'method': self.name,
                'quality_score': quality_score,
                'length': len(cleaned_text),
                'processing_time': processing_time
            }
            
        except Exception as e:
            logger.warning(f"BeautifulSoup extraction failed for {url}: {e}")
            return None


class AdvancedContentExtractor:
    """Advanced content extractor with multiple fallback methods"""
    
    def __init__(self):
        # Extracteurs classés par efficacité (ordre de priorité)
        self.extractors = [
            TrafilaturaExtractor(),
            Newspaper3kExtractor(),
            ReadabilityExtractor(),
            BeautifulSoupExtractor()
        ]
        
        # Filtre les extracteurs disponibles
        self.available_extractors = [ext for ext in self.extractors if ext.available]
        
        logger.info(f"AdvancedContentExtractor initialized with {len(self.available_extractors)} extractors")
        
        # Cache pour éviter re-extraction
        self._extraction_cache = {}
        self._max_cache_size = 100
    
    async def extract_with_fallback(self, url: str, title: str = "", preferred_method: str = None) -> Optional[Dict[str, Any]]:
        """Extract content with intelligent fallback"""
        
        # Check cache
        cache_key = hashlib.md5(url.encode()).hexdigest()
        if cache_key in self._extraction_cache:
            logger.debug(f"Cache hit for {url}")
            return self._extraction_cache[cache_key]
        
        # Ordre des extracteurs
        extractors_to_try = self.available_extractors.copy()
        
        # Prioriser la méthode préférée si spécifiée
        if preferred_method:
            preferred_extractor = next((ext for ext in extractors_to_try if ext.name == preferred_method), None)
            if preferred_extractor:
                extractors_to_try.remove(preferred_extractor)
                extractors_to_try.insert(0, preferred_extractor)
        
        best_result = None
        best_score = 0.0
        
        # Essayer chaque extracteur
        for extractor in extractors_to_try:
            try:
                logger.debug(f"Trying {extractor.name} for {url}")
                result = await extractor.extract(url, title)
                
                if result and result.get('quality_score', 0) > 0.3:  # Seuil minimal de qualité
                    # Si score élevé, prendre immédiatement
                    if result['quality_score'] > 0.8:
                        logger.info(f"High quality extraction with {extractor.name}: {result['quality_score']:.2f}")
                        self._cache_result(cache_key, result)
                        return result
                    
                    # Sinon, garder le meilleur résultat
                    if result['quality_score'] > best_score:
                        best_result = result
                        best_score = result['quality_score']
                        logger.debug(f"New best result from {extractor.name}: {best_score:.2f}")
                
            except Exception as e:
                logger.warning(f"Extractor {extractor.name} failed for {url}: {e}")
                continue
        
        # Retourner le meilleur résultat trouvé
        if best_result:
            logger.info(f"Best extraction result: {best_result['method']} with score {best_score:.2f}")
            self._cache_result(cache_key, best_result)
            return best_result
        
        logger.warning(f"All extractors failed for {url}")
        return None
    
    def _cache_result(self, cache_key: str, result: Dict[str, Any]) -> None:
        """Cache extraction result"""
        if len(self._extraction_cache) >= self._max_cache_size:
            # Supprimer les plus anciens
            oldest_key = next(iter(self._extraction_cache))
            del self._extraction_cache[oldest_key]
        
        self._extraction_cache[cache_key] = result
    
    def get_stats(self) -> Dict[str, Any]:
        """Get extractor statistics"""
        return {
            'available_extractors': len(self.available_extractors),
            'extractor_names': [ext.name for ext in self.available_extractors],
            'cache_size': len(self._extraction_cache),
            'max_cache_size': self._max_cache_size
        }


# Global instance for easy import
advanced_extractor = AdvancedContentExtractor()