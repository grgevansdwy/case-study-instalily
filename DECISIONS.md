# Decisions

Append-only. Never edit an old entry. To change a decision, add a new one that replaces it and mark the old one as superseded in the index.

**Constraint questions** (use in the Constraint field):
C1 What must never go wrong? · C2 How fast must it respond? · C3 What volume and cost? · C4 What does the data look like? · C5 Fixed steps or judgment? · C6 How long does a task live? · C7 Who consumes the output?

## Index
| ID | Decision | Status | Date |
|---|---|---|---|
| D1 | Language: Python >= 3.12 | Active | 2026-10-05 |
| D2 | Framework: FastAPI as given, raw `openai` SDK, explicit loop | Active | 2026-10-05 |
| D3 | No database; stateless per request | Active | 2026-10-05 |
| D4 | Two OpenAI model slots, start strong and downgrade on evals | Superseded by D15 | 2026-10-05 |
| D5 | Hosting: local uvicorn booted by the grader | Active | 2026-10-05 |
| D6 | Tool routing: router model over a compact index, plus `load_more_tools` | Active | 2026-10-05 |
| D7 | Control flow: single ReAct agent | Active | 2026-10-05 |
| D8 | Writes execute directly on explicit requests | Active | 2026-10-05 |
| D9 | Ambiguity rule: three checks, then ask; split on look-up-first | Active | 2026-10-05 |
| D10 | Loop budget: 12 turns, 60 s, loop detection | Active | 2026-10-05 |
| D11 | One `run_tool` wrapper; batched calls run sequentially | Active | 2026-10-05 |
| D12 | Pydantic on all tools; semantic checks on writes only | Active | 2026-10-05 |
| D13 | Context: trim tool results, summarize long history | Active | 2026-10-05 |
| D14 | Testing: fake-model unit tests plus live scenario suite | Active | 2026-10-05 |
| D15 | Models: `gpt-4.1-mini` in both slots first, upgrade on eval failure | Active | 2026-10-05 |
| D16 | Router selects at most 15 tools | Active | 2026-10-05 |
| D17 | Follow-up turns: re-lookup; assistant-quoted IDs count as grounded | Active | 2026-10-05 |
| D18 | M1 uses a fixed 12-tool list until the router exists | Active | 2026-10-05 |
| D19 | M1 limit stops return a fixed message built from the log | Active | 2026-10-05 |
| D20 | `tool`-role request messages are sent to the model as labelled user data | Active | 2026-10-05 |
| D21 | Tool schemas go to the Responses API as emitted; no sanitizer | Active | 2026-10-05 |

---

## D1: Language: Python >= 3.12
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Agent
- **Constraint:** C7
- **Options:** Python >= 3.12 as shipped / nothing else is viable
- **Choice:** Python >= 3.12
- **Reason:** The package, its tests and the grader's install step are all Python.
- **Reversible:** Hard; it would mean rewriting the given backend.
- **Revisit when:** Never for this case study.
- **Replaces:** none

---

## D2: Framework: FastAPI as given, raw `openai` SDK, explicit loop
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Agent
- **Constraint:** C5
- **Options:** Raw SDK with a hand-written loop / an agent framework / the SDK's built-in agent helpers
- **Choice:** Raw `openai` SDK with an explicit loop; no new dependency
- **Reason:** The loop is what is graded, so every decision in it should be visible, and `backend/pyproject.toml` is outside the allowed edit set.
- **Reversible:** Easy; the loop is one module.
- **Revisit when:** A named framework feature is needed that would take longer to write than to adopt.
- **Replaces:** none

---

## D3: No database; stateless per request
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Critique
- **Constraint:** C6
- **Options:** Stateless, history from the request / SQLite session store / in-memory session dict
- **Choice:** Stateless
- **Reason:** `ChatRequest.messages` carries the full conversation, and mock state is reset between scenarios, so a store would hold nothing the request does not already have.
- **Reversible:** Easy; a store can be added behind the history-loading step.
- **Revisit when:** The API changes to send only the latest message with a session ID.
- **Replaces:** none

---

