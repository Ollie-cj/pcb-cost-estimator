# Test Suite Documentation

This directory contains comprehensive tests for the PCB Cost Estimator project.

## Test Structure

### Test Files

- `test_bom_parser.py` - Core BoM parser unit tests (271 lines)
- `test_bom_parser_edge_cases.py` - **NEW** Edge case tests for parser (300+ lines)
- `test_cost_estimator.py` - Core cost estimator tests (416 lines)
- `test_cost_estimator_detailed.py` - **NEW** Detailed cost tests with known components (350+ lines)
- `test_llm_enrichment.py` - Core LLM enrichment tests (422 lines)
- `test_llm_integration_fixtures.py` - **NEW** LLM tests with mocked fixtures (400+ lines)
- `test_reporting.py` - Report generation tests (424 lines)
- `test_end_to_end.py` - **NEW** End-to-end pipeline tests (450+ lines)
- `test_config.py` - Configuration tests (48 lines)

### Fixtures

#### BoM Fixtures (`fixtures/`)
- `arduino_shield_simple.csv` - Simple Arduino shield (~20 components)
- `iot_board_medium.csv` - Medium complexity IoT board (~74 components)
- `mixed_signal_complex.csv` - Complex mixed-signal board (228 components)

#### LLM Response Fixtures (`fixtures/llm_responses/`)
- `classification_responses.json` - Mocked component classification responses
- `price_reasonableness_responses.json` - Mocked price validation responses
- `obsolescence_responses.json` - Mocked obsolescence check responses

## Test Categories

Tests are marked with pytest markers:
- `@pytest.mark.unit` - Unit tests for individual components
- `@pytest.mark.integration` - Integration tests with mocked external services
- `@pytest.mark.e2e` - End-to-end tests running full pipeline

## Running Tests

### Run All Tests
```bash
pytest
```

### Run with Coverage
```bash
pytest --cov=src/pcb_cost_estimator --cov-report=html --cov-report=term-missing
```

### Run Specific Test Categories
```bash
pytest -m unit           # Run only unit tests
pytest -m integration    # Run only integration tests
pytest -m e2e           # Run only end-to-end tests
```

### Run Specific Test Files
```bash
pytest tests/test_bom_parser_edge_cases.py
pytest tests/test_end_to_end.py
```

## Test Coverage

The test suite is designed to achieve >85% code coverage across all modules:

### Coverage by Module
- **bom_parser.py**: Edge cases including missing columns, whitespace, unicode, empty rows
- **cost_estimator.py**: Known components with expected price ranges, all categories
- **llm_enrichment.py**: Mocked API responses, no real API calls in CI
- **reporting.py**: All output formats (JSON, CSV, Markdown, CLI tables)
- **End-to-end**: Full pipeline from BoM file to report output

### Edge Cases Tested
- Empty BoM files
- Single component BoMs
- All DNP components
- Missing MPNs
- Unicode characters
- Very large quantities
- Mixed package types
- Malformed data

## Fixture Details

### arduino_shield_simple.csv
- 20 components
- Categories: Resistors, Capacitors, ICs, Diodes, LEDs, Connectors, Switches, Crystal
- Typical use: Basic functionality testing

### iot_board_medium.csv
- 74 components
- Categories: All basic categories plus sensors, power management, communication modules
- Typical use: Medium complexity testing

### mixed_signal_complex.csv
- 228 components
- Categories: Resistors (35), Capacitors (30), Inductors (10), Diodes (15), ICs (65+), more
- Typical use: Performance and scalability testing

## LLM Testing Strategy

LLM tests use mocked responses to ensure:
1. No real API calls in CI/CD pipelines
2. Deterministic test results
3. Fast test execution
4. Coverage of error handling

Mocked responses are based on real LLM outputs and cover:
- High confidence classifications
- Low confidence scenarios
- Price reasonableness checks (valid and invalid)
- Obsolescence risk levels (low, medium, high)
- Error conditions (invalid JSON, missing fields, API failures)

## Test Metrics

Expected metrics when running full test suite:
- **Total tests**: 100+ test cases
- **Code coverage**: >85%
- **Execution time**: <30 seconds (with mocked LLM)
- **No external dependencies**: All tests run offline with fixtures

## Continuous Integration

The test suite is configured in `pyproject.toml` with:
- Coverage threshold: 85%
- HTML, XML, and terminal coverage reports
- Strict marker enforcement
- Verbose output enabled

## Contributing

When adding new tests:
1. Use appropriate pytest markers
2. Add docstrings explaining what is tested
3. Create fixtures for reusable test data
4. Ensure no external API calls (use mocks)
5. Update this README with new test descriptions
