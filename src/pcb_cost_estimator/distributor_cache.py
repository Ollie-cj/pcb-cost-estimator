"""SQLite-based caching layer for distributor API results.

Stores DistributorResult objects keyed by (distributor, MPN) with a
configurable TTL (default 24 hours).
"""

import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class DistributorCache:
    """SQLite cache for distributor pricing / stock results.

    Schema is intentionally separate from the LLM cache so that the two
    can have different TTLs and clear independently.
    """

    DEFAULT_TTL_SECONDS = 86400  # 24 hours

    def __init__(
        self,
        cache_file: Optional[Path] = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        """Initialise the distributor cache.

        Args:
            cache_file: Path to SQLite database file.  Defaults to
                ``~/.pcb_cost_estimator/distributor_cache.db``.
            ttl_seconds: Cache TTL in seconds (default 24 h).
        """
        if cache_file is None:
            cache_dir = Path.home() / ".pcb_cost_estimator"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = cache_dir / "distributor_cache.db"

        self.cache_file = Path(cache_file)
        self.ttl_seconds = ttl_seconds
        self._init_database()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_database(self) -> None:
        """Create tables and indexes if they do not exist."""
        try:
            with sqlite3.connect(self.cache_file) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS distributor_cache (
                        cache_key     TEXT PRIMARY KEY,
                        distributor   TEXT NOT NULL,
                        mpn           TEXT NOT NULL,
                        result_data   TEXT NOT NULL,
                        created_at    REAL NOT NULL,
                        last_accessed REAL NOT NULL
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dist_mpn
                    ON distributor_cache(distributor, mpn)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dist_created
                    ON distributor_cache(created_at)
                """)
                conn.commit()
                logger.debug("Initialised distributor cache: %s", self.cache_file)
        except Exception as exc:
            logger.error("Failed to initialise distributor cache: %s", exc)

    # ------------------------------------------------------------------
    # Key generation
    # ------------------------------------------------------------------

    @staticmethod
    def _make_key(distributor: str, mpn: str) -> str:
        """Return a stable SHA-256 cache key."""
        raw = f"{distributor.upper()}|{mpn.upper().strip()}"
        return hashlib.sha256(raw.encode()).hexdigest()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, distributor: str, mpn: str) -> Optional[Any]:
        """Retrieve a cached DistributorResult.

        Args:
            distributor: Distributor name (e.g. ``'Farnell'``).
            mpn: Manufacturer part number.

        Returns:
            Deserialised DistributorResult or ``None`` if missing / expired.
        """
        from .distributor_client import DistributorResult  # avoid circular at module level

        key = self._make_key(distributor, mpn)
        try:
            with sqlite3.connect(self.cache_file) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT result_data, created_at FROM distributor_cache WHERE cache_key = ?",
                    (key,),
                )
                row = cursor.fetchone()
                if row is None:
                    logger.debug("Cache miss: %s / %s", distributor, mpn)
                    return None

                result_data_json, created_at = row

                if time.time() - created_at > self.ttl_seconds:
                    logger.debug("Cache expired: %s / %s", distributor, mpn)
                    cursor.execute(
                        "DELETE FROM distributor_cache WHERE cache_key = ?", (key,)
                    )
                    conn.commit()
                    return None

                # Update last-accessed timestamp
                cursor.execute(
                    "UPDATE distributor_cache SET last_accessed = ? WHERE cache_key = ?",
                    (time.time(), key),
                )
                conn.commit()

                data = json.loads(result_data_json)
                logger.debug("Cache hit: %s / %s", distributor, mpn)
                return DistributorResult(**data)

        except Exception as exc:
            logger.error("Failed to read distributor cache: %s", exc)
            return None

    def set(self, distributor: str, mpn: str, result: Any) -> bool:
        """Store a DistributorResult in the cache.

        Args:
            distributor: Distributor name.
            mpn: Manufacturer part number.
            result: DistributorResult instance to cache.

        Returns:
            ``True`` on success, ``False`` otherwise.
        """
        key = self._make_key(distributor, mpn)
        try:
            with sqlite3.connect(self.cache_file) as conn:
                now = time.time()
                # Serialise without the raw_response field to save space
                result_data = result.model_dump(exclude={"raw_response"})
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO distributor_cache
                        (cache_key, distributor, mpn, result_data, created_at, last_accessed)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (key, distributor, mpn.upper().strip(), json.dumps(result_data), now, now),
                )
                conn.commit()
                logger.debug("Cached: %s / %s", distributor, mpn)
                return True
        except Exception as exc:
            logger.error("Failed to write distributor cache: %s", exc)
            return False

    def clear(
        self,
        distributor: Optional[str] = None,
        mpn: Optional[str] = None,
    ) -> int:
        """Remove cache entries.

        Args:
            distributor: If supplied, restrict to this distributor.
            mpn: If supplied, restrict to this MPN.

        Returns:
            Number of rows deleted.
        """
        try:
            with sqlite3.connect(self.cache_file) as conn:
                cursor = conn.cursor()
                if distributor and mpn:
                    cursor.execute(
                        "DELETE FROM distributor_cache WHERE distributor = ? AND mpn = ?",
                        (distributor, mpn.upper().strip()),
                    )
                elif distributor:
                    cursor.execute(
                        "DELETE FROM distributor_cache WHERE distributor = ?",
                        (distributor,),
                    )
                elif mpn:
                    cursor.execute(
                        "DELETE FROM distributor_cache WHERE mpn = ?",
                        (mpn.upper().strip(),),
                    )
                else:
                    cursor.execute("DELETE FROM distributor_cache")
                count = cursor.rowcount
                conn.commit()
                logger.info("Cleared %d distributor cache entries", count)
                return count
        except Exception as exc:
            logger.error("Failed to clear distributor cache: %s", exc)
            return 0

    def cleanup_expired(self) -> int:
        """Delete all expired entries.

        Returns:
            Number of rows deleted.
        """
        cutoff = time.time() - self.ttl_seconds
        try:
            with sqlite3.connect(self.cache_file) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM distributor_cache WHERE created_at < ?", (cutoff,)
                )
                count = cursor.rowcount
                conn.commit()
                if count:
                    logger.info("Cleaned up %d expired distributor cache entries", count)
                return count
        except Exception as exc:
            logger.error("Failed to clean up distributor cache: %s", exc)
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """Return basic cache statistics."""
        try:
            with sqlite3.connect(self.cache_file) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM distributor_cache")
                total = cursor.fetchone()[0]

                cursor.execute(
                    "SELECT distributor, COUNT(*) FROM distributor_cache GROUP BY distributor"
                )
                by_dist = {row[0]: row[1] for row in cursor.fetchall()}

                cursor.execute(
                    "SELECT MIN(created_at), MAX(created_at) FROM distributor_cache"
                )
                min_t, max_t = cursor.fetchone()

                return {
                    "total_entries": total,
                    "by_distributor": by_dist,
                    "oldest_entry_age_seconds": (time.time() - min_t) if min_t else None,
                    "newest_entry_age_seconds": (time.time() - max_t) if max_t else None,
                    "cache_file": str(self.cache_file),
                    "ttl_seconds": self.ttl_seconds,
                }
        except Exception as exc:
            logger.error("Failed to get distributor cache stats: %s", exc)
            return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_distributor_cache: Optional[DistributorCache] = None


def get_distributor_cache(
    cache_file: Optional[Path] = None,
    ttl_seconds: int = DistributorCache.DEFAULT_TTL_SECONDS,
) -> DistributorCache:
    """Return (or create) the global DistributorCache singleton."""
    global _distributor_cache
    if _distributor_cache is None or cache_file is not None:
        _distributor_cache = DistributorCache(cache_file=cache_file, ttl_seconds=ttl_seconds)
    return _distributor_cache
