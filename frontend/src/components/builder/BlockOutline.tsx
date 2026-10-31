import type { Block, BlockKind, ToolInfo } from "@/lib/api";
import {
  addBlock,
  blockErrors,
  canRemoveBlock,
  childLists,
  KIND_LABELS,
  moveBlock,
  removeBlock,
} from "@/lib/blocks";
import type { Path, Section } from "@/lib/builder";
import type { Form } from "./fields";

const SMALL =
  "rounded px-1.5 py-0.5 text-sm text-muted hover:bg-paper hover:text-ink focus-visible:outline-2 focus-visible:outline-llm disabled:opacity-30 disabled:hover:bg-transparent";

// The colour of the block's graph node, so the outline and the graph read as one picture.
function dot(block: Block): string {
  if (block.kind === "tool") return "bg-tool";
  if (block.kind === "check" || (block.kind === "loop" && block.exit === "check")) return "bg-step";
  if (block.kind === "parallel" && block.mode === "branches") return "border border-step bg-panel";
  return "bg-llm";
}

const KINDS = Object.entries(KIND_LABELS) as [BlockKind, string][];

type Props = {
  form: Form;
  tools: ToolInfo[];
  selected: Path | null;
  onOpen: (section: Section) => void;
};

function Entry({ block, path, index, count, props }: { block: Block; path: Path; index: number; count: number; props: Props }) {
  const { form, tools, selected, onOpen } = props;
  const listPath = path.slice(0, -1);
  const isSelected = selected?.join(".") === path.join(".");
  const invalid = blockErrors(form.errors, path).length > 0;
  return (
    <li>
      <div className={`flex items-center gap-1 rounded-md px-1 ${isSelected ? "bg-paper" : ""}`}>
        <span className={`size-2.5 shrink-0 rounded-full ${dot(block)}`} aria-hidden />
        <button
          type="button"
          onClick={() => onOpen({ kind: "block", path })}
          aria-current={isSelected || undefined}
          className="min-w-0 flex-1 truncate rounded px-1 py-1 text-left text-sm focus-visible:outline-2 focus-visible:outline-llm"
        >
          <span className={invalid ? "font-medium text-fault" : "font-medium text-ink"}>{block.name}</span>{" "}
          <span className="text-muted">{KIND_LABELS[block.kind]}</span>
          {invalid && <span className="sr-only"> (has errors)</span>}
        </button>
        {!form.readOnly && (
          <>
            <button type="button" aria-label={`Move ${block.name} up`} disabled={index === 0} onClick={() => form.update((d) => moveBlock(d, path, -1))} className={SMALL}>
              ↑
            </button>
            <button type="button" aria-label={`Move ${block.name} down`} disabled={index === count - 1} onClick={() => form.update((d) => moveBlock(d, path, 1))} className={SMALL}>
              ↓
            </button>
            <button
              type="button"
              aria-label={`Remove ${block.name}`}
              disabled={!canRemoveBlock(form.draft, path)}
              title={canRemoveBlock(form.draft, path) ? undefined : "A list keeps at least one block"}
              onClick={() => form.update((d) => removeBlock(d, path))}
              className={SMALL}
            >
              ✕
            </button>
            <select
              aria-label={`Add a block after ${block.name}`}
              value=""
              onChange={(e) => {
                const kind = e.target.value as BlockKind;
                if (kind) form.update((d) => addBlock(d, listPath, index + 1, kind, tools));
              }}
              className="w-8 cursor-pointer appearance-none rounded bg-transparent px-1.5 py-0.5 text-center text-sm font-semibold text-llm hover:bg-paper focus-visible:outline-2 focus-visible:outline-llm"
            >
              <option value="">+</option>
              {KINDS.map(([kind, label]) => (
                <option key={kind} value={kind}>
                  Add {label.toLowerCase()} after {block.name}
                </option>
              ))}
            </select>
          </>
        )}
      </div>
      {childLists(block).map((list) => (
        <div key={list.path.join(".")} className="mt-0.5 mb-1 ml-2 border-l-2 border-rule pl-2">
          <p className="pt-0.5 text-xs text-muted">{list.label}</p>
          <BlockList blocks={list.blocks} listPath={[...path, ...list.path]} props={props} />
        </div>
      ))}
    </li>
  );
}

function BlockList({ blocks, listPath, props }: { blocks: Block[]; listPath: Path; props: Props }) {
  return (
    <ol className="flex flex-col">
      {blocks.map((block, i) => (
        <Entry key={`${i}:${block.name}`} block={block} path={[...listPath, i]} index={i} count={blocks.length} props={props} />
      ))}
    </ol>
  );
}

/** The agent's blocks in run order, nested as they run; all structural edits happen here. */
export function BlockOutline(props: Props) {
  const blocks = (props.form.draft.config.blocks as Block[] | undefined) ?? [];
  return (
    <nav aria-label="Blocks" className="flex flex-col gap-1">
      <h4 className="text-sm font-medium text-ink">Blocks, in run order</h4>
      <BlockList blocks={blocks} listPath={["config", "blocks"]} props={props} />
      {!props.form.readOnly && (
        <p className="text-sm text-muted">
          + adds a block after another. Prompts can use {"{input}"}, {"{previous}"} and earlier block names in braces.
        </p>
      )}
    </nav>
  );
}
