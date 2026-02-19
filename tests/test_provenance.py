"""Unit tests for provenance models, BomItem provenance fields, and LocalComponentDB."""

import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from pcb_cost_estimator.models import (
    BomItem,
    DistributorAvailability,
    DistributorRegion,
    ManufacturerRegion,
    ProvenanceRisk,
    ProvenanceScore,
    SourcingMode,
)
from pcb_cost_estimator.local_component_db import LocalComponentDB


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestManufacturerRegion:
    def test_all_values_accessible(self):
        assert ManufacturerRegion.EU == "EU"
        assert ManufacturerRegion.CN == "CN"
        assert ManufacturerRegion.US == "US"
        assert ManufacturerRegion.JP == "JP"
        assert ManufacturerRegion.KR == "KR"
        assert ManufacturerRegion.TW == "TW"
        assert ManufacturerRegion.UK == "UK"
        assert ManufacturerRegion.OTHER == "OTHER"

    def test_string_comparison(self):
        assert ManufacturerRegion.EU == "EU"


class TestDistributorRegion:
    def test_all_values_accessible(self):
        assert DistributorRegion.EU == "EU"
        assert DistributorRegion.UK == "UK"
        assert DistributorRegion.US == "US"
        assert DistributorRegion.APAC == "APAC"
        assert DistributorRegion.GLOBAL == "GLOBAL"


class TestSourcingMode:
    def test_all_values(self):
        assert SourcingMode.GLOBAL == "GLOBAL"
        assert SourcingMode.EU_PREFERRED == "EU_PREFERRED"
        assert SourcingMode.EU_ONLY == "EU_ONLY"


class TestProvenanceRisk:
    def test_all_values(self):
        assert ProvenanceRisk.LOW == "LOW"
        assert ProvenanceRisk.MEDIUM == "MEDIUM"
        assert ProvenanceRisk.HIGH == "HIGH"


# ---------------------------------------------------------------------------
# DistributorAvailability model tests
# ---------------------------------------------------------------------------


class TestDistributorAvailability:
    def test_minimal_valid(self):
        da = DistributorAvailability(
            distributor_name="Mouser",
            distributor_region=DistributorRegion.EU,
            in_stock=True,
        )
        assert da.distributor_name == "Mouser"
        assert da.in_stock is True
        assert da.currency == "EUR"
        assert da.stock_quantity is None
        assert da.unit_price is None
        assert da.warehouse_location is None
        assert da.lead_time_days is None

    def test_fully_populated(self):
        da = DistributorAvailability(
            distributor_name="Farnell",
            distributor_region=DistributorRegion.UK,
            in_stock=True,
            stock_quantity=5000,
            unit_price=0.012,
            currency="GBP",
            warehouse_location="UK",
            lead_time_days=2,
        )
        assert da.stock_quantity == 5000
        assert da.unit_price == pytest.approx(0.012)
        assert da.currency == "GBP"
        assert da.warehouse_location == "UK"
        assert da.lead_time_days == 2

    def test_out_of_stock_with_lead_time(self):
        da = DistributorAvailability(
            distributor_name="Digikey",
            distributor_region=DistributorRegion.US,
            in_stock=False,
            lead_time_days=21,
        )
        assert da.in_stock is False
        assert da.lead_time_days == 21

    def test_stock_quantity_must_be_non_negative(self):
        with pytest.raises(ValidationError):
            DistributorAvailability(
                distributor_name="X",
                distributor_region=DistributorRegion.EU,
                in_stock=True,
                stock_quantity=-1,
            )

    def test_unit_price_must_be_non_negative(self):
        with pytest.raises(ValidationError):
            DistributorAvailability(
                distributor_name="X",
                distributor_region=DistributorRegion.EU,
                in_stock=True,
                unit_price=-0.01,
            )

    def test_lead_time_must_be_non_negative(self):
        with pytest.raises(ValidationError):
            DistributorAvailability(
                distributor_name="X",
                distributor_region=DistributorRegion.EU,
                in_stock=False,
                lead_time_days=-5,
            )

    def test_string_region_coercion(self):
        da = DistributorAvailability(
            distributor_name="RS",
            distributor_region="EU",
            in_stock=True,
        )
        assert da.distributor_region == DistributorRegion.EU

    def test_default_currency_is_eur(self):
        da = DistributorAvailability(
            distributor_name="X",
            distributor_region=DistributorRegion.GLOBAL,
            in_stock=True,
        )
        assert da.currency == "EUR"


