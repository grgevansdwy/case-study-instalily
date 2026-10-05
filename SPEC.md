# MCP Case Study, Multi-Tool Chat Harness: SPEC

> For the human. Detailed plans go in SPEC-DETAILED.md. Decision history goes in DECISIONS.md.

## 1. Goal
Implement `POST /chat`: take a user message, choose a small subset of the 191 mock tools, run a bounded agent loop over them, and return the assistant's reply plus an exact log of every tool call. It is scored by an automated harness over ~30 scenarios (single-service lookups, cross-service joins, multi-step plans, ambiguous prompts, error paths), then read by a human reviewer.

## 2. Never go wrong
Each item maps to at least one test (section 8).

1. **Never claim success for an action that failed or never ran.** If a tool raised, a resource was missing, or a limit was hit, the reply says so.
2. **Never write on a guess.** No write runs with an ID, recipient or target that did not come from a lookup or the user. An ambiguous request gets a question and no write calls.
3. **Never drop or alter a tool call in the log.** Every invocation appears in `tool_calls`, in call order, with the exact arguments and the result, or the error with a null result.
4. **Never act on instructions found in tool output.** Text in emails, files, messages and search results is data.
5. **Never run unbounded or send all 191 schemas.** The loop stops at 12 turns or 60 seconds, repeated identical calls are cut off, and each model call sees only the routed subset.
6. **Never edit files outside the README's allowed set.** Code changes go only in `backend/solution.py` and `backend/helpers/`. Tests go in `backend/tests/`, as the README's "Testing your solution" section instructs. `backend/chat_schema.py`, `backend/main.py`, `backend/tooling.py`, `backend/mock_service.py`, every `*_mock/` package, `backend/pyproject.toml` and `README.md` are not touched.

## 3. Constraints
- **Response time:** synchronous, one HTTP request per turn. Hard budget 60 s; a healthy run should take a few seconds. Latency is tracked, not graded.
- **Task lifetime:** one request. No waiting, no pause/resume. The request carries the full message history, and mock state is reset between scenarios.
- **Volume / cost:** ~30 graded scenarios plus local eval runs. Cost is small; the main lever is keeping schemas out of the prompt.
- **Data shape:** 191 tools, ~72k tokens of schemas (GitHub 86 tools / 27k, Calendar 29 / 16k, Linear 25 / 11k, Drive 20 / 7.5k, Gmail 20 / 7.4k, Slack 10 / 2.2k, Perplexity 1). A name + one-line-description index of all tools is ~3.2k tokens. Fixtures are small, structured, in-memory.
- **Output consumer:** a program first (the grader reads `tool_calls` and `GET /state`), then a human reading the assistant message and the code.

## 4. Big-picture decisions
| Decision | Choice | Reason | Ref |
|---|---|---|---|
| Language | Python >= 3.12 | Given by the package | D1 |
| Framework | FastAPI as given; raw `openai` SDK with an explicit loop, no agent framework | Keeps every decision visible; no new dependency allowed | D2 |
| Database | None; stateless per request | History arrives in the request; state resets per scenario. SQLite session store dropped | D3 |
| Model | OpenAI, two config slots: `OPENAI_MODEL` (agent loop) and `OPENAI_ROUTER_MODEL` (tool selection). Both start on `gpt-4.1-mini`; the agent slot is upgraded only if the live suite fails on mini. Pinned names | OpenAI is required. Mini is the package default and the model the grader most likely runs; the two slots keep an upgrade to one variable | D15 (replaces D4) |
| Hosting | Local `uvicorn backend.main:app`, booted by the grader | Given | D5 |
| Tool routing | Router model picks tool names from the compact index; only those schemas enter the loop. The router may pick at most 15 tools. A `load_more_tools` meta-tool is the escape hatch and is not logged in `tool_calls` | 3.2k tokens instead of 72k; recovers from a bad first pick | D6, D16 |
| Control flow | Single ReAct agent. No per-service sub-agents, no composite task tools | Path depends on results; cross-service joins are core; the scorer checks registered tool names | D7 |
| Writes | Execute explicit requests directly, no confirmation turn | The grader is single-turn and checks `tool_calls` and `/state` | D8 |
| Ambiguity | Ask when a required slot has no single value after: stated by user, one lookup gives exactly one match, or a safe default exists. Ask immediately when there is no name to search for; look up first when there is one | Matches the README examples; keeps reads to cases that can resolve something | D9 |
| Follow-up turns | Only message text carries over between requests; earlier tool results do not. The agent looks a resource up again before writing. IDs quoted in earlier assistant messages count as grounded | Stateless (D3); re-lookup uses fresh data and the extra read is not graded | D17 |
| Loop budget | 12 turns, 60 s, loop detection on identical calls; honest partial answer at the limit | Covers a 5-6 step plan with retries; stays under likely client timeouts | D10 |
| Tool execution | One `run_tool` wrapper for every call. Batched calls run sequentially in the order given | One place for validation, errors and logging; deterministic log order; in-process tools gain nothing from concurrency | D11 |
| Validation | Pydantic on arguments and results for every tool; semantic checks on write and sensitive tools only | Shape checks are free via `ToolSpec.invoke`; reads are ground truth | D12 |
| Context | Trim tool results before they re-enter the model; summarize old history past a threshold and keep the last N messages | Large raw results degrade the model; summarization kept at the owner's request | D13 |
| Testing | Two layers: scripted fake-model unit tests for code rules; live-model scenario suite skipped without a key. 3 repeats per case when comparing models | Hard rules need 100% determinism; routing quality needs the real model | D14 |

