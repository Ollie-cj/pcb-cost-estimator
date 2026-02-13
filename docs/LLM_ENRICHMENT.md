# LLM Enrichment Guide

## Overview

The LLM Enrichment feature enhances the deterministic cost model with AI-powered analysis using Large Language Models (OpenAI or Anthropic). This provides:

1. **Component Classification** - Classify ambiguous components that the deterministic classifier can't handle
2. **Price Reasonableness Checking** - Review cost estimates and flag pricing outliers
3. **Obsolescence Detection** - Identify EOL/NRND components and suggest alternatives

## Features

### 1. Component Classification

When the deterministic classifier cannot confidently identify a component (based on MPN patterns, description keywords, or reference designators), the LLM can analyze the component and provide:

- Component category (resistor, capacitor, IC, etc.)
- Confidence score (0.0 - 1.0)
- Typical price range
- Availability assessment
- Package type identification
- Reasoning for classification

**Example:**
```
MPN: XYZ-2023-ABC
Description: "Special component"
Reference: U5

→ LLM classifies as: IC (confidence: 0.85)
→ Reasoning: "Pattern suggests integrated circuit, typical for U designator"
```

### 2. Price Reasonableness Checking

After calculating deterministic cost estimates, the LLM reviews each component's pricing and flags potential issues:

- Prices significantly above/below market rates (>50% variance)
- Potential data entry errors (off by 10x)
- Unusual price patterns
- Expected price range recommendations

**Example:**
```
Component: GRM188R71C104KA01D (Ceramic Capacitor)
Estimated: $5.00
LLM Check: ⚠ UNREASONABLE
Expected: $0.05 - $0.10
Variance: +5000%
Suggestion: "Verify pricing data - likely decimal point error"
```

### 3. Obsolescence Detection

The LLM analyzes components for lifecycle risks and provides:

- Obsolescence risk level (none, low, medium, high, obsolete)
- Lifecycle status (active, NRND, EOL, obsolete)
- Risk factors (e.g., "EOL announced", "Limited availability")
- Alternative component suggestions with compatibility ratings
- Recommendations for mitigation

**Example:**
```
MPN: LM358N (DIP package op-amp)
Risk: MEDIUM
Status: NRND (Not Recommended for New Designs)
Alternatives:
  - LM358DR (SOIC, drop-in replacement)
  - OPA2134PA (enhanced performance alternative)
Recommendation: "Consider migration to surface mount alternative"
```

## Configuration

### Basic Setup

1. **Edit configuration file** (`config/llm_enrichment.yaml`):

```yaml
llm_enrichment:
  enabled: true
  provider: "openai"  # or "anthropic"
  api_key: "sk-..."   # Your API key
  model: null         # Uses provider default if not specified
  temperature: 0.0    # 0.0 for deterministic responses
  max_tokens: 1000
  requests_per_minute: 60
  cache_ttl_days: 30
  enable_classification: true
  enable_price_checking: true
  enable_obsolescence_detection: true
```

2. **Or use environment variables** (recommended for security):

```bash
export OPENAI_API_KEY="sk-..."
# or
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Provider Options

#### OpenAI
- **Provider**: `openai`
- **Default Model**: `gpt-4o-mini` (recommended for cost efficiency)
- **Alternative Models**: `gpt-4`, `gpt-4-turbo`
- **API Key Format**: `sk-...`

#### Anthropic
- **Provider**: `anthropic`
- **Default Model**: `claude-3-5-sonnet-20241022`
- **Alternative Models**: `claude-3-opus`, `claude-3-haiku`
- **API Key Format**: `sk-ant-...`

### Feature Flags

Enable/disable specific enrichment features:

```yaml
llm_enrichment:
  enable_classification: true           # LLM component classification
  enable_price_checking: true           # Price reasonableness checking
  enable_obsolescence_detection: true   # Obsolescence risk detection
```

## Usage

### Command Line

#### Basic estimation with LLM enrichment:
```bash
pcb-cost-estimator estimate bom.csv --enable-llm
```

#### Specify LLM provider and API key:
```bash
pcb-cost-estimator estimate bom.csv \
  --enable-llm \
  --llm-provider openai \
  --llm-api-key "sk-..."