# ---------------------------------------------------------------------------
# ProvenanceScore model tests
# ---------------------------------------------------------------------------


class TestProvenanceScore:
    def test_minimal_valid(self):
        ps = ProvenanceScore(
            sourcing_mode=SourcingMode.GLOBAL,
            eu_available=False,
            eu_manufactured=False,
            provenance_risk=ProvenanceRisk.HIGH,
        )
        assert ps.eu_available is False
        assert ps.eu_manufactured is False
        assert ps.eu_price_delta_pct is None

    def test_eu_preferred_low_risk(self):
        ps = ProvenanceScore(
            sourcing_mode=SourcingMode.EU_PREFERRED,
            eu_available=True,
            eu_manufactured=True,
            eu_price_delta_pct=5.0,
            provenance_risk=ProvenanceRisk.LOW,
        )
        assert ps.eu_available is True
        assert ps.eu_manufactured is True
        assert ps.eu_price_delta_pct == pytest.approx(5.0)
        assert ps.provenance_risk == ProvenanceRisk.LOW

    def test_eu_only_medium_risk(self):
        ps = ProvenanceScore(
            sourcing_mode=SourcingMode.EU_ONLY,
            eu_available=True,
            eu_manufactured=False,
            eu_price_delta_pct=28.5,
            provenance_risk=ProvenanceRisk.MEDIUM,
        )
        assert ps.sourcing_mode == SourcingMode.EU_ONLY
        assert ps.provenance_risk == ProvenanceRisk.MEDIUM

    def test_string_enum_coercion(self):
        ps = ProvenanceScore(
            sourcing_mode="EU_ONLY",
            eu_available=True,
            eu_manufactured=False,
            provenance_risk="HIGH",
        )
        assert ps.sourcing_mode == SourcingMode.EU_ONLY
        assert ps.provenance_risk == ProvenanceRisk.HIGH


# ---------------------------------------------------------------------------
# BomItem provenance fields
# ---------------------------------------------------------------------------


class TestBomItemProvenanceFields:
    def _base_item(self, **kwargs):
        defaults = dict(reference_designator="R1", quantity=10)
        defaults.update(kwargs)
        return BomItem(**defaults)

    def test_provenance_fields_default_to_none_or_empty(self):
        item = self._base_item()
        assert item.manufacturer_country is None
        assert item.manufacturer_region is None
        assert item.available_distributors == []

    def test_manufacturer_country_valid(self):
        item = self._base_item(manufacturer_country="DE")
        assert item.manufacturer_country == "DE"

    def test_manufacturer_country_invalid_length(self):
        with pytest.raises(ValidationError):
            self._base_item(manufacturer_country="DEU")  # 3 chars – too long

    def test_manufacturer_region_enum(self):
        item = self._base_item(manufacturer_region=ManufacturerRegion.JP)
        assert item.manufacturer_region == ManufacturerRegion.JP

    def test_manufacturer_region_string_coercion(self):
        item = self._base_item(manufacturer_region="CN")
        assert item.manufacturer_region == ManufacturerRegion.CN

    def test_available_distributors_populated(self):
        da1 = DistributorAvailability(
            distributor_name="Mouser",
            distributor_region=DistributorRegion.EU,
            in_stock=True,
            stock_quantity=10000,
            unit_price=0.008,
        )
        da2 = DistributorAvailability(
            distributor_name="Digikey",
            distributor_region=DistributorRegion.US,
            in_stock=True,
            stock_quantity=50000,
            unit_price=0.007,
        )
        item = self._base_item(available_distributors=[da1, da2])
        assert len(item.available_distributors) == 2
        assert item.available_distributors[0].distributor_name == "Mouser"

    def test_existing_fields_unaffected(self):
        """Provenance fields must not break core BomItem behaviour."""
        item = BomItem(
            reference_designator="C5",
            quantity=4,
            manufacturer="Murata",
            manufacturer_part_number="GRM188R71C104KA01D",
            description="100nF 16V X7R 0603",
            package="0603",
            value="100nF",
            dnp=False,
        )
        assert item.reference_designator == "C5"
        assert item.quantity == 4
        assert item.manufacturer == "Murata"
        # provenance defaults
        assert item.manufacturer_country is None
        assert item.available_distributors == []

    def test_full_provenance_on_bom_item(self):
        da = DistributorAvailability(
            distributor_name="Farnell",
            distributor_region=DistributorRegion.EU,
            in_stock=True,
            stock_quantity=200,
            unit_price=2.50,
            warehouse_location="NL",
        )
        item = BomItem(
            reference_designator="U1",
            quantity=1,
            manufacturer="STMicroelectronics",
            manufacturer_country="FR",
            manufacturer_region=ManufacturerRegion.EU,
            available_distributors=[da],
        )
        assert item.manufacturer_country == "FR"
        assert item.manufacturer_region == ManufacturerRegion.EU
        assert item.available_distributors[0].warehouse_location == "NL"