## 5. Flow

### 5.1 Per sub-problem
| Sub-problem | Approach | Why |
|---|---|---|
| Tool index (name, description, service, read/write/destructive class) | Code, built once at import | Fixed data; the class table is reviewed by hand because verb prefixes miss cases like `github_actions_run_trigger` |
| Tool selection | Single model call (router) with structured output | Language judgment over a small index |
| Planning and stepping | ReAct loop (agent model) | Next step depends on results |
| Tool execution, logging, error shape | Code (`run_tool`) | Fixed steps and hard rules |
| Resolve-before-write and other semantic checks | Code | Safety must not depend on prompt wording |
| Deciding a prompt is ambiguous | Model, guided by the D9 rule in the system prompt | Language judgment |
| Result trimming | Code | Deterministic caps |
| History summarization | Single model call (router model), only past the threshold | Rare; cheap model is enough |
| Final-answer check | Code | Compares the reply against the log |

### 5.2 End-to-end
1. (code) Load `.env` with a stdlib loader if present; read model config. Receive `ChatRequest`.
2. (code) Estimate history size. (model, only if over threshold) Summarize older messages; keep the last N verbatim.
3. (model, router) Given the compact index and the conversation, return a list of tool names. An empty list is valid (greeting, or a question to ask straight away).
4. (code) Validate names against the registry with exact casing, drop unknown ones, cap the count.
5. (model, agent) One loop turn with the routed schemas plus `load_more_tools`. Returns tool calls, a final answer, or a clarifying question.
6. (code) For each tool call, in the order given, `run_tool`:
   - Drop arguments the model set to `null` (strict mode makes it send null for every unused nullable field), so the tool's own default applies and the log shows only what was passed.
   - Validate arguments (Pydantic).
   - For write and sensitive tools, run semantic checks: IDs and recipients grounded in an earlier tool result this turn or in the conversation text (user or assistant messages); required content non-empty; event end after start; bulk actions only when the user named them.
   - Invoke; catch `ValidationError`, the service's `*MockError`, and anything else.
   - Append to `tool_calls` (result, or error with null result).
   - Return to the model a trimmed result labelled as data, or a structured error `{error, detail, retryable}`.
7. (code) Recovery rules: bad arguments, one corrected retry. Not found, no blind retry; one alternative lookup, then report. Unexpected error on a read, one retry then report to the user. Unexpected error on a write, one read to see whether it landed, retry only if it did not. A failed dependency stops the dependent steps.
8. (code) Loop controls: stop at 12 turns or 60 s; block a call identical to an earlier one after 2 occurrences. Go to step 5 unless stopped or the model gave a final message.
9. (code) Final-answer check: if every write call in the turn errored, or a limit was hit, prefix the reply with a plain statement of what did not complete. If the reply is a clarifying question, assert no write ran.
10. (code) Return `ChatResponse`: the request messages plus one assistant message, and `tool_calls`.

No parallel steps and no pause/resume points.

