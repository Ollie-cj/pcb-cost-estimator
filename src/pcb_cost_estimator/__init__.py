"""PCB Cost Estimator - AI-powered PCB cost estimation tool."""

__version__ = "0.1.0"

from .models import (
    BomItem,
    BomParseResult,
    ComponentCategory,
    PackageType,
    PriceBreak,
    ComponentCostEstimate,
    AssemblyCost,
    OverheadCosts,
    CostEstimate,
)
from .bom_parser import BomParser, ColumnMatcher
from .cost_estimator import CostEstimator, ComponentClassifier, PackageClassifier
from .distributor_client import DistributorClient, DistributorResult
from .distributor_cache import DistributorCache, get_distributor_cache
from .farnell_client import FarnellClient
from .rs_components_client import RSComponentsClient
from .tme_client import TMEClient

__all__ = [
    "BomItem",
    "BomParseResult",
    "ComponentCategory",
    "PackageType",
    "PriceBreak",
    "ComponentCostEstimate",
    "AssemblyCost",
    "OverheadCosts",
    "CostEstimate",
    "BomParser",
    "ColumnMatcher",
    "CostEstimator",
    "ComponentClassifier",
    "PackageClassifier",
    # Distributor clients
    "DistributorClient",
    "DistributorResult",
    "DistributorCache",
    "get_distributor_cache",
    "FarnellClient",
    "RSComponentsClient",
    "TMEClient",
]
