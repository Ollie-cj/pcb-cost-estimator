"""
SQLite-based caching layer for LLM responses.

Prevents redundant API calls by caching responses keyed by MPN and prompt type.
"""

import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CacheEntry(BaseModel):
    """Cache entry metadata."""

    key: str
    prompt_type: str
    mpn: str
    response_data: Dict[str, Any]
    created_at: float
    tokens_used: int


class LLMCache:
    """SQLite-based cache for LLM responses."""

    def __init__(self, cache_file: Optional[Path] = None, ttl_seconds: int = 86400 * 30):
        """
        Initialize the LLM cache.

        Args:
            cache_file: Path to SQLite database file. Defaults to ~/.pcb_cost_estimator/llm_cache.db
            ttl_seconds: Time-to-live for cache entries in seconds (default: 30 days)
        """
        if cache_file is None:
            cache_dir = Path.home() / ".pcb_cost_estimator"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = cache_dir / "llm_cache.db"

        self.cache_file = Path(cache_file)
        self.ttl_seconds = ttl_seconds
        self._init_database()

    def _init_database(self) -> None:
        """Initialize the SQLite database schema."""
        try:
            with sqlite3.connect(self.cache_file) as conn:
                cursor = conn.cursor()

                # Create cache table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS llm_cache (
                        cache_key TEXT PRIMARY KEY,
                        prompt_type TEXT NOT NULL,
                        mpn TEXT NOT NULL,
                        response_data TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        tokens_used INTEGER NOT NULL,
                        last_accessed_at REAL NOT NULL
                    )
                """)

                # Create indexes for efficient lookups
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_mpn
                    ON llm_cache(mpn)
                """)

                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_prompt_type
                    ON llm_cache(prompt_type)
                """)

                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_created_at
                    ON llm_cache(created_at)
                """)

                conn.commit()

                logger.debug(f"Initialized LLM cache database: {self.cache_file}")

        except Exception as e:
            logger.error(f"Failed to initialize cache database: {e}")

    def _generate_cache_key(
        self,
        prompt_type: str,
        mpn: str,
        additional_context: Optional[str] = None
    ) -> str:
        """
        Generate a unique cache key.

        Args:
            prompt_type: Type of prompt (classification, price_check, obsolescence)
            mpn: Manufacturer part number
            additional_context: Optional additional context to include in key

        Returns:
            SHA256 hash as cache key
        """
        key_components = [prompt_type, mpn.upper().strip()]
        if additional_context:
            key_components.append(additional_context)

        key_string = "|".join(key_components)
        return hashlib.sha256(key_string.encode()).hexdigest()

    def get(
        self,
        prompt_type: str,
        mpn: str,
        additional_context: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a cached response.

        Args:
            prompt_type: Type of prompt
            mpn: Manufacturer part number
            additional_context: Optional additional context

        Returns:
            Cached response data if found and not expired, None otherwise
        """
        cache_key = self._generate_cache_key(prompt_type, mpn, additional_context)

        try:
            with sqlite3.connect(self.cache_file) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT response_data, created_at
                    FROM llm_cache
                    WHERE cache_key = ?
                """, (cache_key,))

                row = cursor.fetchone()

                if row is None:
                    logger.debug(f"Cache miss for {prompt_type}:{mpn}")
                    return None

                response_data_json, created_at = row

                # Check if entry is expired
                age_seconds = time.time() - created_at
                if age_seconds > self.ttl_seconds:
                    logger.debug(
                        f"Cache entry expired for {prompt_type}:{mpn} "
                        f"(age: {age_seconds:.0f}s, ttl: {self.ttl_seconds}s)"
                    )
                    # Delete expired entry
                    cursor.execute("DELETE FROM llm_cache WHERE cache_key = ?", (cache_key,))
                    conn.commit()
                    return None

                # Update last accessed time
                cursor.execute("""
                    UPDATE llm_cache
                    SET last_accessed_at = ?
                    WHERE cache_key = ?
                """, (time.time(), cache_key))
                conn.commit()

                response_data = json.loads(response_data_json)
                logger.debug(f"Cache hit for {prompt_type}:{mpn}")
                return response_data

        except Exception as e:
            logger.error(f"Failed to retrieve from cache: {e}")
            return None

    def set(
        self,
        prompt_type: str,
        mpn: str,
        response_data: Dict[str, Any],
        tokens_used: int = 0,
        additional_context: Optional[str] = None
    ) -> bool:
        """
        Store a response in the cache.

        Args:
            prompt_type: Type of prompt
            mpn: Manufacturer part number
            response_data: Response data to cache
            tokens_used: Number of tokens used for this request
            additional_context: Optional additional context

        Returns:
            True if successful, False otherwise
        """
        cache_key = self._generate_cache_key(prompt_type, mpn, additional_context)

        try:
            with sqlite3.connect(self.cache_file) as conn:
                cursor = conn.cursor()

                now = time.time()
                response_data_json = json.dumps(response_data)

                cursor.execute("""
                    INSERT OR REPLACE INTO llm_cache
                    (cache_key, prompt_type, mpn, response_data, created_at, tokens_used, last_accessed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    cache_key,
                    prompt_type,
                    mpn.upper().strip(),
                    response_data_json,
                    now,
                    tokens_used,
                    now
                ))

                conn.commit()

                logger.debug(f"Cached response for {prompt_type}:{mpn}")
                return True

        except Exception as e:
            logger.error(f"Failed to store in cache: {e}")
            return False

    def clear(self, prompt_type: Optional[str] = None, mpn: Optional[str] = None) -> int:
        """
        Clear cache entries.

        Args:
            prompt_type: If specified, only clear entries of this type
            mpn: If specified, only clear entries for this MPN

        Returns:
            Number of entries deleted
        """
        try:
            with sqlite3.connect(self.cache_file) as conn:
                cursor = conn.cursor()

                if prompt_type and mpn:
                    cursor.execute("""
                        DELETE FROM llm_cache
                        WHERE prompt_type = ? AND mpn = ?
                    """, (prompt_type, mpn.upper().strip()))
                elif prompt_type:
                    cursor.execute("""
                        DELETE FROM llm_cache
                        WHERE prompt_type = ?
                    """, (prompt_type,))
                elif mpn:
                    cursor.execute("""
                        DELETE FROM llm_cache
                        WHERE mpn = ?
                    """, (mpn.upper().strip(),))
                else:
                    cursor.execute("DELETE FROM llm_cache")

                deleted_count = cursor.rowcount
                conn.commit()

                logger.info(f"Cleared {deleted_count} cache entries")
                return deleted_count

        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return 0

    def cleanup_expired(self) -> int:
        """
        Remove expired cache entries.

        Returns:
            Number of entries deleted
        """
        try:
            with sqlite3.connect(self.cache_file) as conn:
                cursor = conn.cursor()

                cutoff_time = time.time() - self.ttl_seconds

                cursor.execute("""
                    DELETE FROM llm_cache
                    WHERE created_at < ?
                """, (cutoff_time,))

                deleted_count = cursor.rowcount
                conn.commit()

                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} expired cache entries")

                return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup expired entries: {e}")
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        try:
            with sqlite3.connect(self.cache_file) as conn:
                cursor = conn.cursor()

                # Total entries
                cursor.execute("SELECT COUNT(*) FROM llm_cache")
                total_entries = cursor.fetchone()[0]

                # Entries by prompt type
                cursor.execute("""
                    SELECT prompt_type, COUNT(*), SUM(tokens_used)
                    FROM llm_cache
                    GROUP BY prompt_type
                """)
                by_type = {
                    row[0]: {"count": row[1], "tokens_used": row[2]}
                    for row in cursor.fetchall()
                }

                # Total tokens saved
                cursor.execute("SELECT SUM(tokens_used) FROM llm_cache")
                total_tokens = cursor.fetchone()[0] or 0

                # Oldest and newest entries
                cursor.execute("SELECT MIN(created_at), MAX(created_at) FROM llm_cache")
                min_time, max_time = cursor.fetchone()

                return {
                    "total_entries": total_entries,
                    "by_prompt_type": by_type,
                    "total_tokens_saved": total_tokens,
                    "oldest_entry_age_seconds": time.time() - min_time if min_time else None,
                    "newest_entry_age_seconds": time.time() - max_time if max_time else None,
                    "cache_file": str(self.cache_file),
                    "ttl_seconds": self.ttl_seconds
                }

        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {"error": str(e)}


# Global cache instance
_cache: Optional[LLMCache] = None


def get_llm_cache(cache_file: Optional[Path] = None) -> LLMCache:
    """
    Get or create the global LLM cache instance.

    Args:
        cache_file: Optional custom cache file path

    Returns:
        LLMCache instance
    """
    global _cache

    if _cache is None or cache_file is not None:
        _cache = LLMCache(cache_file)

    return _cache
