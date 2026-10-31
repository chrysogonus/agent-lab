import type { ModelInfo } from "@/lib/api";
import { getField, pathKey, renameItem, type Draft, type ListKind, type Path } from "@/lib/builder";
import { modelOptions, refFromValue, refValue, sameRef } from "@/lib/models";

/** What every builder field needs: the draft, how to change it, and its errors. */
export type Form = {
  draft: Draft;
  set: (path: Path, value: unknown) => void;
  update: (edit: (draft: Draft) => Draft) => void; // structural edits from lib/builder
  readOnly: boolean; // templates: settings are shown, not edited
  errors: Record<string, string>;
};

export const FIELD =
  "w-full rounded-md border border-rule bg-panel px-2.5 py-1.5 text-sm text-ink focus-visible:outline-2 focus-visible:outline-llm aria-invalid:border-fault";
export const INPUT = `${FIELD} read-only:bg-paper read-only:text-muted`;

export function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} className="text-sm text-fault">
      {message}
    </p>
  );
}

export function TextField({
  form,
  path,
  label,
  multiline = false,
  mono = false,
  hint,
}: {
  form: Form;
  path: Path;
  label: string;
  multiline?: boolean;
  mono?: boolean; // prompts: what the model reads, verbatim
  hint?: string;
}) {
  const id = `field-${pathKey(path)}`;
  const error = form.errors[pathKey(path)];
  const value = String(getField(form.draft, path) ?? "");
  const shared = {
    id,
    value,
    readOnly: form.readOnly,
    "aria-invalid": error ? true : undefined,
    "aria-describedby": error ? `${id}-error` : undefined,
    className: `${INPUT} ${mono ? "font-mono text-[13px] leading-relaxed" : ""}`,
  };
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
      </label>
      {multiline ? (
        <textarea
          {...shared}
          rows={Math.min(12, Math.max(3, Math.ceil(value.length / 48)))}
          onChange={(e) => form.set(path, e.target.value)}
        />
      ) : (
        <input {...shared} onChange={(e) => form.set(path, e.target.value)} />
      )}
      {hint && <p className="text-sm text-muted">{hint}</p>}
      <FieldError id={`${id}-error`} message={error} />
    </div>
  );
}

export function NumberField({ form, path, label }: { form: Form; path: Path; label: string }) {
  const id = `field-${pathKey(path)}`;
  const error = form.errors[pathKey(path)];
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-3">
        <label htmlFor={id} className="text-sm font-medium text-ink">
          {label}
        </label>
        <input
          id={id}
          type="number"
          step={1}
          value={String(getField(form.draft, path) ?? "")}
          readOnly={form.readOnly}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
          // An empty box is sent as is; the server names what is allowed.
          onChange={(e) => form.set(path, e.target.value === "" ? "" : Number(e.target.value))}
          className={`${INPUT} w-20 tabular-nums`}
        />
      </div>
      <FieldError id={`${id}-error`} message={error} />
    </div>
  );
}

export function Toggle({
  form,
  path,
  label,
  hint,
}: {
  form: Form;
  path: Path;
  label: string;
  hint?: string;
}) {
  const id = `field-${pathKey(path)}`;
  return (
    <div className="flex flex-col gap-0.5">
      <label htmlFor={id} className="flex items-center gap-2 text-sm font-medium text-ink">
        <input
          id={id}
          type="checkbox"
          checked={getField(form.draft, path) === true}
          disabled={form.readOnly}
          onChange={(e) => form.set(path, e.target.checked)}
          className="size-4 accent-llm"
        />
        {label}
      </label>
      {hint && <p className="pl-6 text-sm text-muted">{hint}</p>}
    </div>
  );
}

/** A list item's name: also its graph node id, so renames go through `renameItem`. */
export function NameField({
  form,
  kind,
  index,
  name,
  hint,
}: {
  form: Form;
  kind: ListKind;
  index: number;
  name: string;
  hint: string;
}) {
  const id = `field-${kind}-${index}-name`;
  // Aspect names are dict keys: pydantic reports them at "<name>.[key]".
  const key = kind === "aspects" ? `config.aspects.${name}.[key]` : `config.${kind}.${index}.name`;
  const error = form.errors[key];
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        Name
      </label>
      <input
        id={id}
        value={name}
        readOnly={form.readOnly}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        onChange={(e) => form.update((d) => renameItem(d, kind, index, e.target.value))}
        className={INPUT}
      />
      <p className="text-sm text-muted">{hint}</p>
      <FieldError id={`${id}-error`} message={error} />
    </div>
  );
}

/** The agent's model: Default (follows the configured default) or a pinned model. */
export function ModelSelect({ form, models }: { form: Form; models: ModelInfo[] }) {
  const id = "field-model";
  const current = form.draft.model;
  const options = modelOptions(models, current);
  const error = form.errors["model"] ?? form.errors["model.model"] ?? form.errors["model.provider"];
  const runsOn = current ? models.find((m) => sameRef(m, current)) : models.find((m) => m.default);
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        Model
      </label>
      <select
        id={id}
        value={refValue(current)}
        disabled={form.readOnly}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        onChange={(e) => form.set(["model"], refFromValue(e.target.value))}
        className={`${FIELD} disabled:bg-paper disabled:text-muted`} // :read-only matches every select
      >
        <option value={options.default.value}>{options.default.label}</option>
        {options.groups.map((group) => (
          <optgroup key={group.label} label={group.label}>
            {group.options.map((o) => (
              <option key={o.value} value={o.value} disabled={o.disabled}>
                {o.label}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      {runsOn?.external && (
        <p className="text-sm text-muted">
          Prompts and tool results are sent to {runsOn.provider_label}.
        </p>
      )}
      <FieldError id={`${id}-error`} message={error} />
    </div>
  );
}
