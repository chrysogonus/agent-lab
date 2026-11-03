import type { Block, CheckRule, ToolInfo } from "@/lib/api";
import {
  addBranch,
  addRoute,
  argumentsFor,
  blockAt,
  canAddBranch,
  canAddRoute,
  canRemoveBranch,
  canRemoveRoute,
  KIND_LABELS,
  removeBranch,
  removeRoute,
  renameBlock,
  renameRoute,
  setExit,
  setMode,
  setRule,
} from "@/lib/blocks";
import { pathKey, setField, type Path } from "@/lib/builder";
import { FIELD, FieldError, INPUT, NumberField, TextField, Toggle, type Form } from "./fields";
import { ToolCheckboxes, ToolOptions } from "./ToolChoices";

const REFERENCES = "{input} is the user's prompt, {previous} the previous block's output, {name} an earlier block's output.";

const SMALL_ACTION =
  "self-start rounded-md px-2 py-1 text-sm font-semibold text-llm hover:bg-paper focus-visible:outline-2 focus-visible:outline-llm disabled:opacity-40";

const RULES: [CheckRule["rule"], string][] = [
  ["min_bullets", "At least N bullet lines"],
  ["max_words", "At most N words"],
  ["contains", "Contains a text"],
  ["valid_json", "Is valid JSON"],
];

function Choice<T extends string>({
  form,
  label,
  name,
  value,
  options,
  onChange,
}: {
  form: Form;
  label: string;
  name: string;
  value: T;
  options: [T, string][];
  onChange: (value: T) => void;
}) {
  return (
    <fieldset className="flex flex-col gap-1">
      <legend className="mb-1 text-sm font-medium text-ink">{label}</legend>
      {options.map(([option, text]) => (
        <label key={option} className="flex items-center gap-2 text-sm text-ink">
          <input
            type="radio"
            name={name}
            checked={value === option}
            disabled={form.readOnly}
            onChange={() => onChange(option)}
            className="accent-llm"
          />
          {text}
        </label>
      ))}
    </fieldset>
  );
}

/** A check rule and its value, at a check block or at a loop's `check`. */
function RuleFields({ form, rulePath, rule }: { form: Form; rulePath: Path; rule: CheckRule }) {
  const id = `field-${pathKey(rulePath)}-rule`;
  return (
    <>
      <div className="flex flex-col gap-1">
        <label htmlFor={id} className="text-sm font-medium text-ink">
          Rule
        </label>
        <select
          id={id}
          value={rule.rule}
          disabled={form.readOnly}
          onChange={(e) => form.update((d) => setRule(d, rulePath, e.target.value as CheckRule["rule"]))}
          className={`${FIELD} disabled:bg-paper disabled:text-muted`} // :read-only matches every select
        >
          {RULES.map(([value, text]) => (
            <option key={value} value={value}>
              {text}
            </option>
          ))}
        </select>
      </div>
      {(rule.rule === "min_bullets" || rule.rule === "max_words") && (
        <NumberField form={form} path={[...rulePath, "value"]} label="N" />
      )}
      {rule.rule === "contains" && <TextField form={form} path={[...rulePath, "value"]} label="Text" />}
    </>
  );
}

function NameInput({ form, path, label, value, onChange, hint }: { form: Form; path: Path; label: string; value: string; onChange: (v: string) => void; hint?: string }) {
  const id = `field-${pathKey(path)}`;
  const error = form.errors[pathKey(path)];
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
      </label>
      <input
        id={id}
        value={value}
        readOnly={form.readOnly}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        onChange={(e) => onChange(e.target.value)}
        className={INPUT}
      />
      {hint && <p className="text-sm text-muted">{hint}</p>}
      <FieldError id={`${id}-error`} message={error} />
    </div>
  );
}

