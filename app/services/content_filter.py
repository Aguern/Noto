"""
Advanced Content Filtering using 2025 AI techniques
Semantic relevance, French news filtering, and intelligent quality scoring
"""
import re
import asyncio
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass
import numpy as np
from loguru import logger

try:
    from fastembed import TextEmbedding
except ImportError:
    TextEmbedding = None
    logger.warning("FastEmbed not installed. Run: pip install fastembed")


@dataclass
class ContentScore:
    """Content quality and relevance scoring"""
    relevance_score: float  # 0-1, semantic relevance to interests
    french_news_score: float  # 0-1, relevance to French news context
    quality_score: float  # 0-1, content quality (not filler)
    factual_score: float  # 0-1, likelihood of being factual
    final_score: float  # 0-1, weighted final score
    reasons: List[str]  # Reasons for scoring


class ContentFilter:
    """2025 State-of-the-art content filtering for French news"""
    
    def __init__(self):
        self.embedding_model = None
        self.interest_embeddings_cache = {}
        self.french_context_embedding = None
        self._initialize_model()
        
        # French news relevance patterns
        self.french_relevance_indicators = {
            'high': [
                'france', 'français', 'française', 'paris', 'marseille', 'lyon',
                'macron', 'gouvernement français', 'assemblée nationale',
                'ministre', 'sénat français', 'élysée', 'matignon'
            ],
            'medium': [
                'europe', 'européen', 'union européenne', 'euro', 'eurozone',
                'bruxelles', 'strasbourg'
            ],
            'context': [
                'international', 'mondial', 'global', 'planète'
            ]
        }
        
        # Filler content patterns (to penalize)
        self.filler_patterns = [
            r'voici les (actualités|nouvelles|informations)',
            r'ces (actualités|nouvelles|informations) sont',
            r'concernent directement la france',
            r'sont récentes et concernent',
            r'a annoncé (sa|son|ses) (saison|programme|plan)',
            r'qui (inclura|comprendra|comportera)',
            r'notamment (la|le|les)',
            r'a évoqué son temps à',
            r'les pensées de son',
        ]
        
        # Irrelevant sports content patterns
        self.irrelevant_sports_patterns = [
            r'défenseur français.*à (dundee|glasgow|birmingham)',
            r'joueur.*en (écosse|angleterre).*championnat',
            r'équipe.*division.*royaume-uni',
            r'transfert.*million.*livres sterling',
        ]

    def _initialize_model(self):
        """Initialize FastEmbed model for semantic analysis"""
        if TextEmbedding is None:
            logger.error("FastEmbed not available. Content filtering will use basic rules only.")
            return
            
        try:
            # Use lightweight, efficient model optimized for 2025
            self.embedding_model = TextEmbedding(
                model_name="BAAI/bge-small-en-v1.5"  # 384D, optimized for CPU
            )
            
            # Precompute French news context embedding
            french_context = "actualités françaises politique économie société sport culture france gouvernement"
            self.french_context_embedding = list(self.embedding_model.embed([french_context]))[0]
            
            logger.info("ContentFilter initialized with FastEmbed BAAI/bge-small-en-v1.5")
            
        except Exception as e:
            logger.error(f"Failed to initialize embedding model: {e}")
            self.embedding_model = None

    def _get_interest_embedding(self, interest: str) -> Optional[np.ndarray]:
        """Get cached embedding for interest, or compute if needed"""
        if self.embedding_model is None:
            return None
            
        if interest not in self.interest_embeddings_cache:
            try:
                # Expand interest context for better matching
                expanded_interest = f"{interest} actualités nouvelles france français"
                embedding = list(self.embedding_model.embed([expanded_interest]))[0]
                self.interest_embeddings_cache[interest] = embedding
            except Exception as e:
                logger.error(f"Failed to compute embedding for '{interest}': {e}")
                return None
                
        return self.interest_embeddings_cache[interest]

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two embeddings"""
        try:
            dot_product = np.dot(a, b)
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(b)
            return dot_product / (norm_a * norm_b)
        except Exception:
            return 0.0

    def _semantic_relevance_score(self, sentence: str, interest: str) -> float:
        """Calculate semantic relevance using embeddings"""
        if self.embedding_model is None:
            # Fallback to keyword matching
            return self._keyword_relevance_score(sentence, interest)
            
        try:
            # Get sentence embedding
            sentence_embedding = list(self.embedding_model.embed([sentence]))[0]
            
            # Get interest embedding
            interest_embedding = self._get_interest_embedding(interest)
            if interest_embedding is None:
                return self._keyword_relevance_score(sentence, interest)
            
            # Calculate similarity
            similarity = self._cosine_similarity(sentence_embedding, interest_embedding)
            
            # Convert to 0-1 score (cosine similarity is -1 to 1)
            return max(0.0, (similarity + 1) / 2)
            
        except Exception as e:
            logger.error(f"Semantic relevance calculation failed: {e}")
            return self._keyword_relevance_score(sentence, interest)

    def _keyword_relevance_score(self, sentence: str, interest: str) -> float:
        """Fallback keyword-based relevance scoring"""
        sentence_lower = sentence.lower()
        interest_lower = interest.lower()
        
        # Direct interest mention
        if interest_lower in sentence_lower:
            return 0.9
        
        # Related keywords based on interest
        related_keywords = {
            'politique': ['gouvernement', 'ministre', 'assemblée', 'parlement', 'élection'],
            'économie': ['croissance', 'inflation', 'marché', 'banque', 'euro'],
            'football': ['match', 'équipe', 'joueur', 'championnat', 'ligue'],
            'sport': ['compétition', 'championnat', 'équipe', 'match'],
        }
        
        for key, keywords in related_keywords.items():
            if key in interest_lower:
                matches = sum(1 for kw in keywords if kw in sentence_lower)
                return min(0.8, matches * 0.2)
        
        return 0.1

    def _french_news_relevance_score(self, sentence: str) -> float:
        """Score relevance to French news context"""
        sentence_lower = sentence.lower()
        score = 0.0
        
        # High relevance indicators
        high_matches = sum(1 for indicator in self.french_relevance_indicators['high'] 
                          if indicator in sentence_lower)
        score += high_matches * 0.3
        
        # Medium relevance indicators  
        medium_matches = sum(1 for indicator in self.french_relevance_indicators['medium']
                           if indicator in sentence_lower)
        score += medium_matches * 0.15
        
        # Context indicators
        context_matches = sum(1 for indicator in self.french_relevance_indicators['context']
                            if indicator in sentence_lower)
        score += context_matches * 0.1
        
        # Semantic similarity to French news context (if available)
        if self.embedding_model and self.french_context_embedding is not None:
            try:
                sentence_embedding = list(self.embedding_model.embed([sentence]))[0]
                similarity = self._cosine_similarity(sentence_embedding, self.french_context_embedding)
                score += max(0.0, (similarity + 1) / 2) * 0.2
            except Exception:
                pass
        
        return min(1.0, score)

    def _quality_score(self, sentence: str) -> Tuple[float, List[str]]:
        """Score content quality (detect filler/low-quality content)"""
        reasons = []
        score = 1.0  # Start with perfect score, deduct for issues
        
        # Check for filler patterns
        filler_matches = 0
        for pattern in self.filler_patterns:
            if re.search(pattern, sentence.lower()):
                filler_matches += 1
                reasons.append(f"Filler pattern: {pattern}")
        
        # Penalize filler content heavily
        score -= filler_matches * 0.3
        
        # Check for irrelevant sports content
        for pattern in self.irrelevant_sports_patterns:
            if re.search(pattern, sentence.lower()):
                score -= 0.8  # Heavy penalty
                reasons.append(f"Irrelevant sports: {pattern}")
        
        # Check sentence length and information density
        if len(sentence) < 30:
            score -= 0.2
            reasons.append("Too short")
        elif len(sentence) > 300:
            score -= 0.1
            reasons.append("Very long")
        
        # Check for enumeration lists (often not newsworthy)
        if re.search(r'(qui inclura|comprendra|comportera).*(,.*){3,}', sentence.lower()):
            score -= 0.4
            reasons.append("Enumeration list")
        
        # Check for meaningful verbs (indicates action/news)
        action_verbs = ['annonce', 'déclare', 'confirme', 'révèle', 'lance', 'présente']
        if any(verb in sentence.lower() for verb in action_verbs):
            score += 0.1
            reasons.append("Contains action verb")
        
        return max(0.0, score), reasons

    def _factual_likelihood_score(self, sentence: str) -> float:
        """Estimate likelihood of sentence being factual vs hallucination"""
        score = 0.5  # Neutral starting point
        
        # Positive indicators
        factual_indicators = [
            r'\d{1,2}\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)',  # Dates
            r'\d+\s*(millions?|milliards?)',  # Numbers with units
            r'selon\s+',  # According to
            r'ministre\s+des?\s+\w+',  # Specific ministry
            r'€|euros?',  # Money
            r'\d+%',  # Percentages
        ]
        
        for indicator in factual_indicators:
            if re.search(indicator, sentence.lower()):
                score += 0.15
        
        # Negative indicators (hallucination risk)
        hallucination_risks = [
            'ministre des finances, bruno le maire',  # Outdated info
            'premier ministre édouard philippe',  # Outdated info
            'président donald trump',  # Context confusion
        ]
        
        for risk in hallucination_risks:
            if risk in sentence.lower():
                score -= 0.8  # Heavy penalty for known hallucinations
        
        return min(1.0, max(0.0, score))

    def score_content(self, sentence: str, interest: str) -> ContentScore:
        """Main scoring function - combines all scoring methods"""
        
        # Calculate individual scores
        relevance_score = self._semantic_relevance_score(sentence, interest)
        french_news_score = self._french_news_relevance_score(sentence)
        quality_score, quality_reasons = self._quality_score(sentence)
        factual_score = self._factual_likelihood_score(sentence)
        
        # Weighted final score
        # Relevance is most important, followed by quality and factual accuracy
        weights = {
            'relevance': 0.4,
            'french_news': 0.25, 
            'quality': 0.25,
            'factual': 0.1
        }
        
        final_score = (
            relevance_score * weights['relevance'] +
            french_news_score * weights['french_news'] +
            quality_score * weights['quality'] +
            factual_score * weights['factual']
        )
        
        # Compile reasons
        reasons = quality_reasons.copy()
        if relevance_score < 0.3:
            reasons.append(f"Low relevance to {interest}")
        if french_news_score < 0.2:
            reasons.append("Low French news relevance")
        if factual_score < 0.3:
            reasons.append("Potential hallucination detected")
        
        return ContentScore(
            relevance_score=relevance_score,
            french_news_score=french_news_score,
            quality_score=quality_score,
            factual_score=factual_score,
            final_score=final_score,
            reasons=reasons
        )

    def filter_sentences(self, sentences: List[str], interest: str, threshold: float = 0.5) -> List[Tuple[str, ContentScore]]:
        """Filter sentences based on quality and relevance scores"""
        scored_sentences = []
        
        for sentence in sentences:
            if len(sentence.strip()) < 10:  # Skip very short sentences
                continue
                
            score = self.score_content(sentence, interest)
            
            if score.final_score >= threshold:
                scored_sentences.append((sentence, score))
        
        # Sort by score (highest first)
        scored_sentences.sort(key=lambda x: x[1].final_score, reverse=True)
        
        return scored_sentences

    def get_top_content(self, sentences: List[str], interest: str, max_items: int = 4, min_score: float = 0.5) -> List[str]:
        """Get top quality, relevant sentences for an interest"""
        filtered = self.filter_sentences(sentences, interest, min_score)
        top_sentences = [sentence for sentence, score in filtered[:max_items]]
        
        logger.info(f"Content filter: {len(sentences)} → {len(top_sentences)} sentences for '{interest}'")
        
        return top_sentences

    async def health_check(self) -> Dict:
        """Check if content filter is working properly"""
        try:
            test_sentence = "Le gouvernement français annonce de nouvelles mesures économiques."
            score = self.score_content(test_sentence, "politique")
            
            return {
                "status": "healthy",
                "embedding_model_available": self.embedding_model is not None,
                "test_score": score.final_score,
                "cached_interests": len(self.interest_embeddings_cache)
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "embedding_model_available": False
            }