# ---------------------------------------------------------------------------
# LocalComponentDB tests
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    """Create a fresh LocalComponentDB backed by a temp-dir SQLite file."""
    db_path = tmp_path / "test_components.db"
    instance = LocalComponentDB(db_path=db_path)
    instance.initialize()
    yield instance
    instance.close()


class TestLocalComponentDB:
    def test_initialize_creates_db_file(self, tmp_path):
        db_path = tmp_path / "sub" / "components.db"
        instance = LocalComponentDB(db_path=db_path)
        instance.initialize()
        assert db_path.exists()
        instance.close()

    def test_upsert_and_get_component(self, db):
        db.upsert_component(
            mpn="RC0603FR-0710KL",
            manufacturer="Yageo",
            description="10k 1% 0603",
            category="resistor",
            package="0603",
            manufacturer_country="TW",
            manufacturer_region="TW",
        )
        row = db.get_component("RC0603FR-0710KL")
        assert row is not None
        assert row["mpn"] == "RC0603FR-0710KL"
        assert row["manufacturer"] == "Yageo"
        assert row["manufacturer_country"] == "TW"
        assert row["manufacturer_region"] == "TW"

    def test_get_nonexistent_component_returns_none(self, db):
        assert db.get_component("DOES_NOT_EXIST") is None

    def test_upsert_updates_existing_component(self, db):
        db.upsert_component(mpn="ABC123", manufacturer="OldMfr")
        db.upsert_component(mpn="ABC123", manufacturer="NewMfr", manufacturer_country="DE")
        row = db.get_component("ABC123")
        assert row["manufacturer"] == "NewMfr"
        assert row["manufacturer_country"] == "DE"

    def test_delete_component(self, db):
        db.upsert_component(mpn="DEL001")
        assert db.get_component("DEL001") is not None
        db.delete_component("DEL001")
        assert db.get_component("DEL001") is None

    def test_list_components_empty(self, db):
        assert db.list_components() == []

    def test_list_components_multiple(self, db):
        db.upsert_component(mpn="A001")
        db.upsert_component(mpn="B002")
        rows = db.list_components()
        assert len(rows) == 2
        mpns = [r["mpn"] for r in rows]
        assert "A001" in mpns
        assert "B002" in mpns

    def test_upsert_distributor_availability(self, db):
        db.upsert_component(mpn="MPN1")
        db.upsert_distributor_availability(
            mpn="MPN1",
            distributor="Mouser",
            region="EU",
            in_stock=True,
            stock_quantity=5000,
            unit_price=0.05,
            currency="EUR",
            warehouse_location="NL",
            lead_time_days=None,
        )
        rows = db.get_distributor_availability("MPN1")
        assert len(rows) == 1
        r = rows[0]
        assert r["distributor"] == "Mouser"
        assert r["region"] == "EU"
        assert r["in_stock"] == 1
        assert r["stock_quantity"] == 5000
        assert r["unit_price"] == pytest.approx(0.05)
        assert r["currency"] == "EUR"
        assert r["warehouse_location"] == "NL"

    def test_upsert_distributor_updates_existing(self, db):
        db.upsert_component(mpn="MPN2")
        db.upsert_distributor_availability(
            mpn="MPN2", distributor="Farnell", region="EU",
            in_stock=True, stock_quantity=100,
        )
        db.upsert_distributor_availability(
            mpn="MPN2", distributor="Farnell", region="UK",
            in_stock=False, stock_quantity=0, lead_time_days=14,
        )
        rows = db.get_distributor_availability("MPN2")
        assert len(rows) == 1
        assert rows[0]["region"] == "UK"
        assert rows[0]["in_stock"] == 0
        assert rows[0]["lead_time_days"] == 14

    def test_multiple_distributors_for_same_mpn(self, db):
        db.upsert_component(mpn="MPN3")
        for dist, region in [("Mouser", "US"), ("Farnell", "EU"), ("RS", "UK")]:
            db.upsert_distributor_availability(
                mpn="MPN3", distributor=dist, region=region, in_stock=True
            )
        rows = db.get_distributor_availability("MPN3")
        assert len(rows) == 3

    def test_get_distributor_availability_empty(self, db):
        db.upsert_component(mpn="MPN4")
        assert db.get_distributor_availability("MPN4") == []

    def test_delete_distributor_availability(self, db):
        db.upsert_component(mpn="MPN5")
        db.upsert_distributor_availability(
            mpn="MPN5", distributor="Mouser", region="EU", in_stock=True
        )
        db.delete_distributor_availability("MPN5", "Mouser")
        assert db.get_distributor_availability("MPN5") == []

    def test_delete_component_cascades_to_distributor(self, db):
        db.upsert_component(mpn="MPN6")
        db.upsert_distributor_availability(
            mpn="MPN6", distributor="Mouser", region="EU", in_stock=True
        )
        db.delete_component("MPN6")
        assert db.get_component("MPN6") is None
        assert db.get_distributor_availability("MPN6") == []

    def test_not_initialized_raises(self, tmp_path):
        db_path = tmp_path / "uninit.db"
        instance = LocalComponentDB(db_path=db_path)
        with pytest.raises(RuntimeError, match="not initialised"):
            instance.get_component("X")

    def test_schema_version_set(self, db):
        version = db._get_schema_version()
        assert version == 2  # SCHEMA_VERSION constant


