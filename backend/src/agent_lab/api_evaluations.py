"""Test cases and evaluations over HTTP (specs/017-evaluation-harness/contracts/interfaces.md)."""

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_lab.agents.registry import AGENTS
from agent_lab.api_errors import field_error
from agent_lab.blocks.model import LayoutError
from agent_lab.evaluation.examples import EXAMPLES, example
from agent_lab.evaluation.model import Attempt, Case, CaseFields, Evaluation
from agent_lab.evaluation.results import Comparison, Summary, compare, summarize
from agent_lab.evaluation.runner import EvaluationConflict, Evaluations, NothingToEvaluate
from agent_lab.llm.base import ProviderName
from agent_lab.llm.models import ModelRef, UnavailableModel
from agent_lab.runs import UnknownAgent
from agent_lab.store import NameInUse, Store
from agent_lab.village.runner import Village

MAX_CASES = 50


class StartEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repeats: int = Field(ge=1, le=10)
    case_ids: list[str] | None = None  # None: all of them
    model: ModelRef | None = None  # None: the agent's own


class EvaluationSummary(BaseModel):
    evaluation: Evaluation
    summary: Summary


class EvaluationDetail(EvaluationSummary):
    attempts: list[Attempt]


class Notice(BaseModel):
    village_shares_provider: bool


def _fields(case: Case) -> CaseFields:
    return CaseFields.model_validate(case.model_dump(include=set(CaseFields.model_fields)))


def copy_cases(store: Store, source: str, agent_id: str) -> None:
    """A template's examples, not the owner's cases beside them, or a saved agent's cases."""
    for case in EXAMPLES[source] if source in AGENTS else store.list_cases(source):
        store.create_case(agent_id, _fields(case))


def add_evaluation_routes(
    app: FastAPI, store: Store, evaluations: Evaluations, village: Village
) -> None:
    def exists(agent_id: str) -> None:
        if agent_id not in AGENTS and store.get_agent(agent_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown agent")

    def name_is_free(agent_id: str, name: str) -> None:
        """Examples are not in the table, whose own rule covers the rest."""
        taken = {c.name.strip().lower() for c in EXAMPLES.get(agent_id, [])}
        if name.strip().lower() in taken:
            raise field_error(("body", "name"), "name already in use")

    def own_case(case_id: str) -> Case:
        if example(case_id):
            raise HTTPException(status.HTTP_409_CONFLICT, "a template's examples are read-only")
        case = store.get_case(case_id)
        if case is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown case")
        return case

    def found(eval_id: str) -> Evaluation:
        evaluation = store.get_evaluation(eval_id)
        if evaluation is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown evaluation")
        return evaluation

    @app.get("/agents/{agent_id}/cases")
    async def list_cases(agent_id: str) -> list[Case]:
        exists(agent_id)
        return evaluations.cases_of(agent_id)

    @app.post("/agents/{agent_id}/cases", status_code=status.HTTP_201_CREATED)
    async def create_case(agent_id: str, body: CaseFields) -> Case:
        exists(agent_id)
        if len(evaluations.cases_of(agent_id)) >= MAX_CASES:
            raise HTTPException(status.HTTP_409_CONFLICT, f"at most {MAX_CASES} cases per agent")
        name_is_free(agent_id, body.name)
        try:
            return store.create_case(agent_id, body)
        except NameInUse:
            raise field_error(("body", "name"), "name already in use") from None

    @app.put("/cases/{case_id}")
    async def update_case(case_id: str, body: CaseFields) -> Case:
        name_is_free(own_case(case_id).agent_id, body.name)
        try:
            updated = store.update_case(case_id, body)
        except NameInUse:
            raise field_error(("body", "name"), "name already in use") from None
        assert updated is not None, "own_case found it, and nothing awaited since"
        return updated

    @app.delete("/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_case(case_id: str) -> None:
        own_case(case_id)
        store.delete_case(case_id)

    @app.post("/agents/{agent_id}/evaluations", status_code=status.HTTP_202_ACCEPTED)
    async def start_evaluation(agent_id: str, body: StartEvaluation) -> Evaluation:
        try:
            return await evaluations.start(
                agent_id, repeats=body.repeats, case_ids=body.case_ids, model=body.model
            )
        except UnknownAgent:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown agent") from None
        except EvaluationConflict as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
        except NothingToEvaluate as exc:
            raise field_error(("body", "case_ids"), str(exc)) from None
        except UnavailableModel as exc:
            raise field_error(("body", "model"), str(exc)) from None
        except (LayoutError, ValidationError) as exc:
            raise field_error(("path", "agent_id"), f"the agent is not valid: {exc}") from None

    @app.get("/agents/{agent_id}/evaluations")
    async def list_evaluations(agent_id: str) -> list[EvaluationSummary]:
        exists(agent_id)
        return [
            EvaluationSummary(evaluation=e, summary=summarize(store.attempts(e.eval_id)))
            for e in store.list_evaluations(agent_id)
        ]

    # Before `/evaluations/{eval_id}`, which would otherwise take these words for an id.
    @app.get("/evaluations/compare")
    async def compare_evaluations(earlier: str, later: str) -> Comparison:
        first, second = found(earlier), found(later)
        if first.agent_id != second.agent_id:
            raise field_error(("query", "later"), "these evaluations are of different agents")
        return compare(first, store.attempts(earlier), second, store.attempts(later))

    @app.get("/evaluations/notice")
    async def evaluation_notice(provider: ProviderName) -> Notice:
        return Notice(village_shares_provider=provider in village.running_on())

    @app.get("/evaluations/{eval_id}")
    async def get_evaluation(eval_id: str) -> EvaluationDetail:
        evaluation = found(eval_id)
        attempts = store.attempts(eval_id)
        return EvaluationDetail(
            evaluation=evaluation, summary=summarize(attempts), attempts=attempts
        )

    @app.post("/evaluations/{eval_id}/stop", status_code=status.HTTP_202_ACCEPTED)
    async def stop_evaluation(eval_id: str) -> Evaluation:
        evaluation = found(eval_id)
        if not evaluations.stop(eval_id):
            raise HTTPException(status.HTTP_409_CONFLICT, "this evaluation is not running")
        return evaluation