function ModelFields({ form, path, block, tools }: { form: Form; path: Path; block: Block & { kind: "model" }; tools: ToolInfo[] }) {
  const toggle = (tool: string) =>
    form.set([...path, "tools"], block.tools.includes(tool) ? block.tools.filter((t) => t !== tool) : [...block.tools, tool]);
  return (
    <>
      <TextField form={form} path={[...path, "system"]} label="System prompt" multiline mono />
      <TextField form={form} path={[...path, "message"]} label="Message" multiline mono hint={REFERENCES} />
      <fieldset className="flex flex-col gap-1.5">
        <legend className="mb-1 text-sm font-medium text-ink">Tools it may call (up to 6)</legend>
        <ToolCheckboxes tools={tools} chosen={block.tools} disabled={form.readOnly} onToggle={toggle} />
        <FieldError id={`field-${pathKey([...path, "tools"])}-error`} message={form.errors[pathKey([...path, "tools"])]} />
      </fieldset>
      {block.tools.length > 0 && (
        <>
          <NumberField form={form} path={[...path, "max_iterations"]} label="Max model calls" />
          <Toggle
            form={form}
            path={[...path, "answer_on_last_call"]}
            label="Answer without tools on the last call"
            hint="Otherwise reaching the limit while it still calls tools ends the run."
          />
        </>
      )}
    </>
  );
}

function ToolFields({ form, path, block, tools }: { form: Form; path: Path; block: Block & { kind: "tool" }; tools: ToolInfo[] }) {
  const id = `field-${pathKey([...path, "tool"])}`;
  const properties = tools.find((t) => t.name === block.tool)?.parameters.properties ?? {};
  return (
    <>
      <div className="flex flex-col gap-1">
        <label htmlFor={id} className="text-sm font-medium text-ink">
          Tool
        </label>
        <select
          id={id}
          value={block.tool}
          disabled={form.readOnly}
          onChange={(e) =>
            form.update((d) => {
              const tool = e.target.value;
              return setField(d, path, { ...(blockAt(d.config, path) as Block), tool, arguments: argumentsFor(tool, tools) });
            })
          }
          className={`${FIELD} disabled:bg-paper disabled:text-muted`}
        >
          <ToolOptions tools={tools} value={block.tool} />
        </select>
      </div>
      {Object.entries(properties).map(([key, schema]) => (
        <TextField
          key={key}
          form={form}
          path={[...path, "arguments", key]}
          label={`Argument: ${key}`}
          mono
          hint={schema.description ? `${schema.description.replace(/\.?$/, ".")} ${REFERENCES}` : REFERENCES}
        />
      ))}
      <FieldError id={`${id}-arguments-error`} message={form.errors[pathKey([...path, "arguments"])]} />
    </>
  );
}

function RouterFields({ form, path, block, tools }: { form: Form; path: Path; block: Block & { kind: "router" }; tools: ToolInfo[] }) {
  return (
    <>
      <TextField form={form} path={[...path, "prompt"]} label="Router prompt" multiline mono hint="Each route's name and description are added after it; the fallback last." />
      {block.routes.map((route, i) => (
        <fieldset key={i} className="flex flex-col gap-2 rounded-md border border-rule p-2">
          <legend className="px-1 text-sm font-medium text-ink">Route {route.name}</legend>
          <NameInput form={form} path={[...path, "routes", i, "name"]} label="Name" value={route.name} onChange={(v) => form.update((d) => renameRoute(d, path, i, v))} />
          <TextField form={form} path={[...path, "routes", i, "description"]} label="When to use it" />
          <label className="flex items-center gap-2 text-sm text-ink">
            <input type="radio" name={`fallback-${pathKey(path)}`} checked={block.fallback === route.name} disabled={form.readOnly} onChange={() => form.set([...path, "fallback"], route.name)} className="accent-llm" />
            Fallback when the decision is unusable
          </label>
          {!form.readOnly && (
            <button type="button" disabled={!canRemoveRoute(block, i)} onClick={() => form.update((d) => removeRoute(d, path, i))} className={SMALL_ACTION}>
              Remove route
            </button>
          )}
        </fieldset>
      ))}
      <FieldError id={`field-${pathKey(path)}-fallback-error`} message={form.errors[pathKey([...path, "fallback"])]} />
      {!form.readOnly && (
        <button type="button" disabled={!canAddRoute(block)} onClick={() => form.update((d) => addRoute(d, path, tools))} className={SMALL_ACTION}>
          Add route
        </button>
      )}
    </>
  );
}

