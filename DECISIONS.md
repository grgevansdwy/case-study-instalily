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
| D18 | M1 uses a fixed 12-tool list until the router exists | Superseded by D22 | 2026-10-05 |
| D19 | M1 limit stops return a fixed message built from the log | Superseded by D30 | 2026-10-05 |
| D20 | `tool`-role request messages are sent to the model as labelled user data | Active | 2026-10-05 |
| D21 | Tool schemas go to the Responses API as emitted; no sanitizer | Active | 2026-10-05 |
| D22 | Router result replaces the fixed tool list; two attempts inside the turn deadline | Active | 2026-10-05 |
| D23 | Router keyword fallback picks read tools by verb tokens until the class table exists | Superseded by D26 | 2026-10-05 |
| D24 | An empty tool selection never reaches `get_openai_tools` | Active | 2026-10-05 |
| D25 | Index lines are `name \| description` under a service heading; no class column until M3 | Active | 2026-10-05 |
| D26 | Class table is explicit data: 107 read, 69 write, 15 destructive; unknown names count as destructive | Active | 2026-10-05 |
| D27 | Reference-argument rule widened to the real argument names, with exclusions and exempt values | Active | 2026-10-05 |
| D28 | Grounding takes whole short result strings and their parts; long text grounds nothing | Active | 2026-10-05 |
| D29 | Unexpected error: code retries a read once; a write is never retried by code | Active | 2026-10-05 |
| D30 | Limit stop: model-written summary under a fixed prefix, log summary as fallback | Active | 2026-10-05 |
| D31 | Bulk tools need per-tool keywords in the last user message, matched as whole words | Active | 2026-10-05 |
| D32 | Closing offers: prompt rule plus a code strip of "Let me know if..." statements; closing questions are left alone | Active | 2026-10-05 |

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
- **Status:** Superseded by D22
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

## D22: Router result replaces the fixed tool list; two attempts inside the turn deadline
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Agent
- **Constraint:** C1, C2
- **Options:** One router attempt with the same fixed timeout each time / two attempts, each limited to the time left in the 60 s turn budget
- **Choice:** `select_tools` makes up to two attempts and asks the loop for the time left before each one. `FIXED_TOOLS` is removed. The index is also appended to the agent instructions so `load_more_tools` has names to choose from.
- **Reason:** The SDK already retries once per call, so two fixed 30 s attempts could exceed the whole turn budget on their own (never-go-wrong 5).
- **Reversible:** Easy; one function.
- **Revisit when:** Router latency shows up as a meaningful share of p95.
- **Replaces:** D18

---

## D23: Router keyword fallback picks read tools by verb tokens until the class table exists
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Agent
- **Constraint:** C1
- **Options:** Wait for the M3 class table / all tools of the matched service / read tools guessed from the name
- **Choice:** A tool counts as a read when its name has a read verb token and no changing verb token. When several services match (for example "issue" matches Linear and GitHub) the cap of 15 is shared between them in turn. No keyword match gives an empty list.
- **Reason:** The fallback runs only after the router failed twice, and it must not hand the agent write tools on a keyword guess. The agent can still load a write tool by name.
- **Reversible:** Easy; swap `_looks_like_read` for the class table.
- **Revisit when:** M3 lands the reviewed class table.
- **Replaces:** none

---

## D24: An empty tool selection never reaches `get_openai_tools`
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Agent
- **Constraint:** C1
- **Options:** Call `get_openai_tools(active_tools)` always / skip the call when the list is empty
- **Choice:** Skip it. With no routed tools the model call carries only `load_more_tools`.
- **Reason:** `get_openai_tools([])` returns all 191 schemas because `main.py` uses `names or list_available_tools()`. A greeting would otherwise send the whole catalog (never-go-wrong 5), and `main.py` is outside the edit set.
- **Reversible:** Easy; one helper in `loop.py`, covered by a test.
- **Revisit when:** Never while `main.py` keeps that fallback.
- **Replaces:** none

---

