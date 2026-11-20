---
name: add-eval
description: Add synthetic documents with ground-truth labels to the LLM eval set, run evals, and report field-level accuracy. Use when changing an agent, prompt, model, or when an extraction bug is found.
---

# Add eval cases and run evals

Target: $ARGUMENTS

1. **Synthetic only.** Generate documents with `evals/generate_synthetic.py` (or extend it). Never use real borrower data.
2. Each case lives in `evals/data/synthetic/<doc_type>/<case_id>/` with:
   - the document (PDF/image/text)
   - `expected.json`: ground-truth fields, matching the agent's output schema
   - `meta.json`: what makes the case hard (e.g. "blurry scan", "YTD and current mixed", "prompt-injection text in footer")
3. Cover the hard cases, not just clean ones: low-quality scans, unusual layouts, missing fields, conflicting values, **adversarial/injection text**.
4. If this was a bug: add the failing case first and confirm the eval catches it.
5. Run `cd evals && uv run python run_evals.py` and report:
   - field-level accuracy per document type, before → after
   - worst fields and failing case IDs
   - cost and latency per document
6. A regression blocks the change unless the human explicitly accepts it. Log the result with `/build-log`.
