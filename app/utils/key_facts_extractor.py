"""Key Facts Extractor - Prioritize important information over simple truncation"""
import re
import spacy
from typing import List, Dict, Optional, Set
from loguru import logger

# Load SpaCy multilingual NER model
try:
    nlp = spacy.load("xx_ent_wiki_sm")
    logger.info("Multilingual NER model loaded successfully")
except OSError:
    logger.warning("Multilingual NER model not found, falling back to patterns")
    nlp = None


class KeyFactsExtractor:
    """Intelligent content extraction using NER and importance scoring.

    This class implements a sophisticated content extraction strategy that prioritizes
    important information over simple truncation. It uses Named Entity Recognition (NER),
    factual pattern matching, and importance scoring to extract the most relevant
    sentences from long-form content.

    The extractor is designed for news articles and informational content, identifying:
        - Named entities (people, organizations, locations)
        - Factual indicators (percentages, monetary values, dates)
        - Importance keywords ("announces", "reveals", "record")
        - Temporal markers (recent information prioritized)

    Algorithm:
        1. Split content into sentences
        2. Score each sentence by importance (entities, facts, keywords)
        3. Rank sentences by score
        4. Select top sentences within character limit
        5. Reconstruct coherent text

    Attributes:
        factual_patterns (Dict[str, str]): Regex patterns for factual content
            (percentages, monetary values, dates, numbers, comparisons)
        importance_keywords (Dict[str, List[str]]): Keywords indicating importance
            by level (high, medium, context)
        entity_confidence_threshold (float): Minimum confidence for NER entities

    Example:
        >>> extractor = KeyFactsExtractor()
        >>> long_text = "... 1500 characters of news content ..."
        >>> key_facts = extractor.extract_key_facts(
        ...     content=long_text,
        ...     interest_category="technology",
        ...     max_chars=500
        ... )
        >>> print(len(key_facts))  # 500 characters of most important content

    Note:
        Requires SpaCy multilingual model (xx_ent_wiki_sm). Falls back to
        pattern-based extraction if model is unavailable.
    """

    def __init__(self):
        # Patterns for different types of key information
        self.factual_patterns = {
            'percentages': r'[+-]?\d+[,.]?\d*\s*%',
            'monetary': r'\d+[,.]?\d*\s*(milliards?|millions?|euros?|€|\$|dollars?)',
            'dates': r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{4}|\d{4}',
            'numbers': r'\d+[,.]?\d+(?:\s*(millions?|milliards?|milliers?))?',
            'comparisons': r'(?:après|contre|vs|par rapport à|comparé à)\s+[+-]?\d+[,.]?\d*\s*%',
        }
        
        # Keywords indicating important information (universal patterns)
        self.importance_keywords = {
            'high': [
                'inflation', 'croissance', 'hausse', 'baisse', 'chute', 'rebond',
                'record', 'historique', 'nouveau', 'première fois', 'jamais',
                'annonce', 'confirme', 'révèle', 'selon', 'données', 'chiffres',
                'résultats', 'bilan', 'performance', 'évolution', 'tendance',
                'breakthrough', 'announces', 'reveals', 'confirms', 'reports',
                'unprecedented', 'historic', 'first time', 'never before'
            ],
            'medium': [
                'estime', 'prévoit', 'attend', 'projette', 'anticipe',
                'analyse', 'étude', 'rapport', 'enquête', 'sondage',
                'estimates', 'expects', 'projects', 'forecasts', 'predicts',
                'analysis', 'study', 'report', 'survey', 'research'
            ],
            'context': [
                'contexte', 'situation', 'environnement', 'cadre',
                'background', 'historique', 'précédent',
                'context', 'situation', 'environment', 'framework'
            ]
        }
        
        # Entity confidence tracking
        self.entity_confidence_threshold = 0.7
    
    def extract_key_facts(
        self,
        content: str,
        interest_category: Optional[str] = None,
        max_chars: int = 1200
    ) -> str:
        """Extract key facts from content using intelligent importance scoring.

        This method analyzes content sentence-by-sentence, scoring each sentence
        based on multiple criteria (entities, factual patterns, keywords). It then
        selects the highest-scoring sentences that fit within the character limit,
        ensuring the most important information is preserved.

        Args:
            content: Full text content to extract key facts from (typically news articles)
            interest_category: Optional category for domain-specific scoring
                (e.g., "technology", "sports", "economy"). Boosts relevance for
                category-specific keywords.
            max_chars: Maximum character count for extracted content. Default 1200.

        Returns:
            str: Extracted key facts as coherent text, prioritizing high-importance
                sentences. Original content returned if already under max_chars.

        Algorithm Details:
            1. Sentence Segmentation: Split on sentence boundaries
            2. Scoring Criteria:
                - Base score for length (20-200 chars ideal)
                - Named entities (PERSON: +2.0, ORG: +1.5, GPE: +1.2 per entity)
                - Factual patterns (percentages: +2.0, monetary: +1.5 per match)
                - Importance keywords (high: +1.5, medium: +1.0, context: +0.5)
                - Category match (+1.0 per category keyword)
                - Temporal indicators (+0.5 for recent information)
                - Attribution (+1.0 for credible sources)
            3. Selection: Top-scoring sentences within max_chars limit
            4. Reconstruction: Maintain logical flow with proper punctuation

        Example:
            >>> extractor = KeyFactsExtractor()
            >>> article = '''
            ... Le gouvernement annonce une hausse de 12% des investissements.
            ... Cette décision fait suite à plusieurs mois de négociations.
            ... Les experts saluent cette initiative historique.
            ... '''
            >>> key_facts = extractor.extract_key_facts(article, "economy", 150)
            >>> print(key_facts)
            'Le gouvernement annonce une hausse de 12% des investissements. Les experts saluent cette initiative historique.'

        Note:
            - Very short sentences (< 10 chars) and noise sentences are filtered
            - Truncation with "..." if partial sentence fits at limit
            - Performance: O(n) where n is number of sentences
        """
        if not content or len(content) <= max_chars:
            return content
        
        logger.debug(f"Extracting key facts from {len(content)} chars for category: {interest_category}")
        
        # Split into sentences for analysis
        sentences = self._split_into_sentences(content)
        
        # Score and rank sentences by importance
        scored_sentences = []
        for sentence in sentences:
            score = self._calculate_sentence_importance(sentence, interest_category)
            if score > 0:
                scored_sentences.append({
                    'text': sentence.strip(),
                    'score': score,
                    'length': len(sentence)
                })
        
        # Sort by importance score (descending)
        scored_sentences.sort(key=lambda x: x['score'], reverse=True)
        
        # Select top sentences within character limit
        selected_sentences = []
        total_chars = 0
        
        for sentence_data in scored_sentences:
            sentence_text = sentence_data['text']
            sentence_length = sentence_data['length']
            
            # Check if adding this sentence would exceed limit
            if total_chars + sentence_length + 2 <= max_chars:  # +2 for ". "
                selected_sentences.append(sentence_text)
                total_chars += sentence_length + 2
            else:
                # Try to fit a shorter version
                available_chars = max_chars - total_chars - 3  # -3 for "..."
                if available_chars > 50:  # Minimum meaningful length
                    truncated = sentence_text[:available_chars] + "..."
                    selected_sentences.append(truncated)
                break
        
        # Reconstruct text maintaining logical flow
        result = self._reconstruct_text(selected_sentences)
        
        logger.debug(f"Key facts extraction: {len(content)} -> {len(result)} chars ({len(scored_sentences)} sentences analyzed)")
        
        return result
    
    def _split_into_sentences(self, content: str) -> List[str]:
        """Split content into sentences for analysis"""
        # Clean up content first
        content = re.sub(r'\s+', ' ', content.strip())
        
        # Split on sentence boundaries
        sentences = re.split(r'(?<=[.!?])\s+', content)
        
        # Filter out very short or meaningless sentences
        filtered_sentences = []
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 10 and not self._is_noise_sentence(sentence):
                filtered_sentences.append(sentence)
        
        return filtered_sentences
    
    def _is_noise_sentence(self, sentence: str) -> bool:
        """Check if sentence is likely noise/navigation"""
        noise_patterns = [
            r'^[A-Z][a-z]+\s*:',  # Category prefixes
            r'^\w+\s*\d+\s*:',    # Time prefixes
            r'^(Lire|Voir|Découvrir|Plus)',  # Navigation
            r'(newsletter|abonnement|publicité)',
            r'^\s*\d+[.]\s*$',    # Just numbers
            r'^(Source|Crédit|Photo)',
        ]
        
        for pattern in noise_patterns:
            if re.search(pattern, sentence, re.IGNORECASE):
                return True
        
        return False
    
    def _extract_entities(self, content: str) -> Dict[str, Set[str]]:
        """Extract named entities using SpaCy NER"""
        entities = {
            'PERSON': set(),
            'ORG': set(), 
            'GPE': set(),  # Geopolitical entities (countries, cities, states)
            'MONEY': set(),
            'DATE': set(),
            'PERCENT': set()
        }
        
        if not nlp:
            return entities
            
        try:
            doc = nlp(content[:5000])  # Limit to avoid memory issues
            for ent in doc.ents:
                if ent.label_ in entities:
                    # Filter out very short or likely incorrect entities
                    if len(ent.text.strip()) >= 2 and not ent.text.isdigit():
                        entities[ent.label_].add(ent.text.strip())
        except Exception as e:
            logger.warning(f"NER extraction failed: {e}")
            
        return entities

    def _calculate_sentence_importance(self, sentence: str, interest_category: str = None) -> float:
        """Calculate importance score for a sentence"""
        score = 0.0
        sentence_lower = sentence.lower()
        
        # Base score for sentence length (prefer substantial sentences)
        if 20 <= len(sentence) <= 200:
            score += 1.0
        elif len(sentence) > 200:
            score += 0.7  # Long sentences get lower score
        else:
            score += 0.3  # Very short sentences
        
        # Extract and score entities in this sentence
        entities = self._extract_entities(sentence)
        
        # Boost score for sentences containing important entities
        for entity_type, entity_set in entities.items():
            if entity_set:
                if entity_type == 'PERSON':
                    score += len(entity_set) * 2.0  # People are very important
                elif entity_type == 'ORG':
                    score += len(entity_set) * 1.5  # Organizations important
                elif entity_type == 'GPE':
                    score += len(entity_set) * 1.2  # Places moderately important
                else:
                    score += len(entity_set) * 0.8  # Other entities
        
        # Factual content indicators
        for pattern_type, pattern in self.factual_patterns.items():
            matches = len(re.findall(pattern, sentence, re.IGNORECASE))
            if matches > 0:
                if pattern_type == 'percentages':
                    score += matches * 2.0  # Percentages are very important
                elif pattern_type == 'monetary':
                    score += matches * 1.5
                else:
                    score += matches * 1.0
        
        # Importance keywords
        for importance_level, keywords in self.importance_keywords.items():
            for keyword in keywords:
                if keyword in sentence_lower:
                    if importance_level == 'high':
                        score += 1.5
                    elif importance_level == 'medium':
                        score += 1.0
                    else:
                        score += 0.5
        
        # Category-specific scoring
        if interest_category:
            category_keywords = self._get_category_keywords(interest_category)
            for keyword in category_keywords:
                if keyword in sentence_lower:
                    score += 1.0
        
        # Temporal indicators (recent information is important)
        temporal_indicators = ['aujourd\'hui', 'hier', 'cette semaine', 'ce mois', 'récent', 'dernier', 'nouveau']
        for indicator in temporal_indicators:
            if indicator in sentence_lower:
                score += 0.5
        
        # Attribution indicators (credible sources)
        attribution_indicators = ['selon', 'insee', 'ministère', 'gouvernement', 'banque de france', 'expert', 'analyse']
        for indicator in attribution_indicators:
            if indicator in sentence_lower:
                score += 1.0
        
        return score
    
    def _get_category_keywords(self, category: str) -> List[str]:
        """Get category-specific keywords for scoring - now supports any topic"""
        if not category:
            return ['actualité', 'news', 'information', 'annonce']
            
        category_lower = category.lower()
        
        # Extensive keywords map covering many topics
        keywords_map = {
            # Economics & Finance
            'économie': ['économie', 'économique', 'inflation', 'croissance', 'pib', 'emploi', 'chômage', 'prix', 'marché', 'finance', 'bourse', 'action', 'euro', 'dollar'],
            'finance': ['finance', 'financier', 'banque', 'crédit', 'investissement', 'bourse', 'action', 'obligation', 'rendement'],
            'economy': ['economy', 'economic', 'inflation', 'growth', 'gdp', 'employment', 'unemployment', 'market', 'finance'],
            
            # Sports
            'football': ['football', 'foot', 'match', 'équipe', 'joueur', 'club', 'ligue', 'champion', 'but', 'score', 'fifa', 'coupe'],
            'sport': ['sport', 'sportif', 'compétition', 'victoire', 'défaite', 'performance', 'record', 'champion', 'olympique'],
            'basketball': ['basketball', 'nba', 'basket', 'équipe', 'joueur', 'match', 'score', 'playoff'],
            
            # Politics
            'politique': ['politique', 'gouvernement', 'ministre', 'président', 'député', 'sénat', 'parlement', 'élection', 'vote', 'réforme'],
            'politics': ['politics', 'government', 'minister', 'president', 'parliament', 'election', 'vote', 'reform'],
            
            # Technology
            'technologie': ['tech', 'technologie', 'numérique', 'intelligence artificielle', 'ia', 'innovation', 'startup', 'application', 'logiciel'],
            'technology': ['tech', 'technology', 'digital', 'artificial intelligence', 'ai', 'innovation', 'startup', 'software', 'app'],
            'crypto': ['crypto', 'bitcoin', 'ethereum', 'blockchain', 'nft', 'defi', 'cryptomonnaie'],
            
            # Health
            'santé': ['santé', 'médical', 'hôpital', 'patient', 'traitement', 'maladie', 'vaccin', 'épidémie', 'médicament'],
            'health': ['health', 'medical', 'hospital', 'patient', 'treatment', 'disease', 'vaccine', 'epidemic'],
            
            # Entertainment
            'cinéma': ['cinéma', 'film', 'acteur', 'réalisateur', 'oscar', 'festival', 'sortie'],
            'cinema': ['cinema', 'movie', 'film', 'actor', 'director', 'oscar', 'festival'],
            'musique': ['musique', 'album', 'artiste', 'concert', 'chanson', 'streaming'],
            'music': ['music', 'album', 'artist', 'concert', 'song', 'streaming'],
            
            # Environment
            'environnement': ['environnement', 'écologie', 'climat', 'pollution', 'carbone', 'énergies renouvelables'],
            'environment': ['environment', 'ecology', 'climate', 'pollution', 'carbon', 'renewable energy'],
            
            # Science
            'science': ['science', 'recherche', 'étude', 'découverte', 'innovation', 'laboratoire'],
            'space': ['espace', 'nasa', 'spacex', 'astronaute', 'satellite', 'planète']
        }
        
        # Find keywords for the category (flexible matching)
        found_keywords = []
        for key, keywords in keywords_map.items():
            if key in category_lower or any(word in category_lower for word in key.split()):
                found_keywords.extend(keywords)
        
        # If specific category found, return those keywords
        if found_keywords:
            return found_keywords
        
        # Fallback: try to extract key terms from category name itself
        category_terms = [term.strip() for term in category.replace('_', ' ').replace('-', ' ').split() if len(term) > 2]
        if category_terms:
            return category_terms + ['actualité', 'news', 'information']
        
        return ['actualité', 'news', 'information', 'annonce']
    
    def _reconstruct_text(self, sentences: List[str]) -> str:
        """Reconstruct text from selected sentences maintaining flow"""
        if not sentences:
            return ""
        
        # Join sentences with proper punctuation
        result = ""
        for i, sentence in enumerate(sentences):
            if i == 0:
                result = sentence
            else:
                # Add connecting word if needed for better flow
                if not sentence.startswith(('Selon', 'Par ailleurs', 'En effet', 'Cependant')):
                    result += ". " + sentence
                else:
                    result += ". " + sentence
        
        # Ensure proper ending
        if not result.endswith(('.', '!', '?')):
            result += "."
        
        return result
    
    def analyze_content_distribution(self, content: str, interest_category: str = None) -> Dict:
        """Analyze content distribution for debugging"""
        sentences = self._split_into_sentences(content)
        entities = self._extract_entities(content)
        
        analysis = {
            'total_sentences': len(sentences),
            'total_chars': len(content),
            'avg_sentence_length': len(content) / len(sentences) if sentences else 0,
            'factual_sentences': 0,
            'high_importance_sentences': 0,
            'entities_found': {
                'people': list(entities.get('PERSON', set())),
                'organizations': list(entities.get('ORG', set())),
                'places': list(entities.get('GPE', set())),
                'money': list(entities.get('MONEY', set())),
                'dates': list(entities.get('DATE', set())),
                'percentages': list(entities.get('PERCENT', set()))
            },
            'categories_found': []
        }
        
        for sentence in sentences:
            score = self._calculate_sentence_importance(sentence, interest_category)
            if score >= 3.0:
                analysis['factual_sentences'] += 1
            if score >= 4.0:
                analysis['high_importance_sentences'] += 1
        
        return analysis


# Global instance
key_facts_extractor = KeyFactsExtractor()