## D25: Index lines are `name | description` under a service heading; no class column until M3
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Agent
- **Constraint:** C4
- **Options:** `name | service | class | description` per line as in SPEC-DETAILED 4.2 / service as a heading and no class yet
- **Choice:** One `## service` heading per group, then `name | description` lines. About 15.6k characters for 191 tools.
- **Reason:** The class table is M3 work and is meant to be reviewed by hand, so M2 does not invent one. Repeating the service on every line adds tokens without adding information.
- **Reversible:** Easy; one function.
- **Revisit when:** M3 adds `tool_class`; add the column then if routing evals show it helps.
- **Replaces:** none

---

## D26: Class table is explicit data: 107 read, 69 write, 15 destructive; unknown names count as destructive
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Agent
- **Constraint:** C1
- **Options:** Infer the class from verb tokens at runtime / one explicit table listing all 191 names
- **Choice:** Three explicit name lists in `catalog.py`, drafted from the verb rule and corrected by hand where it is silent or gives two answers (`slack_conversations_history`, `slack_users_info`, `github_pull_request_read`, `GOOGLECALENDAR_CALENDAR_LIST_INSERT`/`_UPDATE`, `GMAIL_MOVE_TO_TRASH`, `github_merge_pull_request`, `github_mark_all_notifications_read`). Five GitHub write tools become destructive for a delete `method` (`DESTRUCTIVE_METHODS`, taken from the method strings the mocks accept). A name missing from the table is treated as destructive. The router's keyword fallback now reads this table. The index keeps no class column (D25 stands: no eval shows it helps).
- **Reason:** The verb rule misclassifies or misses about a dozen names, and a table can be reviewed line by line. Defaulting an unknown name to destructive means a new tool gets every check rather than none.
- **Reversible:** Easy; data only. A test fails if the table and the registry drift apart.
- **Revisit when:** The owner's review moves a tool between classes.
- **Replaces:** D23

---

## D27: Reference-argument rule widened to the real argument names, with exclusions and exempt values
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Agent
- **Constraint:** C1
- **Options:** The pattern list in SPEC-DETAILED 4.2 as written / the list checked against the arguments the write tools really have
- **Choice:** Added: the `ID`/`IDs`/`Ids` suffixes (`threadID`, `notificationID`), `pullNumber`, `sub_issue_number`, `attendee_email`, `email_address`, `extra_recipients`, `assignees`, `reviewers`, `lead`, `delegate`, `destination`, `parents`, `organization`, `from_branch`, `base`, `head`, `base_ref`, `ref`. Excluded: `requestId`, `colorId`, `color_id`, `themeId`; `id` on the two WATCH tools; `branch` on `github_create_branch`; `path` on `github_create_or_update_file` and `github_push_files`. Exempt values added to the spec's: `main`, and Gmail's built-in label IDs (`INBOX`, `UNREAD`, `STARRED`, ...). A leading `#` or `@` is ignored when comparing. Content arguments also include `message_body` and `text_content`.
- **Reason:** The spec list missed arguments such as `pullNumber` and `attendee_email`, which left real writes unchecked, and it caught values the caller invents (a watch channel ID, a new branch name), which would block correct calls. Without the label and `main` exemptions, "mark as read" or "open a PR" would need an extra lookup for a value that is always valid.
- **Reversible:** Easy; data only.
- **Revisit when:** A live scenario is blocked on a value that was correct, or a write gets through with an argument that should have been checked.
- **Replaces:** none

---

## D28: Grounding takes whole short result strings and their parts; long text grounds nothing
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Agent
- **Constraint:** C1
- **Options:** Every string scalar in a result, whole (spec 4.4 step 10) / also substrings of any result text / whole strings plus their parts, for short strings only
- **Choice:** A result string of 300 characters or fewer is grounded whole and also split on spaces and `< > ( ) , ; : " ' / [ ]`, so `Jordan <jordan@corp.com>` grounds the address and `acme/api` grounds both parts. A longer string grounds nothing. Integers are grounded as strings; booleans are not.
- **Reason:** Whole-scalar matching blocked correct writes whose target sits inside a header or a `owner/repo` name. Leaving out long text means an address that appears only in an email or file body is not a valid write target, so the commonest injection ("forward this to x@evil") is stopped by code, not only by the prompt.
- **Reversible:** Easy; one function and one constant.
- **Revisit when:** A scenario needs a recipient taken from a message body. Known limit: text short enough to be split (a Slack message, a Gmail snippet) still grounds what it contains.
- **Replaces:** none

