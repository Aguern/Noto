#!/usr/bin/env python3
"""Analyze what full content is actually extracted vs what's sent to LLM"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.search_service import SearchService
from loguru import logger

async def analyze_full_content():
    """Analyze what full content is actually extracted"""
    logger.info("🔍 ANALYZING FULL EXTRACTED CONTENT")
    
    # Initialize service
    search_service = SearchService()
    
    # Test with economy query
    query = "actualités économie France inflation 2025"
    
    search_results = await search_service.search(
        query=query,
        max_results=2,  # Just 2 for detailed analysis
        categories="general",
        language="fr"
    )
    
    results = search_results.get('results', [])
    
    for i, result in enumerate(results, 1):
        if result.get('content_extracted', False):
            logger.info(f"\n{'='*100}")
            logger.info(f"📄 FULL CONTENT ANALYSIS - RESULT {i}")
            logger.info(f"{'='*100}")
            logger.info(f"Domain: {result.get('source_domain', 'unknown')}")
            logger.info(f"Method: {result.get('extraction_method', 'none')}")
            logger.info(f"Quality Score: {result.get('content_quality_score', 0):.3f}")
            logger.info(f"Content Length: {result.get('content_length', 0)} chars")
            
            full_content = result.get('full_content', '')
            
            if full_content:
                logger.info(f"\n📄 FULL EXTRACTED CONTENT:")
                logger.info(f"-" * 80)
                logger.info(f"{full_content}")
                logger.info(f"-" * 80)
                
                # Show what gets truncated to 600 chars for LLM
                truncated = full_content[:600] + "..." if len(full_content) > 600 else full_content
                logger.info(f"\n✂️  WHAT GETS SENT TO LLM (600 chars max):")
                logger.info(f"-" * 80)
                logger.info(f"{truncated}")
                logger.info(f"-" * 80)
                
                # Analyze information loss
                if len(full_content) > 600:
                    lost_content = full_content[600:]
                    logger.info(f"\n🗑️  LOST CONTENT ({len(lost_content)} chars):")
                    logger.info(f"-" * 80)
                    logger.info(f"{lost_content}")
                    logger.info(f"-" * 80)
                
                # Find key information in full content
                key_info = []
                sentences = full_content.split('.')
                for sentence in sentences:
                    sentence = sentence.strip()
                    # Look for factual information
                    if any(indicator in sentence.lower() for indicator in [
                        '%', 'milliards', 'euros', 'millions', 'selon', 'annonce', 
                        'hausse', 'baisse', 'croissance', 'chiffres', 'données'
                    ]):
                        key_info.append(sentence)
                
                if key_info:
                    logger.info(f"\n💡 KEY FACTUAL INFO FOUND IN FULL CONTENT:")
                    for j, info in enumerate(key_info[:5], 1):  # Top 5
                        logger.info(f"  {j}. {info}")
                
                # Check if key info is lost in truncation
                truncated_lower = truncated.lower()
                lost_key_info = []
                for info in key_info:
                    if info.lower() not in truncated_lower:
                        lost_key_info.append(info)
                
                if lost_key_info:
                    logger.warning(f"\n⚠️  KEY INFO LOST IN TRUNCATION:")
                    for info in lost_key_info:
                        logger.warning(f"    ❌ {info}")
            
            logger.info(f"\n{'='*100}\n")
    
    return results

async def main():
    """Run content analysis"""
    logger.info("🧪 Starting Full Content Analysis\n")
    
    results = await analyze_full_content()
    
    logger.info("🎯 ANALYSIS CONCLUSIONS:")
    logger.info("=" * 80)
    logger.info("1. Check if key factual information is lost in 600-char truncation")
    logger.info("2. Identify patterns in what content gets cut off")  
    logger.info("3. Determine optimal strategy to preserve important facts")
    logger.info("4. Consider content prioritization vs simple truncation")

if __name__ == "__main__":
    asyncio.run(main())