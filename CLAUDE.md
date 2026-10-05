# MCP Case Study: Multi-Tool Chat Harness

## WHY: purpose
A take-home case study. A FastAPI server exposes 191 mock tools across seven services (Gmail, Google Calendar, Google Drive, Slack, Linear, GitHub, Perplexity). The work is to implement `POST /chat`: take a user message, pick the right tools, run an orchestration loop, and answer.

An automated harness scores ~30 scenarios against `/chat`, resetting state between each. What matters, in order:
1. **Tool routing**: never send all 191 schemas to the model; choose a subset per turn.
2. **Orchestration loop quality**: multi-step plans, error recovery, knowing when to stop, asking when a prompt is ambiguous, never fabricating success when a tool fails or a resource is missing.

Latency and tool-call count (vs. the minimum a task needs) are tracked but not graded. Full brief: `README.md`. Packaging rules: `SUBMITTING.md`.

## WHAT: codebase map

### Stack
- Python >= 3.12, FastAPI, Pydantic v2, uvicorn, `openai` SDK (>=2.40,<3)
- LLM: OpenAI, via `OPENAI_API_KEY` and `OPENAI_MODEL` (see `.env.example`)
- Tests: stdlib `unittest` with FastAPI `TestClient`
- pnpm workspace + turbo wrap the Python commands. The `frontend` workspace named in `pnpm-workspace.yaml` does not exist in this package.

### Layout
```
backend/
  solution.py     # the chat() handler for POST /chat: implement here
  helpers/        # supporting modules for solution.py: config, llm, executor, loop, prompts
  chat_schema.py  # ChatRequest / ChatResponse / ToolCallLog wire models
  main.py         # FastAPI wiring, combined tool registry, /health /tools /reset /state
  tooling.py      # ToolSpec / ToolDefinition, builds args models and docstrings
  mock_service.py # base class for each service's in-memory state
  *_mock/         # one package per service: state.py (fixtures) + tools.py (tools)
  cli.py          # terminal client for a running server
  tests/          # unittest suite
docs/mcp_tool_definitions.txt  # upstream tool catalog, reference only
submit.py         # zips the working copy and uploads it to the grader
SPEC.md           # locked decisions, flow, milestones (M1 built; M2 routing is next)
SPEC-DETAILED.md  # per-component build spec and milestone plans
DECISIONS.md      # append-only decision records D1-D17
templates/        # blank SPEC / DESIGN / DECISIONS templates from the Claude harness
```

### Key modules
- `backend/solution.py`: `chat(request: ChatRequest) -> ChatResponse`, registered at `POST /chat` by `main.py`. Delegates to `helpers.loop.run_turn`; returns 503 only when the provider fails before any tool ran.
- `backend/helpers/executor.py`: `run_tool()` is the only path to a tool; it logs to `tool_calls`. `helpers/llm.py`: `get_client()` is the seam tests patch with `tests/fakes.ScriptedClient`. Model calls use the OpenAI Responses API.
- `backend/helpers/loop.py`: uses a fixed `FIXED_TOOLS` list until the M2 router replaces it.
- `backend/main.py`: `get_tool_spec(name).invoke(**args)` calls a tool in-process; `get_openai_tools(names)` returns OpenAI strict-mode function schemas for a subset; `list_available_tools()`, `get_tool_catalog()`, `reset_all_mock_state()`.
- `backend/chat_schema.py`: `ToolCallLog` has `name`, `arguments`, `result`, `error`.
- `backend/<service>_mock/tools.py`: tool functions plus the `ToolDefinition` list. Each service raises its own `*MockError(ValueError)` on bad input or a missing resource.

## HOW: working here

### Commands
Run from the repo root.
- Install: `pnpm install` (JS tooling only). The scripts expect a virtualenv at `backend/.venv`; nothing in the repo creates it, so ask the user how they set it up.
- Dev: `pnpm run dev` (uvicorn on http://127.0.0.1:8000 with reload)
- Test (all): `pnpm --filter backend test`, or without pnpm: `./backend/.venv/bin/python -m unittest discover -s backend/tests -t . -v`. One test makes a live model call, so it needs `OPENAI_API_KEY` in `.env`.
- Test (single file): `./backend/.venv/bin/python -m unittest backend.tests.test_slack_mock -v`
- Lint / typecheck: none configured
- Build: none configured
- CLI against a running server: `pnpm run cli -- chat "<prompt>"`, `pnpm run cli -- tools --service slack`, `pnpm run cli -- state`, `pnpm run cli -- reset`

### Conventions
- Implementation goes in `backend/solution.py` and `backend/helpers/` only. Tests go in `backend/tests/`. Ask before editing `main.py`, `tooling.py`, `mock_service.py`, `chat_schema.py` or any `*_mock/` package.
- Ask before adding a dependency. The grader installs `backend/` into a clean virtualenv, so anything new must be in `backend/pyproject.toml`.
- Every tool invoked during a turn must be appended to `ChatResponse.tool_calls` in call order, with the exact arguments passed and the result returned. On failure set `error` to the message and `result` to null. This log is what gets scored.
- Tool-name casing differs by service: Gmail, Google Calendar and Google Drive are UPPERCASE (`GMAIL_FETCH_EMAILS`), while Slack, Linear, GitHub and Perplexity are lowercase (`slack_list_conversations`). Always use the exact registered name from `list_available_tools()`; never normalize case.
- `get_openai_tools()` emits strict-mode schemas where every property is in `required`; the model passes null for unused optionals.
- Helpers import from `backend.main` inside functions, never at module top: `main.py` imports `solution.py` at load, so a top-level import is circular.
- Imports are absolute from the repo root (`from backend.chat_schema import ...`), and every module starts with `from __future__ import annotations`.
- Tests are `unittest.TestCase` classes using `TestClient(app)`; follow `backend/tests/test_solution_example.py`.

### Workflow
- Plan non-trivial work with `/interview`, review with `/review`, tidy up with `/cleanup`, and commit with `/recap`.
- Plans live in `docs/plans/`.
- Before handing work back, the checks in `SUBMITTING.md` ("Sanity check before you send") must pass, including the existing test suite.

### Don't
- Never write or edit `DESIGN.md`. The brief requires it to be the candidate's own work, not AI-generated. Answering questions about the code is fine.
- Never edit `README.md`; the submission must return it unchanged. This applies to `/recap` too.
- Never run `submit.py` without `--zip-only` unless the user explicitly asks: it uploads to the grader.
- Never report a tool action as successful when the tool raised or the resource was not found.
