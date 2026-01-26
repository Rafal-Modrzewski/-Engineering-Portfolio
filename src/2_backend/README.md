# Deterministic AI Service

## The Problem
LLMs are non-deterministic and return unstructured text. In production:
- Gemini 2.5 Flash returned invalid JSON 19% of the time
- Users triggered AI calls in invalid campaign states → cost spikes
- No audit trail for compliance (who approved what?)

## The Solution / Design Decision
A three-layer guardrail system:

### 1. Input Guardrail (Decorator)
```python
@require_valid_campaign(['ideas_approved'])
async def generate_content(...)
```
**Enforces:** User authorization + FSM state + valid action

### 2. Output Guardrail (Robust Parser)
```python
def _robust_json_parse(self, raw_text: str):
    # Strips Markdown, handles trailing commas
    return json5.loads(clean_text)
```
**Handles:** GPT-4 markdown wrappers, malformed JSON

### 3. Orchestration (Separation of Concerns)
- Prompt construction
- LLM provider interface
- Schema validation
- State transition

## Prod Impact
- **Zero invalid state errors** in Q4 2025
- **94% reduction** in JSON parsing failures
- **100% audit trail** for compliance

## Prod Note
In production, this integrates with:
- `rate_limiter.py` (prevents cost spirals)
- `service_controls.py` (circuit breakers)
- `PostgresGovernor` (prevents DB saturation from AI traffic spikes)

Available for detailed discussion during interview.