## D4: Two OpenAI model slots, start strong and downgrade on evals
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Owner
- **Constraint:** C3
- **Options:** One model for everything / cheap router model plus stronger agent model / a non-OpenAI provider
- **Choice:** `OPENAI_ROUTER_MODEL` (default `gpt-4.1-mini`) for tool selection, `OPENAI_MODEL` for the agent loop, starting one tier above mini. Names are pinned. On a model-access error the loop falls back to `gpt-4.1-mini` once.
- **Reason:** OpenAI is required; routing is an easy step that suits a cheap model, while the loop carries the judgment, and evals decide how far it can be stripped down.
- **Reversible:** Easy; two environment variables.
- **Revisit when:** The live suite passes on mini-for-both, or the grader is confirmed to set `OPENAI_MODEL` itself.
- **Replaces:** none

---

## D5: Hosting: local uvicorn booted by the grader
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Agent
- **Constraint:** C2
- **Options:** As given / nothing else is in scope
- **Choice:** `uvicorn backend.main:app`, started by the grader on a private port
- **Reason:** `SUBMITTING.md` fixes how the server is booted.
- **Reversible:** Not applicable.
- **Revisit when:** Never for this case study.
- **Replaces:** none

---

## D6: Tool routing: router model over a compact index, plus `load_more_tools`
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Critique
- **Constraint:** C4
- **Options:** LLM selector over a name + description index with an escape hatch / embedding retrieval / service-level routing / per-service sub-agents
- **Choice:** One router call picks tool names from the ~3.2k-token index; only those schemas enter the loop. A `load_more_tools` meta-tool lets the agent recover from a bad pick and is not logged in `tool_calls`.
- **Reason:** It replaces ~72k tokens of schemas with ~3.2k, handles multi-step prompts where later tools are not named in the message, and needs no embeddings or new dependency.
- **Reversible:** Easy; the selector is one function returning a list of names.
- **Revisit when:** Evals show the router missing required tools often, or the extra call dominates latency.
- **Replaces:** none

---

## D7: Control flow: single ReAct agent
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Critique
- **Constraint:** C5
- **Options:** Single ReAct agent / one agent per service under an orchestrator / composite task-shaped tools
- **Choice:** Single ReAct agent over the registered tools
- **Reason:** The next step depends on results; cross-service joins are a core scenario type; the scorer checks for registered tool names, which composite tools would hide; and a per-service agent still needs routing inside GitHub's 86 tools.
- **Reversible:** Moderate; sub-agents could wrap the same wrapper and loop.
- **Revisit when:** A single context cannot hold a scenario's material, or evals fail on long cross-service plans.
- **Replaces:** none

---

## D8: Writes execute directly on explicit requests
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Critique
- **Constraint:** C1
- **Options:** Execute and ask only when ambiguous / confirm destructive actions / confirm every write
- **Choice:** Execute directly. Safety comes from code gates: IDs and recipients must be grounded in a tool result or the user's message, bulk actions must be named by the user, and the final answer is checked against the log.
- **Reason:** The grader sends one request and then checks `tool_calls` and `/state`, so a confirmation turn would fail the scenario.
- **Reversible:** Easy; an approval gate can sit in the wrapper.
- **Revisit when:** The system is used by real users, where external sends and deletes should need approval.
- **Replaces:** none

---

## D9: Ambiguity rule: three checks, then ask; split on look-up-first
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Critique
- **Constraint:** C1
- **Options:** Always ask with zero tool calls / always look up first, then ask with options / split by whether the prompt gives a name to search for
- **Choice:** A request is ambiguous when a required slot has no single value after: stated by the user, one lookup returns exactly one match, or a safe default exists. Zero matches is "not found", not ambiguity. Ask immediately when there is no name to search for; look up first when there is one. Recipients, content, delete targets and project or repo never get a default. A person is resolved in the service where the action happens.
- **Reason:** It matches the README's examples and limits reads to cases that can actually resolve something.
- **Reversible:** Easy; it lives in the system prompt.
- **Revisit when:** The grader fails ambiguous scenarios because a read was made before asking.
- **Replaces:** none

---

