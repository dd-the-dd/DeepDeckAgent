from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .protocol import DecisionResponse
from .views import Card, Game


@dataclass(frozen=True)
class Action:
    raw: dict[str, Any]

    @property
    def id(self) -> str:
        return str(self.raw.get("id") or "")

    @property
    def kind(self) -> str:
        return str(self.raw.get("kind") or "")

    @property
    def label(self) -> str:
        return str(self.raw.get("label") or self.kind)

    @property
    def card_instance_id(self) -> str | None:
        value = self.raw.get("cardInstanceId")
        return str(value) if value else None

    @property
    def attacker_id(self) -> str | None:
        value = self.raw.get("attackerId")
        return str(value) if value else None

    @property
    def blocker_id(self) -> str | None:
        value = self.raw.get("blockerId")
        return str(value) if value else None

    @property
    def payment_sources(self) -> tuple[str, ...]:
        values = self.raw.get("paymentSources", [])
        return tuple(str(value) for value in values) if isinstance(values, list) else ()

    @property
    def targets(self) -> dict[str, dict[str, Any]]:
        values = self.raw.get("targets", {})
        if not isinstance(values, dict):
            return {}
        return {key: value for key, value in values.items() if isinstance(value, dict)}

    @property
    def target_permanent_ids(self) -> tuple[str, ...]:
        return tuple(
            str(target["instanceId"])
            for target in self.targets.values()
            if target.get("kind") == "permanent" and target.get("instanceId")
        )

    @property
    def target_player_ids(self) -> tuple[str, ...]:
        return tuple(
            str(target["playerId"])
            for target in self.targets.values()
            if target.get("kind") == "player" and target.get("playerId")
        )

    @property
    def target_stack_ids(self) -> tuple[str, ...]:
        return tuple(
            str(target["stackId"])
            for target in self.targets.values()
            if target.get("kind") == "stackObject" and target.get("stackId")
        )

    def targets_permanent(self, instance_id: str) -> bool:
        return instance_id in self.target_permanent_ids

    def respond(self) -> DecisionResponse:
        return DecisionResponse(action_id=self.id)


DecisionResult = Action | DecisionResponse | str


class Decision:
    """One engine question plus small helpers for inspecting its legal answers."""

    def __init__(self, request_id: str, player_id: str, raw: dict[str, Any], game: Game) -> None:
        self.request_id = request_id
        self.player_id = player_id
        self.raw = raw
        self.game = game

    @property
    def kind(self) -> str:
        return str(self.raw.get("kind") or "")

    @property
    def choice(self) -> dict[str, Any] | None:
        value = self.raw.get("choice")
        return value if isinstance(value, dict) else None

    @property
    def actions(self) -> list[Action]:
        values = self.raw.get("options", [])
        if not isinstance(values, list):
            return []
        return [Action(value) for value in values if isinstance(value, dict)]

    def actions_of(self, *kinds: str) -> list[Action]:
        accepted = {kind.casefold() for kind in kinds}
        return [action for action in self.actions if action.kind.casefold() in accepted]

    def first(self, *kinds: str) -> Action | None:
        actions = self.actions_of(*kinds) if kinds else self.actions
        return actions[0] if actions else None

    @property
    def pass_action(self) -> Action | None:
        return self.first(
            "passPriority",
            "finishAttackers",
            "finishBlockers",
            "declinePayment",
            "keepHand",
        )

    def card_for(self, action: Action) -> Card | None:
        return self.game.card(action.card_instance_id)

    def target_permanents(self, action: Action) -> list[Card]:
        return [
            card
            for instance_id in action.target_permanent_ids
            if (card := self.game.permanent(instance_id)) is not None
        ]

    def choose(self, action: Action | str) -> DecisionResponse:
        action_id = action.id if isinstance(action, Action) else action
        if action_id not in {candidate.id for candidate in self.actions}:
            raise ValueError(f"{action_id!r} is not a legal action for {self.request_id}")
        return DecisionResponse(action_id=action_id)

    def choose_number(self, value: int) -> DecisionResponse:
        choice = self.choice or {}
        minimum = int(choice.get("minimum", value))
        maximum = int(choice.get("maximum", value))
        if not minimum <= value <= maximum:
            raise ValueError(f"number must be between {minimum} and {maximum}")
        action = self.first()
        return DecisionResponse(action_id=action.id if action else None, number_value=value)

    def choose_cards(self, *instance_ids: str) -> DecisionResponse:
        selected = list(instance_ids)
        choice = self.choice or {}
        kind = choice.get("kind")
        if kind == "cardSelection":
            candidates = [str(value) for value in choice.get("candidateCardInstanceIds", [])]
            minimum = int(choice.get("minimum", 0))
            maximum = int(choice.get("maximum", len(candidates)))
            if not minimum <= len(selected) <= maximum:
                raise ValueError(f"select between {minimum} and {maximum} cards")
            if len(set(selected)) != len(selected) or any(
                instance_id not in candidates for instance_id in selected
            ):
                raise ValueError("card selection contains a duplicate or an illegal card")
        elif kind == "cardOrder":
            cards = [str(value) for value in choice.get("cardInstanceIds", [])]
            if len(selected) != len(cards) or set(selected) != set(cards):
                raise ValueError("card order must contain every candidate exactly once")
        return DecisionResponse(card_instance_ids=selected)

    def normalize(self, result: DecisionResult) -> DecisionResponse:
        if isinstance(result, DecisionResponse):
            return result
        return self.choose(result)
