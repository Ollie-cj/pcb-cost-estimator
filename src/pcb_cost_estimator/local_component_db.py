"""Local SQLite component database for caching component and pricing data."""

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Generator, List, Optional

logger = logging.getLogger(__name__)

# Default database location
DEFAULT_DB_PATH = Path.home() / ".pcb_cost_estimator" / "components.db"

# Current schema version – bump when migrating
SCHEMA_VERSION = 2


class LocalComponentDB:
    """SQLite-backed local component database.

    Stores component metadata (including provenance) and distributor
    availability information.  Schema migrations are applied automatically
    when the database is opened.

    Usage::

        db = LocalComponentDB()
        db.initialize()
        db.upsert_component(mpn="GRM188R71C104KA01D", manufacturer="Murata",
                            manufacturer_country="JP")
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._connection: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Create the database directory, open a connection, and apply schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self.db_path))
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._apply_schema()
        logger.debug("LocalComponentDB initialised at %s", self.db_path)

    def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    @contextmanager
    def _cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        if self._connection is None:
            raise RuntimeError("Database not initialised – call initialize() first")
        cursor = self._connection.cursor()
        try:
            yield cursor
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            cursor.close()

    # ------------------------------------------------------------------
    # Schema creation / migration
    # ------------------------------------------------------------------

    def _apply_schema(self) -> None:
        """Create tables if they don't exist and run any pending migrations."""
        assert self._connection is not None
        with self._connection:
            self._connection.executescript(_DDL_COMPONENTS)
            self._connection.executescript(_DDL_DISTRIBUTOR_AVAILABILITY)
            self._connection.executescript(_DDL_SCHEMA_VERSION)
            self._set_schema_version(SCHEMA_VERSION)

    def _get_schema_version(self) -> int:
        assert self._connection is not None
        row = self._connection.execute(
            "SELECT version FROM schema_version WHERE id = 1"
        ).fetchone()
        return int(row[0]) if row else 0

    def _set_schema_version(self, version: int) -> None:
        assert self._connection is not None
        self._connection.execute(
            "INSERT OR REPLACE INTO schema_version (id, version) VALUES (1, ?)",
            (version,),
        )

    # ------------------------------------------------------------------
    # Component CRUD
    # ------------------------------------------------------------------

    def upsert_component(
        self,
        mpn: str,
        manufacturer: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        package: Optional[str] = None,
        manufacturer_country: Optional[str] = None,
        manufacturer_region: Optional[str] = None,
    ) -> None:
        """Insert or update a component record.

        Args:
            mpn: Manufacturer part number (primary key).
            manufacturer: Manufacturer name.
            description: Component description.
            category: Component category string.
            package: Package / footprint string.
            manufacturer_country: ISO 3166-1 alpha-2 country code.
            manufacturer_region: Region enum value (EU, US, CN, …).
        """
        now = datetime.utcnow().isoformat()
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO components
                    (mpn, manufacturer, description, category, package,
                     manufacturer_country, manufacturer_region, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mpn) DO UPDATE SET
                    manufacturer         = excluded.manufacturer,
                    description          = excluded.description,
                    category             = excluded.category,
                    package              = excluded.package,
                    manufacturer_country = excluded.manufacturer_country,
                    manufacturer_region  = excluded.manufacturer_region,
                    last_updated         = excluded.last_updated
                """,
                (
                    mpn,
                    manufacturer,
                    description,
                    category,
                    package,
                    manufacturer_country,
                    manufacturer_region,
                    now,
                ),
            )

    def get_component(self, mpn: str) -> Optional[Dict]:
        """Retrieve a component by MPN.

        Returns:
            Dictionary with component data or ``None`` if not found.
        """
        with self._cursor() as cur:
            cur.execute("SELECT * FROM components WHERE mpn = ?", (mpn,))
            row = cur.fetchone()
        return dict(row) if row else None

    def delete_component(self, mpn: str) -> None:
        """Delete a component and its associated distributor availability rows."""
        with self._cursor() as cur:
            cur.execute(
                "DELETE FROM distributor_availability WHERE mpn = ?", (mpn,)
            )
            cur.execute("DELETE FROM components WHERE mpn = ?", (mpn,))

    def list_components(self) -> List[Dict]:
        """Return all component records."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM components ORDER BY mpn")
            return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Distributor availability CRUD
    # ------------------------------------------------------------------

    def upsert_distributor_availability(
        self,
        mpn: str,
        distributor: str,
        region: str,
        in_stock: bool,
        stock_quantity: Optional[int] = None,
        unit_price: Optional[float] = None,
        currency: str = "EUR",
        warehouse_location: Optional[str] = None,
        lead_time_days: Optional[int] = None,
    ) -> None:
        """Insert or update a distributor availability record.

        Args:
            mpn: Manufacturer part number (foreign key → components.mpn).
            distributor: Distributor name (e.g. "Mouser", "Farnell").
            region: DistributorRegion enum value (EU, UK, US, APAC, GLOBAL).
            in_stock: True if the part is currently available.
            stock_quantity: Available stock quantity.
            unit_price: Unit price in *currency*.
            currency: Currency code (default EUR).
            warehouse_location: Country / warehouse code (e.g. "DE", "NL").
            lead_time_days: Lead time when out of stock.
        """
        now = datetime.utcnow().isoformat()
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO distributor_availability
                    (mpn, distributor, region, in_stock, stock_quantity,
                     unit_price, currency, warehouse_location, lead_time_days,
                     last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mpn, distributor) DO UPDATE SET
                    region             = excluded.region,
                    in_stock           = excluded.in_stock,
                    stock_quantity     = excluded.stock_quantity,
                    unit_price         = excluded.unit_price,
                    currency           = excluded.currency,
                    warehouse_location = excluded.warehouse_location,
                    lead_time_days     = excluded.lead_time_days,
                    last_updated       = excluded.last_updated
                """,
                (
                    mpn,
                    distributor,
                    region,
                    int(in_stock),
                    stock_quantity,
                    unit_price,
                    currency,
                    warehouse_location,
                    lead_time_days,
                    now,
                ),
            )

    def get_distributor_availability(self, mpn: str) -> List[Dict]:
        """Return all distributor availability records for an MPN.

        Args:
            mpn: Manufacturer part number.

        Returns:
            List of distributor availability dictionaries.
        """
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM distributor_availability WHERE mpn = ? ORDER BY distributor",
                (mpn,),
            )
            return [dict(r) for r in cur.fetchall()]

    def delete_distributor_availability(self, mpn: str, distributor: str) -> None:
        """Remove a specific distributor record for an MPN."""
        with self._cursor() as cur:
            cur.execute(
                "DELETE FROM distributor_availability WHERE mpn = ? AND distributor = ?",
                (mpn, distributor),
            )


# ---------------------------------------------------------------------------
# DDL statements
# ---------------------------------------------------------------------------

_DDL_SCHEMA_VERSION = """
CREATE TABLE IF NOT EXISTS schema_version (
    id      INTEGER PRIMARY KEY,
    version INTEGER NOT NULL
);
"""

_DDL_COMPONENTS = """
CREATE TABLE IF NOT EXISTS components (
    mpn                  TEXT PRIMARY KEY,
    manufacturer         TEXT,
    description          TEXT,
    category             TEXT,
    package              TEXT,
    manufacturer_country TEXT,   -- ISO 3166-1 alpha-2 (e.g. JP, DE, US)
    manufacturer_region  TEXT,   -- ManufacturerRegion enum value
    last_updated         TEXT NOT NULL
);
"""

_DDL_DISTRIBUTOR_AVAILABILITY = """
CREATE TABLE IF NOT EXISTS distributor_availability (
    mpn                TEXT NOT NULL,
    distributor        TEXT NOT NULL,
    region             TEXT NOT NULL,   -- DistributorRegion enum value
    in_stock           INTEGER NOT NULL DEFAULT 0,
    stock_quantity     INTEGER,
    unit_price         REAL,
    currency           TEXT NOT NULL DEFAULT 'EUR',
    warehouse_location TEXT,
    lead_time_days     INTEGER,
    last_updated       TEXT NOT NULL,
    PRIMARY KEY (mpn, distributor),
    FOREIGN KEY (mpn) REFERENCES components(mpn) ON DELETE CASCADE
);
"""