## D10: Loop budget: 12 turns, 60 s, loop detection
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Critique
- **Constraint:** C2
- **Options:** 8 turns / 30 s; 12 turns / 60 s; 20 turns / 120 s
- **Choice:** 12 turns and 60 s, an identical call blocked after 2 occurrences, and an honest partial answer when a limit is hit
- **Reason:** It covers a 5-6 step plan with retries while staying under a likely client timeout; a timed-out request scores nothing, a partial answer can still be honest.
- **Reversible:** Easy; two constants.
- **Revisit when:** The grader's timeout is known, or a legitimate scenario needs more turns.
- **Replaces:** none

---

## D11: One `run_tool` wrapper; batched calls run sequentially
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Owner
- **Constraint:** C1
- **Options:** One shared wrapper / per-service handling; sequential / concurrent execution of a batch
- **Choice:** Every call goes through `run_tool`: drop nulls for non-nullable optionals, validate, run semantic checks for writes, invoke, catch, log, return a trimmed result or a structured error `{error, detail, retryable}`. Calls in one batch run in the order given. Recovery: bad arguments get one corrected retry; not found gets one alternative lookup then a report; an unexpected error on a read gets one retry then goes to the user; an unexpected error on a write gets a verifying read before any retry; a failed dependency stops the dependent steps.
- **Reason:** One place guarantees the log is complete and errors are uniform; sequential order keeps the log deterministic and in-process tools gain nothing from concurrency.
- **Reversible:** Easy for ordering; the wrapper itself should stay.
- **Revisit when:** Tools become real network calls, where concurrency and timeouts matter.
- **Replaces:** none

---

## D12: Pydantic on all tools; semantic checks on writes only
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Owner
- **Constraint:** C1
- **Options:** Shape checks only / semantic checks on every tool / semantic checks on write and sensitive tools
- **Choice:** Argument and result shape validated for every tool through `ToolSpec.invoke`. Semantic checks only for write and sensitive tools, identified by a hand-reviewed read / write / destructive table.
- **Reason:** Shape validation is already built in; a read result is the ground truth with nothing to check it against, while a wrong write changes state.
- **Reversible:** Easy; checks are per-class functions in the wrapper.
- **Revisit when:** A read tool turns out to need argument sanity checks to avoid wasted calls.
- **Replaces:** none

---

## D13: Context: trim tool results, summarize long history
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Owner
- **Constraint:** C4
- **Options:** Full results and full history / trim results only / trim results and summarize history
- **Choice:** Trim tool results before they re-enter the model (the full result always goes to `tool_calls`). Past a size threshold, summarize older messages with the router model and keep the last N verbatim.
- **Reason:** Large raw results degrade tool selection and burn tokens; summarization guards against long conversations even though the graded scenarios are short.
- **Reversible:** Easy; both are isolated steps.
- **Revisit when:** A long-history test exists to set the threshold and N, currently guessed at ~50k tokens and 6 messages.
- **Replaces:** none

---

## D14: Testing: fake-model unit tests plus live scenario suite
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Critique
- **Constraint:** C1
- **Options:** Live scenarios only / fake-model unit tests only / both
- **Choice:** Both, in stdlib `unittest`. Scripted fake-model tests cover the code rules and must pass 100%. A live suite of 20-30 scenarios is skipped without `OPENAI_API_KEY`; each case runs 3 times when comparing models, once otherwise.
- **Reason:** Hard rules need deterministic tests, and routing and stopping behaviour can only be checked against the real model.
- **Reversible:** Easy.
- **Revisit when:** The live suite becomes too slow or costly to run per change.
- **Replaces:** none

---

## D15: Models: `gpt-4.1-mini` in both slots first, upgrade on eval failure
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Owner
- **Constraint:** C3
- **Options:** Stronger agent model first, then downgrade (D4) / `gpt-4.1-mini` in both slots first, then upgrade if needed / one hard-coded model with no slots
- **Choice:** Keep the two slots from D4 (`OPENAI_MODEL` for the agent loop, `OPENAI_ROUTER_MODEL` for tool selection), both set to `gpt-4.1-mini` to start. Upgrade the agent slot only if the live suite fails on mini. With both slots on mini, D4's fall-back-to-mini rule is not needed.
- **Reason:** Mini is the package default and the model the grader most likely runs, so passing on it is the result that counts; the slots keep an upgrade to a one-variable change.
- **Reversible:** Easy; one environment variable.
- **Revisit when:** The live suite's pass rate on mini is below target after prompt and routing fixes.
- **Replaces:** D4

