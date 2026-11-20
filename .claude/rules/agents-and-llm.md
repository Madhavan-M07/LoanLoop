---
paths:
  - "backend/app/agents/**"
  - "backend/app/llm/**"
  - "backend/app/rules/**"
  - "prompts/**"
  - "evals/**"
---

# LLM agents vs deterministic rules

**Decide first: does this need an LLM?** Use an LLM only for understanding unstructured text (classify, extract, summarize, draft). Anything that computes, compares, decides, or must be exactly reproducible goes in `app/rules/` as pure Python. Pure means: no I/O, no LLM, 100% unit-tested.

Every LLM agent must have:
1. **One job**, a clear name, and an input and output Pydantic schema. Use structured output; no free-text parsing.
2. **A versioned prompt** in `prompts/<agent>/v<N>.md`. Changing a prompt means a new version plus an eval run.
3. **Validation after the call:** schema check, then sanity checks (e.g. pay date not in the future, gross ≥ net). On failure: one retry with the error fed back, then mark `needs_human_review`. Never guess.
4. **A confidence/evidence field.** Extracted values carry the source snippet or page they came from.
5. **Langfuse tracing:** agent name, prompt version, model, tokens, latency, cost.
6. **Provider-agnostic calls** through `app/llm/client.py`. Never import a vendor SDK inside an agent.
7. **Untrusted input:** document text goes in a delimited data section of the prompt, never mixed into instructions.

Eval gate: any change in `agents/`, `prompts/` or `llm/` requires `/add-eval` cases if behavior changed, and an eval run showing no field-level accuracy regression.
