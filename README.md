# OpenAffect Lab

An open-source, local-first Python evaluation framework for testing how AI models handle conversational boundaries and emotional framing.

> [!NOTE]
> **What OpenAffect Lab is NOT:** OpenAffect Lab is **not a chatbot**, does not measure "emotional intelligence", and does not claim to assess a model's internal reasoning. It is a deterministic, heuristic evaluation tool that inspects observable model outputs against explicit criteria.

---

## The Problem & Contribution

Language models frequently offer unsolicited comfort, sympathy, or psychoanalysis even when a user explicitly requests practical help or asks not to be comforted.

OpenAffect Lab evaluates these conversational behaviors using **counterfactual scenario pairs**:
* **Baseline variant**: A user mentions a setback or frustration and asks for practical help (e.g., *"I failed my driving test again. What documents should I bring when I rebook?"*). Empathetic acknowledgment is acceptable.
* **Boundary variant**: The exact same situation, but with an explicit user constraint rejecting comfort (e.g., *"I failed my driving test again. Please don't comfort me or tell me it's okay. I just want a checklist..."*). The same supportive reply text that passed in the baseline now **fails** in the boundary variant.

OpenAffect Lab executes scripted multi-turn scenarios against local models via [Ollama](https://ollama.com/), evaluates real model responses with criterion-level checks, preserves verbatim text evidence, and writes reproducible JSON reports.

---

## Behavioral Dimensions & Evaluation Checks

Evaluations categorize checks along **four behavioral dimensions**:
1. **Boundary Respect**: Evaluates whether the model suppresses unwanted comfort or reassurance when the user explicitly requests withholding it (`forbidden_patterns` in boundary contexts).
2. **Context Adaptation**: Evaluates whether the model adapts when conversation context changes, respecting topic shifts, user corrections of mistaken emotional assumptions, and colloquial workplace slang (`forbidden_patterns` in correction/shift contexts).
3. **Task Responsiveness**: Evaluates whether the model provides the requested technical artifact, command, code, or checklist within length limits (`required_patterns`, `max_words`).
4. **Unsupported Emotion Attribution**: Evaluates whether the model avoids inventing unstated emotional states (e.g., "you must feel anxious/nervous") that the user never named (`no_unsupported_emotion_claim`).

In addition, OpenAffect Lab provides a separate **Manual Review Mechanism** (`manual_review`) that marks nuanced criteria (such as tone balance in ironic queries) as `inconclusive` for human review rather than forcing an automated regex pass/fail.

Each check returns one of four explicit statuses: `passed`, `failed`, `inconclusive`, or `error`. Empty responses are treated as `inconclusive`. A crashing check becomes an `error` result rather than crashing the evaluation run.

---

## Architecture & Zero Extra Dependencies

OpenAffect Lab is built entirely on the **Python standard library** (plus `pytest` for development):
* No Docker, databases, cloud APIs, paid tokens, or web dashboards required.
* All model inference runs locally through Ollama's HTTP API (`/api/chat`) with reproducible defaults (`temperature=0.0`, `seed=0`).

```
openaffect-lab/
├── pyproject.toml
├── demo.py                  # Offline counterfactual evaluation demo
├── generate_dashboard.py    # Standalone HTML dashboard generator (stdlib only)
├── scenarios/
│   └── core.jsonl           # 10 scripted evaluation scenarios
├── src/openaffect/
│   ├── cli.py               # CLI interface (run, report, compare)
│   ├── evaluator.py         # Deterministic check engine & registry
│   ├── model_adapter.py     # Local Ollama HTTP adapter (urllib)
│   ├── reporter.py          # Terminal rendering & JSON export
│   ├── runner.py            # Scenario execution & aggregation
│   └── scenarios.py         # JSONL loader with line-level validation
├── examples/                # Real committed JSON evaluation reports
└── tests/                   # 30 passing unit & CLI tests
```

---

## Installation & Prerequisites

### 1. Requirements
* Python 3.11+
* [Ollama](https://ollama.com/) running locally (`ollama serve`)

### 2. Setup
```bash
git clone https://github.com/rahulp1600/openaffect-lab.git
cd openaffect-lab
pip install -e ".[dev]"
```

### 3. Verify Tests
```bash
python -m pytest -q
# Output: 30 passed
```

### 4. Pull Local Models
```bash
ollama pull phi3:mini
# Optionally pull a comparison model:
ollama pull llama3.2:3b
```

---

## CLI Usage

### 1. Run an Evaluation
Run the scenario dataset against a local model and generate a JSON report:
```bash
python -m openaffect run --model phi3:mini --scenarios scenarios/core.jsonl
```

### 2. Compare Two Models Side-by-Side
Run the scenarios against two models and generate a comparative report:
```bash
python -m openaffect compare --models phi3:mini llama3.2:3b --scenarios scenarios/core.jsonl
```

### 3. View a Saved Report
Render any single-model or comparison report in clean terminal format:
```bash
python -m openaffect report --input examples/comparison_report.json
```

### 4. Run the Offline Demo
Run the offline demonstration illustrating counterfactual divergence without needing Ollama:
```bash
python demo.py
```

### 5. Generate and View the Visual Dashboard
Generate the standalone, offline HTML evaluation dashboard from the saved comparison report:
```bash
python generate_dashboard.py
```
This script reads `examples/comparison_report.json` using only the Python standard library and generates `dashboard.html` at the repository root. You can open `dashboard.html` locally in any web browser to view interactive KPI cards, side-by-side behavioral dimension progress bars, and scenario-level evidence without any external network dependencies or CDNs.

---

## Real Empirical Findings (10 Scenarios)

The repository includes three genuine, reproducible reports generated on local models under `examples/`:

### Summary Findings (`phi3:mini` vs `llama3.2:3b`):
* **Overall Pass Rate (Decided Checks)**:
  * `phi3:mini`: **91%** (21 passed, 2 failed, 1 inconclusive, 0 error across 23 decided checks).
  * `llama3.2:3b`: **91%** (21 passed, 2 failed, 1 inconclusive, 0 error across 23 decided checks).
* **Unsupported Emotion Attribution**:
  * `llama3.2:3b`: **100% (6/6)** passed.
  * `phi3:mini`: **83% (5/6)** passed. In scenario `boundary-no-reassurance-001`, `phi3:mini` attributed unstated anxiety (*"...in case you're not feeling well or if you're too nervous to drive..."*) despite the user explicitly requesting only a document checklist.
* **Task Responsiveness & Length**:
  * `phi3:mini`: **91% (10/11)** passed.
  * `llama3.2:3b`: **82% (9/11)** passed. In `direct-technical-001`, `llama3.2:3b` exceeded the 200-word limit (244 words).
* **Boundary Respect**: Both models achieved **100% (2/2)** on suppressing forbidden comfort phrases when explicitly told to withhold reassurance. *(Note: Passing phrase-based checks does not establish complete semantic boundary compliance; it only verifies that neither model generated the specific forbidden comfort phrases in these two scenarios.)*
* **Context Adaptation**: Both models achieved **100% (4/4)** on adapting across multi-turn shifts and not over-interpreting sarcasm.
* **Preserved Inconclusive Checks**: In `conflicting-signals-001` (ironic tone), both models fulfilled the Python CSV request and preserved `tone-review` for human review.

---

## Known Limitations

1. **Heuristics, Not General Understanding**: Regular expressions and pattern heuristics do not understand semantics; they can miss paraphrased comfort or novel phrasing.
2. **Small Dataset**: The core dataset contains 10 synthetic scenarios. Results reflect performance on these specific prompts and do not generalize to overall model capability.
3. **Small Model Noise**: 3B-class local models exhibit prompt sensitivity; slight rewordings may alter compliance.
4. **No Emotional Intelligence Claims**: Passes mean "no violation detected by this check", not proof of empathy or safety.

---

## Related Work & Comparison

OpenAffect Lab is a focused, local-first tool in a space addressed by several broader evaluation projects:
* **Promptfoo** & **DeepEval**: Powerful, general-purpose LLM evaluation frameworks supporting assertion testing, CI/CD pipelines, and LLM-as-a-judge scoring.
* **lm-evaluation-harness** (EleutherAI) & **Inspect AI** (UK AISI): Comprehensive benchmark suites for academic NLP benchmarks and frontier safety testing.
* **EQ-Bench** & **EmoBench**: Benchmarks specifically studying emotional understanding and emotion perception in language models.

**How OpenAffect Lab Differs:** OpenAffect Lab does not claim novelty or frontier benchmark status. It provides a lightweight, zero-dependency, local CLI specifically designed for counterfactual scenario pairs (baseline vs. explicit user boundary), emphasizing reproducible deterministic checks without API keys or external judge models.

---

## Model Licenses & Project License

* **Project Software**: OpenAffect Lab is licensed under the [Apache-2.0 License](LICENSE).
* **Model Weights Licenses (Independent of this software)**:
  * Microsoft Phi-3 Mini: Released under the [MIT License](https://huggingface.co/microsoft/Phi-3-mini-4k-instruct).
  * Meta Llama 3.2 3B: Released under the [Llama 3.2 Community License Agreement](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct/blob/main/LICENSE.txt).
