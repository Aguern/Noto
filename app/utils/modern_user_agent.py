"""Modern User Agent Manager for 2025 web scraping"""
import random
from typing import List, Dict
from datetime import datetime
from loguru import logger


class ModernUserAgentManager:
    """Manages modern user agents for web scraping in 2025"""
    
    def __init__(self):
        # User-agents 2025 les plus récents et populaires
        self.user_agents = {
            'chrome_mac': [
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Apple M1 Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            ],
            'chrome_windows': [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            ],
            'firefox_mac': [
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:119.0) Gecko/20100101 Firefox/119.0",
            ],
            'firefox_windows': [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:119.0) Gecko/20100101 Firefox/119.0",
            ],
            'safari_mac': [
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
            ],
            'edge_windows': [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0",
            ]
        }
        
        # Poids pour la sélection (Chrome = plus populaire)
        self.weights = {
            'chrome_mac': 0.35,
            'chrome_windows': 0.25, 
            'firefox_mac': 0.15,
            'firefox_windows': 0.10,
            'safari_mac': 0.10,
            'edge_windows': 0.05
        }
        
        # Cache pour éviter répétition immédiate
        self._recent_ua = []
        self._max_recent = 5
        
    def get_random_ua(self) -> str:
        """Get a random modern user agent"""
        # Sélection pondérée du type de navigateur
        browser_types = list(self.weights.keys())
        browser_weights = list(self.weights.values())
        
        selected_type = random.choices(browser_types, weights=browser_weights)[0]
        
        # Sélection d'un UA spécifique dans ce type
        available_uas = self.user_agents[selected_type]
        selected_ua = random.choice(available_uas)
        
        # Éviter répétition immédiate
        if selected_ua in self._recent_ua:
            # Réessayer avec un autre UA
            remaining_uas = [ua for ua_list in self.user_agents.values() for ua in ua_list 
                           if ua not in self._recent_ua]
            if remaining_uas:
                selected_ua = random.choice(remaining_uas)
        
        # Mise à jour du cache
        self._recent_ua.append(selected_ua)
        if len(self._recent_ua) > self._max_recent:
            self._recent_ua.pop(0)
            
        return selected_ua
    
    def get_chrome_ua(self) -> str:
        """Get a Chrome user agent specifically"""
        chrome_uas = self.user_agents['chrome_mac'] + self.user_agents['chrome_windows']
        return random.choice(chrome_uas)
    
    def get_firefox_ua(self) -> str:
        """Get a Firefox user agent specifically"""
        firefox_uas = self.user_agents['firefox_mac'] + self.user_agents['firefox_windows']
        return random.choice(firefox_uas)
    
    def get_safari_ua(self) -> str:
        """Get a Safari user agent specifically"""
        return random.choice(self.user_agents['safari_mac'])
    
    def get_headers_for_french_sites(self, user_agent: str = None) -> Dict[str, str]:
        """Get optimized headers for French news sites"""
        if not user_agent:
            user_agent = self.get_random_ua()
            
        return {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'sec-ch-ua': self._get_sec_ch_ua(user_agent),
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': self._get_platform(user_agent)
        }
    
    def _get_sec_ch_ua(self, user_agent: str) -> str:
        """Generate sec-ch-ua header based on user agent"""
        if 'Chrome/129' in user_agent:
            return '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"'
        elif 'Chrome/128' in user_agent:
            return '"Google Chrome";v="128", "Chromium";v="128", "Not;A=Brand";v="24"'
        elif 'Firefox' in user_agent:
            return '"Firefox";v="120"'
        elif 'Safari' in user_agent:
            return '"Safari";v="17"'
        elif 'Edg' in user_agent:
            return '"Microsoft Edge";v="129", "Not=A?Brand";v="8", "Chromium";v="129"'
        else:
            return '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"'
    
    def _get_platform(self, user_agent: str) -> str:
        """Get platform from user agent"""
        if 'Macintosh' in user_agent:
            return '"macOS"'
        elif 'Windows' in user_agent:
            return '"Windows"'
        else:
            return '"macOS"'
    
    def get_stats(self) -> Dict:
        """Get statistics about user agent usage"""
        return {
            'total_ua_available': sum(len(uas) for uas in self.user_agents.values()),
            'recent_used': len(self._recent_ua),
            'browser_types': len(self.user_agents),
            'last_ua_used': self._recent_ua[-1] if self._recent_ua else None
        }


# Global instance for easy import
ua_manager = ModernUserAgentManager()