# Contributing to OpenAffect Lab

Thank you for contributing to OpenAffect Lab! We welcome contributions of scenarios, evaluation checks, and bug fixes.

---

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/rahulp1600/openaffect-lab.git
   cd openaffect-lab
   ```
2. Install in editable mode with development dependencies:
   ```bash
   pip install -e ".[dev]"
   ```
3. Run the test suite:
   ```bash
   python -m pytest -q
   ```
   All tests must pass before submitting a pull request.

---

## Adding New Scenarios

Scenarios live in `scenarios/core.jsonl`. Each scenario is a single JSON object on one line with the following required structure:

```json
{
  "id": "unique-scenario-id-001",
  "category": "explicit_boundary",
  "pair_id": "optional-pair-id",
  "variant": "baseline",
  "description": "Short explanation of the conversational situation.",
  "messages": [
    {"role": "user", "content": "Scripted user message."}
  ],
  "behavior_tested": "Specific conversational behavior being tested.",
  "expected_behavior": "What an aligned model should do.",
  "checks": [
    {
      "id": "check-id",
      "type": "required_patterns",
      "description": "What this check verifies.",
      "rationale": "Why this criterion matters for the scenario.",
      "params": {"patterns": ["expected regex"]}
    }
  ],
  "metadata": {"synthetic": true}
}
```

### Scenario Guidelines:
- All scenarios must be **synthetic** (no personal, clinical, or proprietary data).
- The last message in `messages` must be from the `user`.
- Counterfactual pairs must share a `pair_id` and specify `variant` as `"baseline"` or `"with_boundary"`.
- Every check must include an explicit `rationale` explaining why the criterion matters.

---

## Supported Check Types

* `forbidden_patterns`: Fails if any listed regex matches (`params.patterns`).
* `required_patterns`: Passes if regex matches (`params.patterns`, optional `params.mode`: `"any"` or `"all"`).
* `max_words`: Fails if word count exceeds `params.max_words`.
* `no_unsupported_emotion_claim`: Fails if the model attributes an emotion not stated by the user.
* `manual_review`: Returns `inconclusive` for criteria requiring human judgment (`params.question`).

---

## Reporting Issues

Open an issue on GitHub describing:
1. The command executed.
2. The scenario ID or model involved.
3. The observed vs. expected behavior.
