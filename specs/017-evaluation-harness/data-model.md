# Data Model: M17 — The Evaluation Harness

New tables and columns are added in place, as earlier milestones did. Nothing existing changes
shape, and `agents.config` keeps its contents, so config versions stay the same
([research.md](research.md) §1).

## Run: changed

| Column | Kind | Notes |
|---|---|---|
| `status` | text | adds `waiting_approval`, `over_budget`, `stopped`, `interrupted` |
| `stop_reason` | text, nullable | new: e.g. "model calls: 3 of 3" |
| `harness` | JSON, nullable | new: `{budget, ask_first, default_budget}` as it ran; null for older runs and the village |
| `eval_id` | text, nullable | existing: now also the evaluation an attempt or judge run belongs to |

### Run states

```text
running ⇄ waiting_approval        any approval open ⇄ none open
running | waiting_approval → completed | max_iterations | error    as today
                           → over_budget     a limit reached
                           → stopped         the owner pressed Stop
                           → interrupted     found live when the lab starts
```

The lab's start marks runs `interrupted` where `status` is live and `village_tick IS NULL`. Village
runs are left alone (FR-023).

## Agent: changed

| Column | Kind | Notes |
|---|---|---|
| `harness` | JSON, nullable | new: `{budget, ask_first}`; null means no budget and no ask-first tools |

## Budget (`harness/budget.py`)

| Field | Default | Range |
|---|---|---|
| `model_calls` | 30 | 1–200 |
| `tokens` | 200,000 | 1–2,000,000 |
| `tool_calls` | 30 | 1–200 |
| `seconds` | 600 | 1–3,600 |

All four are required in a budget. Unknown fields are refused.

## Test case: table `eval_cases`

| Column | Kind | Rules |
|---|---|---|
| `case_id` | text, key | `case-<hex>`; an example's is fixed, e.g. `example-react-1`, and is not stored |
| `agent_id` | text | a template id or a saved agent; indexed |
| `name` | text | 1–80 characters, unique per agent ignoring case |
| `prompt` | text | 1–4,000 characters |
| `checks` | JSON | 1–10 checks |
| `approvals` | text | `approve` or `deny`; default `deny` |
| `created_at`, `updated_at` | real | |

At most 50 cases per agent, counting a template's examples. Examples are in code, are listed with
`read_only: true`, and cannot be edited or deleted.

## Check (`evaluation/model.py`, a union on `kind`)

| `kind` | Fields | Passes when |
|---|---|---|
| `contains` | `text` (1–500) | the answer contains the text |
| `not_contains` | `text` (1–500) | the answer does not contain it |
| `matches` | `pattern` (1–500, must compile) | `re.search` finds it in the answer |
| `tool_called` | `tool` (config name) | a tool span of that tool exists |
| `tool_not_called` | `tool` | no tool span of that tool exists |
| `end_state` | `state` (a finished run state) | the run ended in it |
| `max_model_calls` | `limit` (≥ 1) | `totals.llm_calls ≤ limit` |
| `max_tokens` | `limit` (≥ 1) | `tokens_in + tokens_out ≤ limit`; **error** if a model call reported none |
| `judge` | `question` (1–500), `model` (optional) | the judge answers `yes` |

Text checks on a run without an answer read it as empty, so `contains` fails and `not_contains`
passes.

## Evaluation: table `evaluations`

| Column | Kind | Notes |
|---|---|---|
| `eval_id` | text, key | `eval-<hex>` |
| `agent_id` | text | indexed |
| `agent_name` | text | as it was at the start |
| `config_version` | text | |
| `config` | JSON | redacted copy, for the record |
| `harness` | JSON | `{budget, ask_first, default_budget}`; `default_budget` true when the agent had none |
| `model` | JSON | `{provider, model}` |
| `repeats` | integer | 1–10 |
| `cases` | JSON | the chosen cases as they were, each with its `fingerprint` |
| `state` | text | see below |
| `started_at`, `ended_at` | real | |

`fingerprint` is a hash of the prompt, checks and approvals setting. A renamed case keeps its
fingerprint, and any other edit changes it.

### Evaluation states

```text
running → finished      every attempt ended
        → stopped       the owner pressed Stop
        → interrupted   found running when the lab starts
```

Only one may be `running`.

## Attempt: table `eval_attempts`

| Column | Kind | Notes |
|---|---|---|
| `eval_id`, `case_id`, `number` | key | `number` counts from 1 per case |
| `run_id` | text, nullable | null when the run was refused before it started |
| `outcome` | text | `pass`, `fail` or `error`, by the order in FR-004 |
| `reason` | text, nullable | why it failed or errored, redacted |
| `checks` | JSON | per check: `{kind, expected, result, reason, judge_run_id?}` |
| `llm_calls`, `tool_calls`, `tokens`, `wall_ms` | integer, nullable | copied from the run's totals |

A check's `result` is `pass`, `fail` or `error`. Its `reason` says what it expected and what the run
did.

### Results (computed, `evaluation/results.py`)

| Value | Rule |
|---|---|
| A case's pass rate | passed ÷ attempts that are not errors; none when all are errors (FR-004a) |
| Overall pass rate | the same over all attempts pooled, not an average of cases |
| Averages | model calls, tokens and time over attempts with a run; judge runs are not attempts |

### Comparison (computed)

Per case, matched by `case_id`:

| `change` | When |
|---|---|
| `new` / `removed` | in only the later / only the earlier evaluation |
| `changed` | fingerprints differ; rates are shown but not compared |
| `up` / `down` / `same` | same fingerprint, by the pass rates |
| `no_rate` | same fingerprint, and either side has no pass rate |

Both sides also carry their config version, budget and model.

## Approval request (in memory, `harness/approvals.py`)

| Field | Notes |
|---|---|
| `approval_id` | random |
| `run_id`, `agent_name`, `prompt` | to show and to link to the run |
| `tool`, `server`, `arguments` | config name, its server, redacted arguments |
| `asked_at`, `expires_at` | 10 minutes apart |

Its decision is recorded on the approval span ([contracts/interfaces.md](contracts/interfaces.md)).

## Deleting

| Deleted | Also deleted | Kept |
|---|---|---|
| An agent | its cases, evaluations, attempts, and the attempts' and judges' runs and spans | its other runs, as today |
| A case | nothing: evaluations keep their own copy | |