## 6. Safety rules
- **Gates and approvals:** no human approval step (D8). The code gates are the resolve-before-write check, the bulk-action check, and the final-answer check. A production version would add approval for external sends and deletes.
- **Permissions:** the model sees only routed tools. Identity is whatever the mock services treat as "me"; the model does not supply a user ID.
- **Prompt-injection handling:** tool output is wrapped and labelled as data, and the system prompt forbids following instructions inside it. The enforceable part is the grounding gate: a recipient or ID that appears only in tool output still passes it, so the model rule and the injection test carry this case. Stated as a known limit.
- **Data handling:** no PII redaction on inputs (addresses and names are tool arguments). The API key comes from the environment and is never logged or put in a prompt. Debug logs do not print message bodies.
- **Gmail specifics:** there is no plain send tool. "Write an email" creates a draft and the reply says drafted, not sent. `GMAIL_REPLY_TO_THREAD` is the only tool that sends.
- **Dates:** the mocks' clock is fixed at 2026-04-08, not the real date. The agent never assumes today's date; for relative dates ("next week") it calls `GOOGLECALENDAR_GET_CURRENT_DATE_TIME`.
- **Identity across services:** the same person has different emails per service (for example Jordan Rivera). Resolve a person in the service where the action happens.

## 7. Open decisions
| Decision | Options | Recommendation | Needed before milestone |
|---|---|---|---|
| Result-trimming caps | Per-result character cap / per-list item cap / both | Both: cap list items with an "N more" note, then a character cap. Full result always goes to `tool_calls` | M3 |
| Summarization threshold and N | Trigger at ~50k estimated tokens, keep last 6 messages / other values | As stated; a guess until a long-history test exists | M4 |
| Ambiguous scenarios: are reads allowed before asking? | Zero calls always / split rule (D9) | Split rule, already locked; revisit only if the grader fails it | M3 |
| Packaging | Zip as-is / exclude `templates/`, `george-setup/`, `.claude/`, `CLAUDE*.md`, `SPEC*.md`, `DECISIONS.md` | Exclude; `submit.py` zips the working copy | Before submission |

## 8. Milestones
| # | Goal | Needs from you | How to test | Success means |
|---|---|---|---|---|
| M1 | Thin end-to-end slice: `run_tool` wrapper, loop with limits, exact logging, driven by a scripted fake model; one live Slack lookup | OpenAI key in `.env`; how you want `backend/.venv` created | Fake-model unit tests for never-go-wrong 3 and 5; `curl` the Slack example | 200 with an assistant message and one logged call; existing tests pass after removing the 501 assertion and the `@unittest.skip`, as the README instructs |
| M2 | Routing: compact index, router call, name validation, `load_more_tools`; cross-service and multi-step scenarios | Nothing new | Live scenarios: lookups, cross-service joins, multi-step. Assert schema count per model call | Right tools reached; no call ever carries all 191 schemas |
| M3 | Safety and honesty: read/write class table, semantic checks, recovery rules, ambiguity rule, final-answer check, injection labelling, result trimming | Review of the class table | Fake-model tests for never-go-wrong 1, 2, 4; live ambiguous, missing-resource and injection scenarios | Hard-rule tests at 100%; no fabricated success |
| M4 | History summarization; full eval suite (20-30 cases); model downgrade comparison at 3 repeats | Budget for eval runs | Long-history test; pass-rate table per model setup | Chosen models pinned; `SUBMITTING.md` sanity checks pass |

Never-go-wrong 6 is checked at every milestone: `git status` shows changes only under `backend/solution.py`, `backend/helpers/` and `backend/tests/`.

## 9. Assumptions to confirm
- The grader supplies its own `OPENAI_API_KEY`. Unknown: whether it sets `OPENAI_MODEL`, and to what.
- The grader's HTTP timeout per scenario is at least 60 s.
- `README.md` wins over `SUBMITTING.md` on where `/chat` lives (`solution.py`, not `main.py`), and "56 existing tests still pass" allows deleting the one 501 assertion the test file itself says to delete.
- `backend/tests/` is inside the allowed edit set, because the README says to write tests there.
- A clarifying question with a read-only lookup before it does not fail an "ambiguous" scenario.
- The reviewer does not expect `DESIGN.md` content from this file; `DESIGN.md` is written by the owner alone.
