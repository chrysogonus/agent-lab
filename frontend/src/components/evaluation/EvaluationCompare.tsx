import type { Comparison, ComparisonSide } from "@/lib/api";
import { budgetText, changeText, rateText } from "@/lib/evaluation";
import { modelLabel } from "@/lib/models";

const CHANGE_COLOR: Record<Comparison["rows"][number]["change"], string> = {
  up: "text-tool",
  down: "text-fault",
  same: "text-muted",
  changed: "text-muted",
  new: "text-muted",
  removed: "text-muted",
  no_rate: "text-muted",
};

function Side({ title, side }: { title: string; side: ComparisonSide }) {
  return (
    <div className="min-w-0 flex-1 rounded-md border border-rule p-3 text-sm">
      <h4 className="font-semibold text-ink">
        {title}: {rateText(side.overall)}
      </h4>
      <p className="break-words text-muted">
        Config {side.config_version}, {modelLabel(side.model)}
      </p>
      <p className="break-words text-muted">{budgetText(side.harness)}</p>
    </div>
  );
}

/** Which cases got better or worse between two evaluations, without opening a run (SC-006). */
export function EvaluationCompare({ comparison }: { comparison: Comparison }) {
  return (
    <section aria-label="Comparison" className="flex flex-col gap-3">
      <div className="flex flex-col gap-2 sm:flex-row">
        <Side title="Earlier" side={comparison.earlier} />
        <Side title="This one" side={comparison.later} />
      </div>
      <ul className="divide-y divide-rule/60 rounded-md border border-rule">
        {comparison.rows.map((row) => (
          <li key={row.case_id} className="flex flex-wrap justify-between gap-x-4 px-3 py-2 text-sm">
            <span className="font-medium text-ink">{row.name}</span>
            <span className={CHANGE_COLOR[row.change]}>{changeText(row)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
