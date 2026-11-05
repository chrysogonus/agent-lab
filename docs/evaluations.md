# Evaluations and the harness

[← README](../README.md)

The harness is the code around an agent that measures it, limits it, retries for it and asks you
before it acts. It works for the six templates and your saved agents. The village keeps its own
turn checks and scenarios, and none of this applies to its turns.

## Test cases

Pick an agent, then **Evaluate**. A test case is a name, a prompt and up to 10 checks, and an agent
holds up to 50.

| Check | Passes when |
|---|---|
| The answer contains, or does not contain | that text is, or is not, in the answer |
| The answer matches | a regular expression finds a match in the answer |
| This tool was called, or was not | a tool span of that tool exists, or does not |
| The run ended as | the run ended in that state |
| At most this many model calls, or tokens | the run stayed within that number |
| A judge answers yes to | a model answers yes to your question about the answer |

A judge's call is its own traced run. It does not count against the agent's budget or its averages.

**Examples**: each template comes with at least two cases. They are read-only and update with the
lab. A new agent you save from a template starts with its own editable copy, and copying an agent
copies its cases.

## Running an evaluation

Choose the cases, how many times to run each (1 to 10) and a model, or leave the agent's own. Each
attempt is an ordinary traced run, kept out of **Past runs** and linked from the results. Attempts
run one at a time, and only one evaluation runs at once. It uses a copy of the agent and the cases
taken when it starts, so editing either changes only later evaluations.

An attempt ends as one of these, in this order:

1. **Error**: the run could not start (a tool's server is not connected), failed with a provider
   error, or was stopped.
2. **Fail**: the run ended any way other than completed, unless a check expects that end.
3. **Fail**: a check failed.
4. **Error**: a check could not be decided, such as a judge that answered neither yes nor no.
5. **Pass** otherwise.

A pass rate leaves errors out, so a rate limit does not look like a bad agent. A case whose attempts
are all errors has no pass rate. The overall rate pools every attempt; it is not an average of the
cases' rates.

**Compare with** sets an evaluation beside an earlier one of the same agent. Each case shows as
better, worse or the same. A case that was edited shows as changed, since its rates are about
different things, and cases in only one of them show as new or removed.

If the village is running on the same provider, the start form warns you: they share its rate
limits, and the village has no retries, so it could lose turns or pause itself. You can pause it
first. Ordinary runs are not held back either.

### What an evaluation can cost

An attempt stops at its budget, but nothing limits an evaluation as a whole. At most 500 attempts
(50 cases, 10 times each) at the default budget is 100 million tokens; at the largest budget it is
1 billion, and judge calls come on top. Those are worst cases, but **Stop** is the only brake, so
start with few cases and few repeats on a paid model.

## Budgets

A budget is the most one run may use: model calls, tokens, tool calls and seconds. Set it in the
agent's settings.

| | Model calls | Tokens | Tool calls | Seconds |
|---|---|---|---|---|
| Default | 30 | 200,000 | 30 | 600 |
| Largest | 200 | 2,000,000 | 200 | 3,600 |

- **Who has one**: a new agent starts with the default. Agents saved before this milestone and the
  templates have none, and run as before. A copy keeps what its source has.
- **In an evaluation** an agent without a budget runs under the default, and the results say so. The
  agent itself stays without one.
- **Going over**: the run starts no further step and ends **over budget**, saying which limit it
  reached, with its trace kept.
- **Parallel branches** share one budget. Model and tool calls count when they start, so those limits
  are never passed. Calls already under way finish and stay in the trace. Tokens are known only
  after a call, so a run can end somewhat past its token limit.
- **Tokens** count what was sent, cached tokens included, not what was billed. A provider that reports
  no tokens never trips the limit, and a token check on such a run counts as an error.
- **The time limit** abandons a call under way. Time spent waiting for your approval does not count,
  whatever other branches do meanwhile.

## Stop

**Stop** in a running lab run ends it within 2 seconds, as **stopped**, with its trace kept. A tool
already called may still do its work; the trace says its answer was not awaited. The village's runs
cannot be stopped this way.

## Retries

A model call that fails for a passing reason is tried up to 2 more times, 2 s and then 8 s later. When
the provider says how long to wait, the lab waits that long, up to 30 s.

| Retried | Not retried |
|---|---|
| HTTP 408, 429, 500, 502, 503, 504, 529 | a refused request, a wrong key, an unknown model |
| timeouts and lost connections | running out of quota, a declined request, an unreadable answer |

Each attempt is its own model span with its reason and wait, and counts against the budget. A wait
that would pass the time budget ends the run as over budget instead.

## Approvals

In an agent's settings, mark tools under **Ask me before calling**. Before such a tool is called, by
the model or by a tool block, the run waits as **waiting for approval**, and a notice shows on every
page. The run shows the tool and its arguments, with secrets removed.

- **Approve**: the call goes out as usual.
- **Deny**, with a reason if you like: the tool is not called, and the denial becomes its result, so
  the model reads it, or a tool block passes it on. The run goes on.
- **No answer within 10 minutes** counts as a denial.

Calls from one model answer are decided one by one, in order. Each decision is a span saying what was
decided and by whom. A denied call has no tool span, so a tool span always means the tool ran.

In an evaluation nobody is watching, so each case says what to do: approve or deny, by default deny.
The trace marks those decisions as the case's.

If the lab stops during a run, the run shows as **interrupted** when it starts again, and no waiting
call goes out. An evaluation shows as interrupted too, with the results it had; it does not resume.