---

## D16: Router selects at most 15 tools
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Owner
- **Constraint:** C4
- **Options:** 10 / 15 / 20
- **Choice:** 15 from the router; `load_more_tools` may raise the total to 25 within a turn.
- **Reason:** Enough for a three-service plan with lookups and writes, while staying within the range where tool selection stays accurate.
- **Reversible:** Easy; one constant.
- **Revisit when:** Evals show required tools being cut by the cap, or selection accuracy dropping at 15.
- **Replaces:** none

---

## D17: Follow-up turns: re-lookup; assistant-quoted IDs count as grounded
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Critique
- **Constraint:** C6
- **Options:** Look the resource up again on a follow-up turn / return `tool` messages in the response so results carry forward
- **Choice:** Re-lookup. The grounding gate accepts a value that appears in a tool result from this turn or anywhere in the conversation text, including earlier assistant messages.
- **Reason:** Only message text survives between requests (D3); re-lookup uses fresh data and adds no extra messages the grader may not expect, and the widening stops the gate blocking an ID the agent itself showed the user.
- **Reversible:** Easy.
- **Revisit when:** Multi-turn evals show the extra read causing failures.
- **Replaces:** none

---

## D18: M1 uses a fixed 12-tool list until the router exists
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Agent
- **Constraint:** C4
- **Options:** All 191 schemas for now / one service / a fixed small list spanning both name casings
- **Choice:** `FIXED_TOOLS` in `helpers/loop.py`: the 10 Slack tools plus `GMAIL_FETCH_EMAILS` and `GOOGLECALENDAR_GET_CURRENT_DATE_TIME`.
- **Reason:** It keeps never-go-wrong 5 true from the first slice, covers the M1 Slack acceptance check, and exercises both lowercase and uppercase registered names against the live model.
- **Reversible:** Easy; the list is replaced by the router result in M2.
- **Revisit when:** M2 lands. The list should then be deleted, not kept as a fallback.
- **Replaces:** none

---

## D19: M1 limit stops return a fixed message built from the log
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Agent
- **Constraint:** C1
- **Options:** One last no-tools model call for a summary / a fixed message built in code from `tool_calls`
- **Choice:** Fixed message: the reason (step limit, time limit, or provider error after tools ran), the names of calls that completed and that failed, and "The task may be incomplete."
- **Reason:** It cannot claim success the log does not show, and it needs no extra model call when time is already spent. The model-written summary is M3 scope (spec 4.7 step 5).
- **Reversible:** Easy; one function.
- **Revisit when:** M3 adds the limit-stop summary call; the fixed message stays as the fallback when under 5 s remain.
- **Replaces:** none

---

## D20: `tool`-role request messages are sent to the model as labelled user data
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Agent
- **Constraint:** C1
- **Options:** Drop them / pass them as system messages / pass them as user content wrapped in `<tool_message trust="data">`
- **Choice:** Wrap and send as user content. They are left out of `conversation_text`. The response still returns the caller's messages unchanged.
- **Reason:** `ChatMessage` allows a `tool` role but the Responses API input has no bare equivalent, and tool output must never gain instruction authority (never-go-wrong 4).
- **Reversible:** Easy; one function.
- **Revisit when:** The grader is seen sending `tool` messages whose content a follow-up turn must act on.
- **Replaces:** none

---

## D21: Tool schemas go to the Responses API as emitted; no sanitizer
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Agent
- **Constraint:** C4
- **Options:** Send `get_openai_tools()` output unchanged / strip `default`, `title` and similar keys from a copy in `helpers/`
- **Choice:** Send unchanged.
- **Reason:** Checked live on 2026-10-05: `gpt-4.1-mini` accepted all 191 strict schemas (sent in batches of 24) with zero rejections, so a sanitizer would be code with no purpose.
- **Reversible:** Easy; a copy-and-strip step can sit in front of the model call.
- **Revisit when:** `OPENAI_MODEL` changes, or the API starts returning a 400 on a tool schema.
- **Replaces:** none

---

<!-- Copy the block above for each new decision. -->
