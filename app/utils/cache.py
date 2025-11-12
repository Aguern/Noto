"""Redis cache utility"""
import os
import json
import redis.asyncio as redis
from typing import Optional, Any
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


class RedisCache:
    """Async Redis cache wrapper"""
    
    def __init__(self):
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self._connected = False
    
    async def connect(self):
        """Establish Redis connection"""
        try:
            await self.redis.ping()
            self._connected = True
            logger.info("Redis cache connected successfully")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            self._connected = False
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from cache"""
        if not self._connected:
            await self.connect()
        
        if not self._connected:
            return None
        
        try:
            return await self.redis.get(key)
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None
    
    async def set(self, key: str, value: str, ttl: int = 3600) -> bool:
        """Set value in cache with TTL"""
        if not self._connected:
            await self.connect()
        
        if not self._connected:
            return False
        
        try:
            await self.redis.setex(key, ttl, value)
            return True
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if not self._connected:
            await self.connect()
        
        if not self._connected:
            return False
        
        try:
            await self.redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        if not self._connected:
            await self.connect()
        
        if not self._connected:
            return False
        
        try:
            return await self.redis.exists(key) > 0
        except Exception as e:
            logger.error(f"Cache exists error for key {key}: {e}")
            return False
    
    async def health_check(self) -> dict:
        """Check Redis health"""
        try:
            if not self._connected:
                await self.connect()
            
            if self._connected:
                await self.redis.ping()
                return {"status": "healthy", "connected": True}
            else:
                return {"status": "unhealthy", "connected": False}
        except Exception as e:
            return {"status": "unhealthy", "connected": False, "error": str(e)}
    
    async def close(self):
        """Close Redis connection"""
        if self._connected:
            await self.redis.close()
            self._connected = False


# Global cache instance
cache = RedisCache()


class MemoryCache:
    """Simple in-memory cache with TTL for news briefing"""
    
    def __init__(self):
        self._cache = {}
        self._timestamps = {}
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from memory cache"""
        if key not in self._cache:
            return None
        
        # Check TTL
        if key in self._timestamps:
            from datetime import datetime, timedelta
            timestamp = self._timestamps[key]
            if datetime.utcnow() - timestamp > timedelta(seconds=3600):
                # Expired
                del self._cache[key]
                del self._timestamps[key]
                return None
        
        return self._cache.get(key)
    
    async def set(self, key: str, value: str, ttl: int = 3600) -> bool:
        """Set value in memory cache with TTL"""
        from datetime import datetime
        self._cache[key] = value
        self._timestamps[key] = datetime.utcnow()
        return True
    
    def clear(self):
        """Clear all cache"""
        self._cache.clear()
        self._timestamps.clear()