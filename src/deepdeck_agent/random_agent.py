from __future__ import annotations

import random

from .agent import Agent
from .decisions import Decision, DecisionResult
from .protocol import DecisionResponse


class RandomAgent(Agent):
    """Small reproducible baseline that samples one legal engine action."""

    def __init__(self, seed: int | None = None) -> None:
        self.random = random.Random(seed)

    async def make_decision(self, decision: Decision) -> DecisionResponse:
        choice = decision.choice or {}
        if choice.get("kind") == "numberSelection":
            minimum = int(choice.get("minimum", 0))
            maximum = int(choice.get("maximum", minimum))
            return decision.choose_number(self.random.randint(minimum, maximum))
        if choice.get("kind") == "cardSelection":
            candidates = [str(value) for value in choice.get("candidateCardInstanceIds", [])]
            self.random.shuffle(candidates)
            minimum = int(choice.get("minimum", 0))
            maximum = int(choice.get("maximum", len(candidates)))
            return decision.choose_cards(
                *candidates[: self.random.randint(minimum, maximum)]
            )
        if choice.get("kind") == "cardOrder":
            cards = [str(value) for value in choice.get("cardInstanceIds", [])]
            self.random.shuffle(cards)
            return decision.choose_cards(*cards)
        return decision.normalize(self._safe_default(decision))

    def _safe_default(self, decision: Decision) -> DecisionResult:
        if not decision.actions:
            raise ValueError(f"decision {decision.request_id} has no legal actions")
        return self.random.choice(decision.actions)