function ParallelFields({ form, path, block, tools }: { form: Form; path: Path; block: Block & { kind: "parallel" }; tools: ToolInfo[] }) {
  return (
    <>
      <Choice
        form={form}
        label="Runs"
        name={`mode-${pathKey(path)}`}
        value={block.mode}
        options={[
          ["branches", "Fixed branches, at the same time"],
          ["per_item", "Its blocks once per planned item, at the same time"],
        ]}
        onChange={(mode) => form.update((d) => setMode(d, path, mode))}
      />
      {block.mode === "branches" ? (
        <>
          {(block.branches ?? []).map((branch, i) => (
            <div key={i} className="flex items-end gap-2">
              <div className="flex-1">
                <TextField form={form} path={[...path, "branches", i, "name"]} label={`Branch ${i + 1} name`} />
              </div>
              {!form.readOnly && (
                <button type="button" disabled={!canRemoveBranch(block)} onClick={() => form.update((d) => removeBranch(d, path, i))} className={SMALL_ACTION} aria-label={`Remove branch ${branch.name}`}>
                  Remove
                </button>
              )}
            </div>
          ))}
          {!form.readOnly && (
            <button type="button" disabled={!canAddBranch(block)} onClick={() => form.update((d) => addBranch(d, path, tools))} className={SMALL_ACTION}>
              Add branch
            </button>
          )}
          <p className="text-sm text-muted">The group&apos;s output lists each branch&apos;s output under its name; a model call after the group can merge them.</p>
        </>
      ) : (
        <>
          <TextField form={form} path={[...path, "planner"]} label="Planner prompt" multiline mono hint="The model answers with a list of items; the group's blocks run once per item, with {item}." />
          <NumberField form={form} path={[...path, "max_items"]} label="Max items" />
        </>
      )}
    </>
  );
}

function LoopFields({ form, path, block }: { form: Form; path: Path; block: Block & { kind: "loop" } }) {
  return (
    <>
      <Choice
        form={form}
        label="Repeat until"
        name={`exit-${pathKey(path)}`}
        value={block.exit}
        options={[
          ["judge", "A judge approves"],
          ["check", "A check passes"],
        ]}
        onChange={(exit) => form.update((d) => setExit(d, path, exit))}
      />
      {block.exit === "judge" ? (
        <TextField form={form} path={[...path, "judge"]} label="Judge prompt" multiline mono hint="The judge reads the last block's output and approves or gives feedback; {feedback} brings it to the next round." />
      ) : (
        block.check && <RuleFields form={form} rulePath={[...path, "check"]} rule={block.check} />
      )}
      <NumberField form={form} path={[...path, "max_rounds"]} label="Max rounds" />
    </>
  );
}

/** The settings of the block at `path`. */
export function BlockSettings({ form, path, tools }: { form: Form; path: Path; tools: ToolInfo[] }) {
  const block = blockAt(form.draft.config, path);
  if (!block) return null;
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted">{KIND_LABELS[block.kind]}</p>
      <NameInput
        form={form}
        path={[...path, "name"]}
        label="Name"
        value={block.name}
        onChange={(v) => form.update((d) => renameBlock(d, path, v))}
        hint="Also its node in the graph and {its-name} in later prompts."
      />
      {block.kind === "model" && <ModelFields form={form} path={path} block={block} tools={tools} />}
      {block.kind === "tool" && <ToolFields form={form} path={path} block={block} tools={tools} />}
      {block.kind === "check" && (
        <>
          <RuleFields form={form} rulePath={path} rule={block} />
          <p className="text-sm text-muted">Checks the previous output; failing ends the run with an error.</p>
        </>
      )}
      {block.kind === "router" && <RouterFields form={form} path={path} block={block} tools={tools} />}
      {block.kind === "parallel" && <ParallelFields form={form} path={path} block={block} tools={tools} />}
      {block.kind === "loop" && <LoopFields form={form} path={path} block={block} />}
    </div>
  );
}