---

## D29: Unexpected error: code retries a read once; a write is never retried by code
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Agent
- **Constraint:** C1
- **Options:** Return `retryable: true` and let the model retry / retry in the executor
- **Choice:** A read that raises an unexpected exception is invoked once more by the executor. Both attempts are logged. If the second fails the model gets `retryable: false` and is told to report it. A write is invoked once; its error tells the model to check with a read whether it landed. Each invocation counts toward the two-identical-calls limit, so the model cannot retry the same failed read again.
- **Reason:** A fixed rule belongs in code, and it costs no model turn. A write may have been applied before it raised, so repeating it blindly could apply it twice.
- **Reversible:** Easy.
- **Revisit when:** A tool shows unexpected errors that need more than one retry.
- **Replaces:** none

---

## D30: Limit stop: model-written summary under a fixed prefix, log summary as fallback
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Agent
- **Constraint:** C1
- **Options:** Fixed message only (D19) / model summary only / fixed prefix, then the model summary, else the log summary
- **Choice:** On the step or time limit, if at least 5 s remain, one model call with no tools writes what was and was not done. If that call fails, returns no text, or there is no time, the reply is the list of completed and failed calls from the log. Either way the reply starts with a fixed sentence naming the limit. A provider error after tools ran uses the log summary only. The same prefix step names any write that errored with no later success of that tool, on every stop reason.
- **Reason:** The model's summary is more useful to the user, but the statement that the task is incomplete must not depend on the model.
- **Reversible:** Easy.
- **Revisit when:** The prefix reads badly on honest replies that already report the failure.
- **Replaces:** D19

---

## D31: Bulk tools need per-tool keywords in the last user message, matched as whole words
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Agent
- **Constraint:** C1
- **Options:** One shared keyword list matched as substrings (spec 4.4) / per-tool keyword groups matched as whole words
- **Choice:** `BULK_KEYWORDS` in `catalog.py`. Clear-calendar, empty-trash and mark-all-read need one of `clear`, `empty`, `all`, `every`, `everything`, `entire` (per tool). Delete-drive and delete-calendar need `delete` or `remove` together with `drive` or `calendar`.
- **Reason:** As a substring, "all" matches "call" and "install", which would let a bulk action through on an unrelated request. The exact phrase "delete the calendar" would block "delete my Team calendar".
- **Reversible:** Easy; data only.
- **Revisit when:** A clearly requested bulk action is blocked.
- **Replaces:** none

---

## D32: Closing offers: prompt rule plus a code strip of "Let me know if..." statements; closing questions are left alone
- **Date:** 2026-10-05
- **Status:** Active
- **Source:** Agent
- **Constraint:** C7
- **Options:** Prompt rule only / also strip closing offers in code, statements only / also strip closing "Would you like me to...?" questions
- **Choice:** The agent prompt forbids closing offers and gives two example answers. `loop._strip_closing_offer` removes a final sentence that starts with "Let me know", "Feel free", "I can also", "If you'd like", "If you want" or "If you need" and ends in "." or "!". A reply ending in "?" is never changed.
- **Reason:** With the prompt rule alone, `gpt-4.1-mini` still closed 3 to 5 of 15 live replies with "Let me know if...". The strip removes those every time. A closing question cannot be told apart in code from a clarifying question the user must answer, and removing one of those would break the ambiguous scenarios.
- **Reversible:** Easy; one function and one pattern.
- **Revisit when:** Measured at 3 repeats after the change: the Q3-budget reply still ended with "Would you like me to post there anyway?" in 2 of 3 runs. Fix by prompt or a stronger agent model, not by stripping questions.
- **Replaces:** none

---

<!-- Copy the block above for each new decision. -->