```

#### With environment variable:
```bash
export OPENAI_API_KEY="sk-..."
pcb-cost-estimator estimate bom.csv --enable-llm
```

### Python API

```python
from pcb_cost_estimator.bom_parser import BomParser
from pcb_cost_estimator.cost_estimator import CostEstimator
from pcb_cost_estimator.llm_enrichment import create_enrichment_service
from pcb_cost_estimator.config import load_cost_model_config

# Parse BOM
parser = BomParser()
bom_result = parser.parse_file("bom.csv")

# Create LLM enrichment service
llm_service = create_enrichment_service(
    provider_name="openai",
    api_key="sk-...",
    enabled=True,
    temperature=0.0,
    max_tokens=1000
)

# Create cost estimator with LLM enrichment
config = load_cost_model_config()
estimator = CostEstimator(config, llm_enrichment=llm_service)

# Estimate costs with LLM enrichment
cost_estimate = estimator.estimate_bom_cost(bom_result, board_quantity=100)

# Results include LLM insights
for component in cost_estimate.component_costs:
    if "LLM classification" in str(component.notes):
        print(f"{component.reference_designator}: LLM-classified")

for warning in cost_estimate.warnings:
    if "Price may be unreasonable" in warning:
        print(f"Price issue: {warning}")

for note in cost_estimate.notes:
    if "obsolescence" in note.lower():
        print(f"Obsolescence: {note}")
```

## Caching

The LLM enrichment system includes a built-in SQLite cache to prevent redundant API calls:

- **Location**: `~/.pcb_cost_estimator/llm_cache.db`
- **TTL**: 30 days (configurable)
- **Key**: MPN + prompt type + context
- **Benefits**:
  - Faster repeated estimations
  - Reduced API costs
  - Offline access to previous results

### Cache Management

View cache statistics:
```python
from pcb_cost_estimator.llm_cache import get_llm_cache

cache = get_llm_cache()
stats = cache.get_stats()
print(f"Total cached entries: {stats['total_entries']}")
print(f"Tokens saved: {stats['total_tokens_saved']}")
```

Clear cache:
```python
cache.clear()  # Clear all
cache.clear(prompt_type="classification")  # Clear classification only
cache.clear(mpn="LM358DR")  # Clear specific MPN
```

## Prompt Templates

LLM prompts are versioned and stored in `config/llm_prompts/`:

- `component_classification_v1.yaml` - Component classification prompt
- `price_reasonableness_v1.yaml` - Price checking prompt
- `obsolescence_detection_v1.yaml` - Obsolescence detection prompt

### Customizing Prompts

1. Copy template to new version:
```bash
cp config/llm_prompts/component_classification_v1.yaml \
   config/llm_prompts/component_classification_v2.yaml
```

2. Edit prompt content, update version field

3. Use custom version in code:
```python
from pcb_cost_estimator.prompt_templates import get_template_manager

manager = get_template_manager()
template = manager.load_template("component_classification", version="v2")
```

## Rate Limiting and Retry Logic

Built-in protections for API stability:

- **Rate Limiting**: Token bucket algorithm (default: 60 req/min)
- **Retry Logic**: Exponential backoff (default: 3 retries)
- **Backoff Schedule**: 1s, 2s, 4s
- **Error Handling**: Graceful degradation to deterministic-only mode

## Graceful Degradation

The system operates in "degraded mode" when:

- LLM enrichment is disabled
- No API key is provided
- API calls fail after retries
- Rate limits are exceeded

In degraded mode:
- Deterministic classification continues normally
- No price checking or obsolescence detection
- Warnings logged but processing continues
- No impact on core functionality

## Cost Considerations

### API Costs (Approximate)

**OpenAI (gpt-4o-mini)**:
- Input: $0.15 / 1M tokens
- Output: $0.60 / 1M tokens
- ~200-500 tokens per component
- **Estimate**: $0.0001 - $0.0005 per component

**Anthropic (claude-3-5-sonnet)**:
- Input: $3.00 / 1M tokens
- Output: $15.00 / 1M tokens
- ~200-500 tokens per component
- **Estimate**: $0.002 - $0.008 per component

### Cost Optimization

1. **Use caching**: First analysis incurs cost, subsequent lookups are free
2. **Choose efficient model**: `gpt-4o-mini` is 10-20x cheaper than `gpt-4`
3. **Selective enrichment**: Disable features you don't need
4. **Batch processing**: Process multiple BOMs with shared components
5. **Set rate limits**: Control spending with `requests_per_minute`

## Troubleshooting

### LLM enrichment not working

1. **Check API key**:
```bash
pcb-cost-estimator validate-config
```
Look for "API Key Configured: True"

2. **Check logs**:
```bash
pcb-cost-estimator estimate bom.csv --enable-llm --verbose
```

3. **Test manually**:
```python
from pcb_cost_estimator.llm_enrichment import create_enrichment_service

