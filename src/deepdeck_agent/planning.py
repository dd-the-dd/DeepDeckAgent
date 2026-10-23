from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from .agent import Agent
from .decisions import Action, Decision, DecisionResult
from .events import Event
from .protocol import DecisionResolvedRequest, DecisionResponse
from .views import Game


class PlanRevisionKind(str, Enum):
    KEEP = "keep"
    ADVANCE = "advance"
    PATCH = "patch"
    REPLAN = "replan"


class ComputeMode(str, Enum):
    REFLEX = "reflex"
    TACTICAL = "tactical"
    STRATEGIC = "strategic"


@dataclass(frozen=True)
class TimingIntent:
    window: str = "now"
    earliest_turn: int | None = None
    latest_turn: int | None = None
    after_event: str | None = None
    decision_offset: int = 0


@dataclass(frozen=True)
class ActionIntent:
    kind: str
    source_id: str | None = None
    target_ids: tuple[str, ...] = ()
    parameters: dict[str, Any] = field(default_factory=dict)
    timing: TimingIntent = field(default_factory=TimingIntent)
    engine_action_id: str | None = None


@dataclass(frozen=True)
class EffectPrediction:
    state_delta: dict[str, Any] = field(default_factory=dict)
    event_kinds: tuple[str, ...] = ()
    confidence: float = 0.0
    latent: tuple[float, ...] = ()


@dataclass(frozen=True)
class FeasibilityPrediction:
    probability: float
    reason: str | None = None
    missing_requirements: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanBranch:
    condition: str
    next_node_id: str
    event_kinds: tuple[str, ...] = ()
    probability: float = 0.0


@dataclass(frozen=True)
class PlanNode:
    node_id: str
    objective: str
    intent: ActionIntent
    expected_effect: EffectPrediction = field(default_factory=EffectPrediction)
    feasibility: FeasibilityPrediction = field(default_factory=lambda: FeasibilityPrediction(0.0))
    branches: tuple[PlanBranch, ...] = ()
    fallback_node_id: str | None = None


@dataclass(frozen=True)
class PlanGraph:
    plan_id: str
    root_node_id: str
    nodes: tuple[PlanNode, ...]
    objective: str = ""
    state_revision: int | None = None

    def node(self, node_id: str) -> PlanNode | None:
        return next((node for node in self.nodes if node.node_id == node_id), None)


@dataclass(frozen=True)
class ActivePlan:
    graph: PlanGraph
    current_node_id: str
    revision: int = 0
    invalidated_reason: str | None = None

    @property
    def current_node(self) -> PlanNode | None:
        return self.graph.node(self.current_node_id)


@dataclass(frozen=True)
class PlanRevision:
    kind: PlanRevisionKind
    plan: PlanGraph | None = None
    next_node_id: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ComputeBudget:
    mode: ComputeMode
    budget_ms: int
    remaining_ms: int | None = None
    importance: float = 0.0


@dataclass(frozen=True)
class PlanningContext:
    game: Game
    events: tuple[Event, ...] = ()
    budget: ComputeBudget = field(
        default_factory=lambda: ComputeBudget(ComputeMode.TACTICAL, 1_000)
    )


@runtime_checkable
class PlanningModel(Protocol):
    async def create_plan(self, context: PlanningContext) -> PlanGraph: ...

    async def review_plan(self, context: PlanningContext, plan: ActivePlan) -> PlanRevision: ...

    async def select_intent(
        self, decision: Decision, plan: ActivePlan, budget: ComputeBudget
    ) -> ActionIntent: ...


class ActionBinder:
    """Bind a semantic plan intent only to actions authorized by the Engine."""

    @staticmethod
    def _source_id(action: Action) -> str | None:
        raw = action.raw
        for key in ("cardInstanceId", "sourceId", "sourceCardInstanceId"):
            if raw.get(key) is not None:
                return str(raw[key])
        return None

    @staticmethod
    def _target_ids(action: Action) -> set[str]:
        target_ids = {
            *action.target_permanent_ids,
            *action.target_player_ids,
            *action.target_stack_ids,
        }
        raw_target_ids = action.raw.get("targetIds", [])
        if isinstance(raw_target_ids, list):
            target_ids.update(str(value) for value in raw_target_ids)
        return target_ids

    def candidates(self, intent: ActionIntent, decision: Decision) -> list[Action]:
        if intent.engine_action_id:
            exact = [action for action in decision.actions if action.id == intent.engine_action_id]
            if exact:
                return exact
        kind = intent.kind.casefold()
        candidates = [action for action in decision.actions if action.kind.casefold() == kind]
        if intent.source_id:
            candidates = [
                action for action in candidates if self._source_id(action) == intent.source_id
            ]
        if intent.target_ids:
            wanted = set(intent.target_ids)
            targeted = [
                action
                for action in candidates
                if wanted <= self._target_ids(action)
            ]
            if targeted:
                candidates = targeted
        return candidates

    def bind(self, intent: ActionIntent, decision: Decision) -> Action | None:
        candidates = self.candidates(intent, decision)
        return candidates[0] if candidates else None


