from __future__ import annotations

from .decisions import Decision, DecisionResult
from .events import Event
from .protocol import DecisionResolvedRequest, DecisionResponse
from .views import Game


class Agent:
    """Subclass this class and override only the decisions your agent cares about."""

    async def analyze_starting_situation(
        self,
        observation: dict[str, object],
        known_deck: list[dict[str, object]],
    ) -> None:
        """Optional pre-game analysis with the visible setup and this agent's deck."""

    async def on_game_start(self, game: Game, known_deck: list[dict[str, object]]) -> None:
        """Called once before the first decision of a game."""

    async def on_observation(self, game: Game) -> None:
        """Called whenever a complete visible state has been reconstructed."""

    async def on_event(self, event: Event, game: Game) -> None:
        """Called once for every newly visible ordered game event."""

    async def on_decision_resolved(self, result: DecisionResolvedRequest) -> None:
        """Called when the server confirms or replaces the last decision."""

    async def on_game_end(self, outcome: dict[str, object]) -> None:
        """Called once when a terminal outcome is observed or pushed."""

    async def choose_opening_hand(self, decision: Decision) -> DecisionResult:
        return self._safe_default(decision)

    async def choose_mulligan(self, decision: Decision) -> DecisionResult:
        return decision.first("keepHand") or self._safe_default(decision)

    async def choose_mulligan_bottom(self, decision: Decision) -> DecisionResult:
        return self._safe_default(decision)

    async def choose_priority(self, decision: Decision) -> DecisionResult:
        return decision.pass_action or self._safe_default(decision)

    async def choose_discard(self, decision: Decision) -> DecisionResult:
        return self._safe_default(decision)

    async def choose_attackers(self, decision: Decision) -> DecisionResult:
        return decision.first("finishAttackers") or self._safe_default(decision)

    async def choose_blockers(self, decision: Decision) -> DecisionResult:
        return decision.first("finishBlockers") or self._safe_default(decision)

    async def choose_combat_damage(self, decision: Decision) -> DecisionResult:
        return self._safe_default(decision)

    async def choose_replacement(self, decision: Decision) -> DecisionResult:
        return self._safe_default(decision)

    async def choose_resolution(self, decision: Decision) -> DecisionResult:
        choice = decision.choice or {}
        if choice.get("kind") == "numberSelection":
            return decision.choose_number(int(choice.get("maximum", 0)))
        if choice.get("kind") == "cardSelection":
            candidates = [str(value) for value in choice.get("candidateCardInstanceIds", [])]
            minimum = int(choice.get("minimum", 0))
            return decision.choose_cards(*candidates[:minimum])
        if choice.get("kind") == "cardOrder":
            cards = [str(value) for value in choice.get("cardInstanceIds", [])]
            return decision.choose_cards(*cards)
        return self._safe_default(decision)

    async def choose_sideboarding(self, decision: Decision) -> DecisionResult:
        return self._safe_default(decision)

    async def make_decision(self, decision: Decision) -> DecisionResponse:
        handlers = {
            "openingHandSelection": self.choose_opening_hand,
            "mulligan": self.choose_mulligan,
            "mulliganBottom": self.choose_mulligan_bottom,
            "priority": self.choose_priority,
            "discard": self.choose_discard,
            "attackers": self.choose_attackers,
            "blockers": self.choose_blockers,
            "combatDamage": self.choose_combat_damage,
            "replacementChoice": self.choose_replacement,
            "resolutionChoice": self.choose_resolution,
            "sideboarding": self.choose_sideboarding,
        }
        handler = handlers.get(decision.kind)
        result = await handler(decision) if handler else self._safe_default(decision)
        return decision.normalize(result)

    def _safe_default(self, decision: Decision) -> DecisionResult:
        action = decision.first()
        if action is None:
            raise ValueError(f"decision {decision.request_id} has no legal actions")
        return action
