# Task: Implement LLM-powered component enrichment and pricing intelligence

## Instructions
Build an LLM integration layer that enhances the deterministic model with AI-powered analysis. This module should: (1) Use an LLM (OpenAI/Anthropic) to classify ambiguous components that the deterministic classifier can't handle, by sending the MPN + description and getting back category, typical price range, and availability assessment, (2) Implement an LLM-based 'price reasonableness checker' that reviews the deterministic estimates and flags outliers, (3) Use the LLM to identify potential component obsolescence risks and suggest alternatives, (4) Implement prompt templates with structured output parsing (JSON mode) for reliable extraction, (5) Add caching (SQLite or file-based) to avoid redundant LLM calls for previously seen MPNs, (6) Implement graceful fallback to deterministic-only mode when LLM is unavailable or API key is missing. Use a strategy pattern so the LLM provider can be swapped.

## Acceptance Criteria

* LLM correctly classifies at least 80% of common electronic components
* Structured JSON responses are parsed reliably with error handling
* Caching prevents duplicate API calls for the same MPN
* System works in degraded mode without LLM API access
* Prompt templates are versioned and stored separately
* Rate limiting and retry logic implemented for API calls
* Obsolescence risk flagging works for at least known EOL parts

**Complexity:** high
**Dependencies:** Build deterministic cost model engine

## Acceptance Criteria
- 

## Rules
- Work autonomously — make all necessary changes
- Commit your work with descriptive messages
- Write output summary to /workspace/.aegis/output.json when done
