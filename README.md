# LoanLoop

**AI loan-processing system for mortgage brokers.** LoanLoop takes a loan file from *"the borrower sent a pile of documents"* to *"complete, checked and ready for underwriting"*. It uses a small team of AI agents, a deterministic rules engine, and a human who approves every outward action.

> **Status: early development.** Project setup and engineering guardrails are in place; the product is being built in phases. See [`docs/ROADMAP.md`](docs/ROADMAP.md) for exactly what is done and what isn't. All borrower data in this repo is **synthetic**.

---

## The problem

Loan processors at mortgage brokerages spend a large part of their day on four things:
- sorting and reading borrower documents (paystubs, W-2s, bank statements)
- checking them by hand
- calculating income
- chasing borrowers over email and phone for missing or expired items

Files that reach underwriting incomplete get sent back, closings slip, and the brokerage can only grow by hiring more processors.

## Outcomes we're building for

Every feature has to move one of these metrics. Targets are hypotheses until validated with real processors.

| # | Outcome | Metric |
|---|---|---|
| O1 | Less processor work | Processor minutes per loan file |
| O2 | Faster complete files | Days from application to "file complete" |
| O3 | Fewer underwriting kick-backs | % of files suspended for document issues |
| O4 | Faster borrower response | Hours from document request to upload |
| O5 | More capacity | Files per processor per month |
| O6 | Trust | % of AI-extracted fields a human had to correct |

## How it works

```
Borrower (WhatsApp/Telegram) → OpenClaw ─┐
Processor (chat)             → Hermes   ─┼→ LoanLoop MCP server (scoped tools)
Processor dashboard (Next.js) ───────────┘            │
                     FastAPI + PostgreSQL ⇄ Temporal workflow (one per loan file)
   classify agent (LLM) → extract agent (LLM, JSON schema) → rules engine (pure Python)
   → conditions agent (LLM drafts) → human approval → send
```

**Design principle: use an LLM only where it's actually needed.**
- **LLM agents** read and write language: classify documents, extract fields with evidence, draft messages.
- **Deterministic code** does everything that must be exact: income, DTI, LTV, document expiry, cross-document checks, workflow state, permissions.
- **Humans** approve every message to a borrower. The system never makes credit decisions.

| Component | Role |
|---|---|
| **Temporal** | Durable workflow per loan file: retries, reminders, waits for human approval, survives crashes |
| **LoanLoop MCP server** | The only way external agents touch the system; every tool is scoped (`borrower` / `processor`) |
| **OpenClaw** | Borrower channel: "what do you still need from me?", upload a photo of a document |
| **Hermes** | Processor assistant: stuck files, daily pipeline summary |
| **Evals + Langfuse** | Field-level extraction accuracy on synthetic documents; cost/latency tracing |

## Tech stack

Python 3.12 · FastAPI · PostgreSQL · Temporal · MCP (Python SDK) · Next.js (TypeScript) · Docker · Coolify on a Linux VPS · Langfuse · GitHub Actions.
LLM access goes through a provider-agnostic client (free tiers: Gemini / Groq / OpenRouter / local Ollama).

## Repository layout

```
backend/    FastAPI app: api, agents, llm, rules, workflows, db
mcp/        LoanLoop MCP server (scoped tools for OpenClaw & Hermes)
frontend/   Next.js processor dashboard
evals/      synthetic documents, ground truth, eval runner
infra/      Docker Compose, Coolify config, runbook
docs/       product, architecture, ADRs, roadmap, build log
.claude/    Claude Code setup: rules, skills, subagents, hooks
```

Folders appear as each phase lands.

## Built with AI agents, deliberately

The project is built with Claude Code (plus Codex for independent PR review), with guardrails that make agent output verifiable:

- **`CLAUDE.md` + path-scoped rules** give every agent the architecture, boundaries and conventions.
- **Subagents:** `architect` plans, `test-engineer` writes tests, `code-reviewer` and `security-auditor` review, `verifier` independently confirms "done".
- **Parallel agents** work in separate git worktrees with non-overlapping ownership.
- **Hooks:**
  - block dangerous commands, secrets and real data
  - auto-format and lint every edit
  - stop an agent from declaring "done" while tests fail
- **[`docs/BUILD_LOG.md`](docs/BUILD_LOG.md)** is an honest record of what the agents did, what the human fixed, and what broke.

## Getting started

Setup instructions will be added as the backend, frontend and infra are scaffolded (Phase 1). Prerequisites: Python 3.12+, [`uv`](https://docs.astral.sh/uv/), Node 20+, Docker.

## Data & safety

- Only synthetic borrower documents are used. No real personal data is committed or processed.
- Document text is treated as untrusted input and is tested against prompt injection.
- PII is masked in logs and traces; every state change is audit-logged.
