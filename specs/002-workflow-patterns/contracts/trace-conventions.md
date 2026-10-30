# Trace conventions for workflows

Applies to every agent and workflow from M2 on.

1. Root span: `step "invoke_agent {agent_id}"` at node `start`, input = prompt, output = answer.
2. Final span: `step "final answer"` at node `end`, `lab.came_from` = last node(s); error set for
   any non-`completed` end state.
3. Every node visit opens a span at that node with `lab.came_from`; nested spans at the same node
   (e.g. the llm call inside a decision) omit it.
4. Model calls only via `steps.chat` (kind `llm`, name `chat {model}`); tool calls only via
   `steps.call_tool` (kind `tool`, name `execute_tool {tool}`).
5. Decisions only via `steps.decide`: decision span (kind `route` for routing, otherwise `step`)
   named after the decision (`route`, `plan`, `verdict`), input = messages + schema, output =
   validated decision, error = validation failure. The code gate is a `step "gate"` span with
   output `GateResult`.
6. Concurrent work: one span per branch/worker, parent = the step that launched them.