# ---------------------------------------------------------------------------
# ProvenanceConfig tests
# ---------------------------------------------------------------------------


class TestProvenanceConfig:
    def test_defaults(self):
        from pcb_cost_estimator.config import ProvenanceConfig

        cfg = ProvenanceConfig()
        assert cfg.default_mode == "eu_preferred"
        assert "DE" in cfg.eu_countries
        assert "FR" in cfg.eu_countries
        assert len(cfg.eu_countries) == 27
        assert cfg.uk_included_in_eu is True
        assert cfg.price_premium_threshold == pytest.approx(0.30)

    def test_custom_values(self):
        from pcb_cost_estimator.config import ProvenanceConfig

        cfg = ProvenanceConfig(
            default_mode="eu_only",
            eu_countries=["DE", "FR"],
            uk_included_in_eu=False,
            price_premium_threshold=0.15,
        )
        assert cfg.default_mode == "eu_only"
        assert cfg.eu_countries == ["DE", "FR"]
        assert cfg.uk_included_in_eu is False
        assert cfg.price_premium_threshold == pytest.approx(0.15)

    def test_invalid_mode_raises(self):
        from pcb_cost_estimator.config import ProvenanceConfig

        with pytest.raises(ValidationError):
            ProvenanceConfig(default_mode="invalid_mode")

    def test_valid_modes(self):
        from pcb_cost_estimator.config import ProvenanceConfig

        for mode in ("global", "eu_preferred", "eu_only"):
            cfg = ProvenanceConfig(default_mode=mode)
            assert cfg.default_mode == mode

    def test_config_model_includes_provenance(self):
        from pcb_cost_estimator.config import Config

        cfg = Config()
        assert hasattr(cfg, "provenance")
        assert cfg.provenance.default_mode == "eu_preferred"

    def test_config_load_with_provenance_section(self, tmp_path):
        """Config loader should parse a YAML file that contains a provenance section."""
        import yaml
        from pcb_cost_estimator.config import load_config

        cfg_data = {
            "provenance": {
                "default_mode": "eu_only",
                "eu_countries": ["DE", "FR", "NL"],
                "uk_included_in_eu": False,
                "price_premium_threshold": 0.20,
            }
        }
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.dump(cfg_data))
        loaded = load_config(cfg_file)
        assert loaded["provenance"]["default_mode"] == "eu_only"
        assert "DE" in loaded["provenance"]["eu_countries"]
        assert loaded["provenance"]["uk_included_in_eu"] is False
        assert loaded["provenance"]["price_premium_threshold"] == pytest.approx(0.20)
