#!/usr/bin/env python3
"""Test script for OpenAI and Perplexity APIs"""
import os
import asyncio
import json
from dotenv import load_dotenv
import httpx
import openai

load_dotenv()

async def test_perplexity_api():
    """Test Perplexity Sonar API"""
    print("🔍 Testing Perplexity API...")
    
    api_key = os.getenv("PPLX_API_KEY")
    if not api_key:
        print("❌ PPLX_API_KEY not found")
        return False
    
    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "sonar",
        "messages": [
            {"role": "user", "content": "What are the latest news in Formula 1?"}
        ],
        "temperature": 0.1,
        "max_tokens": 500
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.is_success:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                print(f"✅ Perplexity API works! Response length: {len(content)} chars")
                return True
            else:
                print(f"❌ Perplexity API error: {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
    except Exception as e:
        print(f"❌ Perplexity API exception: {e}")
        return False

async def test_openai_api():
    """Test OpenAI API"""
    print("\n🤖 Testing OpenAI API...")
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not found")
        return False
    
    try:
        client = openai.AsyncOpenAI(api_key=api_key)
        
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": "Test message - respond with JSON: {\"status\": \"ok\", \"message\": \"API working\"}"}
            ],
            temperature=0.1,
            max_tokens=100,
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        parsed = json.loads(content)
        
        if parsed.get("status") == "ok":
            print("✅ OpenAI API works!")
            return True
        else:
            print("❌ OpenAI API unexpected response")
            return False
            
    except Exception as e:
        print(f"❌ OpenAI API exception: {e}")
        return False

async def main():
    print("🚀 Testing News Briefing APIs\n")
    
    pplx_ok = await test_perplexity_api()
    openai_ok = await test_openai_api()
    
    print(f"\n📊 Results:")
    print(f"Perplexity API: {'✅ OK' if pplx_ok else '❌ FAILED'}")
    print(f"OpenAI API: {'✅ OK' if openai_ok else '❌ FAILED'}")
    
    if pplx_ok and openai_ok:
        print("\n🎉 All APIs are working! Ready for news briefing pipeline.")
        return True
    else:
        print("\n⚠️  Some APIs are not working. Check your configuration.")
        return False

if __name__ == "__main__":
    asyncio.run(main())