class PlannedAgent(Agent):
    """Optional SDK adapter for persistent, event-revisable planning agents."""

    def __init__(self, planning_model: PlanningModel) -> None:
        self.planning_model = planning_model
        self.action_binder = ActionBinder()
        self._plans: dict[str, ActivePlan] = {}
        self._events: dict[str, list[Event]] = {}
        self._request_context: dict[str, str] = {}

    @staticmethod
    def context_id(game: Game) -> str:
        raw = game.raw
        return str(raw.get("sessionId", raw.get("gameId", game.player_id or "game")))

    def compute_budget(self, decision: Decision) -> ComputeBudget:
        raw_clock = decision.raw.get("clock", decision.game.raw.get("clock", {}))
        clock = raw_clock if isinstance(raw_clock, dict) else {}
        remaining = clock.get("remainingMs")
        remaining_ms = int(remaining) if isinstance(remaining, (int, float)) else None
        actions = len(decision.actions)
        importance = min(1.0, max(0.0, (actions - 1) / 5.0))
        if actions <= 1:
            return ComputeBudget(ComputeMode.REFLEX, 25, remaining_ms, importance)
        if importance >= 0.6 and (remaining_ms is None or remaining_ms > 60_000):
            budget = min(10_000, max(1_000, (remaining_ms or 100_000) // 20))
            return ComputeBudget(ComputeMode.STRATEGIC, budget, remaining_ms, importance)
        return ComputeBudget(ComputeMode.TACTICAL, 750, remaining_ms, importance)

    async def on_game_start(self, game: Game, known_deck: list[dict[str, object]]) -> None:
        context_id = self.context_id(game)
        self._events[context_id] = []
        self._plans.pop(context_id, None)

    async def on_event(self, event: Event, game: Game) -> None:
        self._events.setdefault(self.context_id(game), []).append(event)

    async def on_decision_resolved(self, result: DecisionResolvedRequest) -> None:
        context_id = self._request_context.pop(result.request_id, None)
        if context_id is None or result.fallback_reason is None:
            return
        active = self._plans.get(context_id)
        if active is not None:
            self._plans[context_id] = replace(
                active,
                revision=active.revision + 1,
                invalidated_reason=result.fallback_reason,
            )

    async def make_decision(self, decision: Decision) -> DecisionResponse:
        context_id = self.context_id(decision.game)
        budget = self.compute_budget(decision)
        events = tuple(self._events.pop(context_id, []))
        context = PlanningContext(decision.game, events, budget)
        active = self._plans.get(context_id)
        if active is None:
            graph = await self.planning_model.create_plan(context)
            active = ActivePlan(graph, graph.root_node_id)
        elif events or active.invalidated_reason:
            revision = await self.planning_model.review_plan(context, active)
            if revision.kind is PlanRevisionKind.REPLAN:
                graph = revision.plan or await self.planning_model.create_plan(context)
                active = ActivePlan(graph, graph.root_node_id, active.revision + 1)
            elif revision.kind is PlanRevisionKind.PATCH and revision.plan is not None:
                active = ActivePlan(
                    revision.plan,
                    revision.next_node_id or active.current_node_id,
                    active.revision + 1,
                )
            elif revision.kind is PlanRevisionKind.ADVANCE and revision.next_node_id:
                active = replace(
                    active,
                    current_node_id=revision.next_node_id,
                    revision=active.revision + 1,
                    invalidated_reason=None,
                )
            else:
                active = replace(active, invalidated_reason=None)
        self._plans[context_id] = active
        self._request_context[decision.request_id] = context_id
        intent = await self.planning_model.select_intent(decision, active, budget)
        action = self.action_binder.bind(intent, decision)
        result: DecisionResult = action if action is not None else self._safe_default(decision)
        return decision.normalize(result)

    async def on_game_end(self, outcome: dict[str, object]) -> None:
        self._plans.clear()
        self._events.clear()
        self._request_context.clear()