service = create_enrichment_service("openai", "sk-...", enabled=True)
result = service.classify_component("LM358DR", "Op-amp", "U1")
print(result)
```

### Rate limit errors

Reduce `requests_per_minute` in configuration:
```yaml
llm_enrichment:
  requests_per_minute: 30  # Slower but more stable
```

### Cache issues

Clear and rebuild cache:
```python
from pcb_cost_estimator.llm_cache import get_llm_cache
cache = get_llm_cache()
cache.clear()
```

## Best Practices

1. **Start with test run**: Use small BOM first to validate setup
2. **Monitor costs**: Track API usage in provider dashboard
3. **Use caching**: Re-run same BOMs to verify cache effectiveness
4. **Review LLM suggestions**: LLM insights are recommendations, not absolute truth
5. **Combine with validation**: Cross-reference LLM results with datasheets
6. **Version control**: Keep prompt templates in version control
7. **Environment variables**: Never commit API keys to repositories

## Examples

### Example 1: Classify Unknown Component

```python
from pcb_cost_estimator.llm_enrichment import create_enrichment_service

service = create_enrichment_service("openai", api_key="sk-...", enabled=True)

result = service.classify_component(
    mpn="ABC-XYZ-123",
    description="Unknown electronic component",
    reference_designator="U10"
)

if result:
    print(f"Category: {result.category}")
    print(f"Confidence: {result.confidence}")
    print(f"Reasoning: {result.reasoning}")
```

### Example 2: Batch Obsolescence Check

```python
components = [
    {"mpn": "LM358N", "manufacturer": "TI", "category": "ic", "quantity": 100},
    {"mpn": "74HC00", "manufacturer": "NXP", "category": "ic", "quantity": 50},
]

results = service.batch_check_obsolescence(components)

for result in results:
    if result.obsolescence_risk in ["high", "obsolete"]:
        print(f"⚠ {result.mpn}: {result.obsolescence_risk}")
        if result.alternatives:
            print(f"  Alternatives: {[alt['mpn'] for alt in result.alternatives]}")
```

### Example 3: Price Validation

```python
price_check = service.check_price_reasonableness(
    mpn="GRM188R71C104KA01D",
    description="100nF ceramic capacitor",
    category="capacitor",
    package_type="smd_small",
    unit_cost_low=0.08,
    unit_cost_typical=0.10,
    unit_cost_high=0.12,
    quantity=100
)

if price_check and not price_check.is_reasonable:
    print(f"Price issue detected!")
    print(f"Expected range: ${price_check.expected_price_range['low']:.4f} - "
          f"${price_check.expected_price_range['high']:.4f}")
    print(f"Variance: {price_check.price_variance_percentage:.1f}%")
```

## Security Notes

1. **API Keys**: Never commit API keys to version control
2. **Use environment variables**: Store keys in environment, not config files
3. **Rotate keys**: Regularly rotate API keys for security
4. **Access control**: Limit API key permissions to minimum required
5. **Monitor usage**: Set up billing alerts in provider dashboard

## Support

For issues or questions:
- GitHub Issues: [anthropics/claude-code/issues](https://github.com/anthropics/claude-code/issues)
- Documentation: See README.md for additional resources
