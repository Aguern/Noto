"""Smart Source Manager for French news sites with extraction optimization"""
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse
from loguru import logger
from datetime import datetime, timedelta


class SmartSourceManager:
    """Manages French news sources with extraction success tracking"""
    
    def __init__(self):
        # Sources françaises testées et validées (avec performance réelle)
        self.trusted_french_sources = {
            # Tier 1: Excellente extraction (>5000 chars)
            'lci.fr': {
                'priority': 10, 
                'extractor': 'trafilatura', 
                'avg_chars': 8800, 
                'success_rate': 0.95,
                'category': 'news',
                'language': 'fr'
            },
            'lepoint.fr': {
                'priority': 10, 
                'extractor': 'trafilatura', 
                'avg_chars': 8200, 
                'success_rate': 0.90,
                'category': 'news',
                'language': 'fr'
            },
            
            # Tier 2: Très bonne extraction (3000-5000 chars)
            'challenges.fr': {
                'priority': 9, 
                'extractor': 'newspaper3k', 
                'avg_chars': 4000, 
                'success_rate': 0.85,
                'category': 'business',
                'language': 'fr'
            },
            'france24.com': {
                'priority': 9, 
                'extractor': 'trafilatura', 
                'avg_chars': 3500, 
                'success_rate': 0.88,
                'category': 'international',
                'language': 'fr'
            },
            'rfi.fr': {
                'priority': 9, 
                'extractor': 'trafilatura', 
                'avg_chars': 3500, 
                'success_rate': 0.87,
                'category': 'international',
                'language': 'fr'
            },
            'slate.fr': {
                'priority': 9, 
                'extractor': 'trafilatura', 
                'avg_chars': 3600, 
                'success_rate': 0.82,
                'category': 'analysis',
                'language': 'fr'
            },
            'franceinter.fr': {
                'priority': 9, 
                'extractor': 'trafilatura', 
                'avg_chars': 3000, 
                'success_rate': 0.80,
                'category': 'news',
                'language': 'fr'
            },
            
            # Tier 3: Bonne extraction (1500-3000 chars)  
            'rtl.fr': {
                'priority': 8, 
                'extractor': 'trafilatura', 
                'avg_chars': 2900, 
                'success_rate': 0.78,
                'category': 'news',
                'language': 'fr'
            },
            'huffingtonpost.fr': {
                'priority': 8, 
                'extractor': 'trafilatura', 
                'avg_chars': 2500, 
                'success_rate': 0.75,
                'category': 'opinion',
                'language': 'fr'
            },
            'ladepeche.fr': {
                'priority': 8, 
                'extractor': 'trafilatura', 
                'avg_chars': 1800, 
                'success_rate': 0.72,
                'category': 'regional',
                'language': 'fr'
            },
            'lexpress.fr': {
                'priority': 8, 
                'extractor': 'trafilatura', 
                'avg_chars': 1800, 
                'success_rate': 0.70,
                'category': 'news',
                'language': 'fr'
            },
            'europe1.fr': {
                'priority': 8, 
                'extractor': 'trafilatura', 
                'avg_chars': 1700, 
                'success_rate': 0.75,
                'category': 'news',
                'language': 'fr'
            },
            'sudouest.fr': {
                'priority': 7, 
                'extractor': 'trafilatura', 
                'avg_chars': 4800, 
                'success_rate': 0.68,
                'category': 'regional',
                'language': 'fr'
            },
            
            # Tier 4: Extraction correcte (1000-1500 chars)
            '20minutes.fr': {
                'priority': 7, 
                'extractor': 'trafilatura', 
                'avg_chars': 1400, 
                'success_rate': 0.85,
                'category': 'popular',
                'language': 'fr'
            },
            'cnews.fr': {
                'priority': 6, 
                'extractor': 'trafilatura', 
                'avg_chars': 1200, 
                'success_rate': 0.65,
                'category': 'news',
                'language': 'fr'
            },
            'marianne.net': {
                'priority': 7, 
                'extractor': 'trafilatura', 
                'avg_chars': 2000, 
                'success_rate': 0.70,
                'category': 'opinion',
                'language': 'fr'
            },
            
            # Sources internationales fiables
            'euronews.com': {
                'priority': 8, 
                'extractor': 'trafilatura', 
                'avg_chars': 2500, 
                'success_rate': 0.80,
                'category': 'international',
                'language': 'multilingual'
            },
            'apnews.com': {
                'priority': 7, 
                'extractor': 'newspaper3k', 
                'avg_chars': 2000, 
                'success_rate': 0.75,
                'category': 'international',
                'language': 'en'
            },
            'bbc.com': {
                'priority': 6, 
                'extractor': 'readability', 
                'avg_chars': 1800, 
                'success_rate': 0.60,
                'category': 'international',
                'language': 'en'
            },
            'theguardian.com': {
                'priority': 6, 
                'extractor': 'newspaper3k', 
                'avg_chars': 2200, 
                'success_rate': 0.55,
                'category': 'international',
                'language': 'en'
            }
        }
        
        # Sites bloqués confirmés (à éviter complètement)
        self.blocked_sites = {
            'lemonde.fr': 'Paywall + anti-bot Cloudflare',
            'lefigaro.fr': 'Paywall + protection anti-scraping',
            'reuters.com': 'Anti-bot sophistiqué',
            'bfmtv.com': 'Extraction vide systématique', 
            'franceinfo.fr': 'Protection anti-bot',
            'francetvinfo.fr': 'Extraction vide',
            'ouest-france.fr': 'Téléchargement échoué récurrent',
            'leparisien.fr': 'Paywall + restrictions',
            'lavoixdunord.fr': 'Téléchargement échoué',
            'aljazeera.com': 'Retiré sur demande'
        }
        
        # Domaines suspects (extraction souvent échouée)
        self.suspicious_domains = {
            'nouvelobs.com': 'Lent (4.6s) et contenu court',
            'liberation.fr': 'Protection anti-bot variable',
            'latribune.fr': 'Paywall partiel'
        }
        
        # Statistiques d'utilisation
        self.usage_stats = {
            'extractions_attempted': 0,
            'extractions_successful': 0,
            'blocked_sites_avoided': 0,
            'source_performance': {}
        }
        
        # Cache de vérification des domaines
        self._domain_cache = {}
        
        logger.info(f"SmartSourceManager initialized with {len(self.trusted_french_sources)} trusted sources")
    
    def extract_domain(self, url: str) -> str:
        """Extract clean domain from URL"""
        if url in self._domain_cache:
            return self._domain_cache[url]
        
        try:
            if not url or not url.startswith(('http://', 'https://')):
                domain = 'unknown'
            else:
                parsed = urlparse(url)
                domain = parsed.netloc.lower()
                
                # Remove www. prefix
                if domain.startswith('www.'):
                    domain = domain[4:]
                    
                # Remove port if present
                if ':' in domain:
                    domain = domain.split(':')[0]
            
            self._domain_cache[url] = domain
            return domain
            
        except Exception as e:
            logger.warning(f"Failed to parse domain from {url}: {e}")
            return 'unknown'
    
    def should_skip_source(self, url: str) -> bool:
        """Check if source should be skipped due to blocking"""
        domain = self.extract_domain(url)
        
        if domain in self.blocked_sites:
            self.usage_stats['blocked_sites_avoided'] += 1
            logger.debug(f"Skipping blocked source: {domain} - {self.blocked_sites[domain]}")
            return True
        
        return False
    
    def get_source_priority(self, url: str) -> int:
        """Get source priority (higher = better)"""
        domain = self.extract_domain(url)
        source_config = self.trusted_french_sources.get(domain)
        
        if source_config:
            return source_config['priority']
        elif domain in self.suspicious_domains:
            return 3  # Priorité faible
        else:
            return 5  # Priorité moyenne pour sources inconnues
    
    def get_optimal_extractor(self, url: str) -> str:
        """Get optimal extractor for this source"""
        domain = self.extract_domain(url)
        source_config = self.trusted_french_sources.get(domain)
        
        if source_config:
            return source_config['extractor']
        else:
            return 'trafilatura'  # Default extractor
    
    def get_expected_quality(self, url: str) -> Dict[str, float]:
        """Get expected quality metrics for source"""
        domain = self.extract_domain(url)
        source_config = self.trusted_french_sources.get(domain)
        
        if source_config:
            return {
                'expected_chars': source_config['avg_chars'],
                'success_rate': source_config['success_rate'],
                'priority': source_config['priority'] / 10.0,  # Normalize to 0-1
                'category': source_config['category']
            }
        else:
            return {
                'expected_chars': 1000,
                'success_rate': 0.5,
                'priority': 0.5,
                'category': 'unknown'
            }
    
    def rank_sources(self, results: List[Dict]) -> List[Dict]:
        """Rank sources by quality and extraction potential"""
        
        def calculate_source_score(result):
            url = result.get('url', '')
            domain = self.extract_domain(url)
            
            # Base priority from trusted sources
            base_score = self.get_source_priority(url)
            
            # Bonus for French sources
            if domain in self.trusted_french_sources:
                source_config = self.trusted_french_sources[domain]
                french_bonus = 2 if source_config['language'] == 'fr' else 0
                quality_bonus = source_config['success_rate'] * 2
                base_score += french_bonus + quality_bonus
            
            # Penalty for suspicious domains
            if domain in self.suspicious_domains:
                base_score -= 2
            
            # Bonus for content length in snippet
            snippet = result.get('snippet', '') or result.get('content', '')
            if len(snippet) > 200:
                base_score += 1
            
            # Recency bonus
            pub_date = result.get('published_date') or result.get('publishedDate')
            if pub_date:
                # Simple recency check
                if any(indicator in str(pub_date).lower() for indicator in ['today', 'il y a', 'hours ago']):
                    base_score += 1
            
            return base_score
        
        # Trier par score décroissant
        ranked_results = sorted(results, key=calculate_source_score, reverse=True)
        
        logger.debug(f"Ranked {len(ranked_results)} sources")
        return ranked_results
    
    def update_extraction_stats(self, url: str, success: bool, chars_extracted: int = 0):
        """Update extraction statistics"""
        self.usage_stats['extractions_attempted'] += 1
        
        if success:
            self.usage_stats['extractions_successful'] += 1
        
        domain = self.extract_domain(url)
        if domain not in self.usage_stats['source_performance']:
            self.usage_stats['source_performance'][domain] = {
                'attempts': 0,
                'successes': 0,
                'total_chars': 0,
                'avg_chars': 0
            }
        
        stats = self.usage_stats['source_performance'][domain]
        stats['attempts'] += 1
        
        if success:
            stats['successes'] += 1
            stats['total_chars'] += chars_extracted
            stats['avg_chars'] = stats['total_chars'] / stats['successes']
    
    def get_french_sources_by_category(self, category: str = None) -> List[str]:
        """Get French sources filtered by category"""
        if not category:
            return [domain for domain, config in self.trusted_french_sources.items() 
                   if config['language'] == 'fr']
        
        return [domain for domain, config in self.trusted_french_sources.items()
                if config['language'] == 'fr' and config['category'] == category]
    
    def get_performance_report(self) -> Dict:
        """Get comprehensive performance report"""
        total_attempts = self.usage_stats['extractions_attempted']
        total_successes = self.usage_stats['extractions_successful']
        
        success_rate = (total_successes / total_attempts) if total_attempts > 0 else 0
        
        # Top performing sources
        top_sources = []
        for domain, stats in self.usage_stats['source_performance'].items():
            if stats['attempts'] > 0:
                domain_success_rate = stats['successes'] / stats['attempts']
                top_sources.append({
                    'domain': domain,
                    'success_rate': domain_success_rate,
                    'avg_chars': stats['avg_chars'],
                    'attempts': stats['attempts']
                })
        
        top_sources.sort(key=lambda x: x['success_rate'], reverse=True)
        
        return {
            'overall_stats': {
                'total_attempts': total_attempts,
                'total_successes': total_successes,
                'success_rate': success_rate,
                'blocked_sites_avoided': self.usage_stats['blocked_sites_avoided']
            },
            'trusted_sources_count': len(self.trusted_french_sources),
            'blocked_sources_count': len(self.blocked_sites),
            'french_sources_count': len(self.get_french_sources_by_category()),
            'top_performing_sources': top_sources[:10],
            'categories_available': list(set(config['category'] for config in self.trusted_french_sources.values()))
        }
    
    def is_french_source(self, url: str) -> bool:
        """Check if source is French"""
        domain = self.extract_domain(url)
        source_config = self.trusted_french_sources.get(domain)
        return source_config and source_config['language'] == 'fr'
    
    def get_source_info(self, url: str) -> Dict:
        """Get comprehensive source information"""
        domain = self.extract_domain(url)
        
        if domain in self.trusted_french_sources:
            config = self.trusted_french_sources[domain].copy()
            config['status'] = 'trusted'
            config['domain'] = domain
            return config
        elif domain in self.blocked_sites:
            return {
                'domain': domain,
                'status': 'blocked',
                'reason': self.blocked_sites[domain],
                'priority': 0
            }
        elif domain in self.suspicious_domains:
            return {
                'domain': domain, 
                'status': 'suspicious',
                'reason': self.suspicious_domains[domain],
                'priority': 3
            }
        else:
            return {
                'domain': domain,
                'status': 'unknown',
                'priority': 5,
                'extractor': 'trafilatura'
            }


# Global instance for easy import
smart_source_manager = SmartSourceManager()