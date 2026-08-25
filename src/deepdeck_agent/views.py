from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _walk(value: Any) -> Iterator[Any]:
    yield value
    if isinstance(value, Mapping):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


@dataclass(frozen=True)
class Card:
    raw: dict[str, Any]

    @property
    def definition(self) -> dict[str, Any]:
        value = self.raw.get("definition", self.raw)
        return value if isinstance(value, dict) else {}

    @property
    def id(self) -> str:
        return str(self.raw.get("instanceId") or self.definition.get("id") or "")

    @property
    def name(self) -> str:
        return str(self.definition.get("name") or self.raw.get("name") or "Unknown card")

    @property
    def type_line(self) -> str:
        return str(self.definition.get("typeLine") or self.raw.get("typeLine") or "")

    @property
    def mana_cost(self) -> str:
        return str(self.definition.get("manaCost") or self.raw.get("manaCost") or "")

    @property
    def rules(self) -> list[Any]:
        rules = self.definition.get("rules", [])
        return list(rules) if isinstance(rules, list) else []

    @property
    def controller(self) -> str:
        return str(self.raw.get("controller") or "")

    @property
    def owner(self) -> str:
        return str(self.raw.get("owner") or "")

    @property
    def tapped(self) -> bool:
        return bool(self.raw.get("tapped"))

    @property
    def attached_to(self) -> str | None:
        value = self.raw.get("attachedTo")
        return str(value) if value else None

    @property
    def power(self) -> int:
        base = _integer(self.definition.get("power"))
        counters = self.raw.get("counters", {})
        plus = _integer(counters.get("+1/+1")) if isinstance(counters, dict) else 0
        minus = _integer(counters.get("-1/-1")) if isinstance(counters, dict) else 0
        return base + _integer(self.raw.get("powerModifier")) + plus - minus

    @property
    def toughness(self) -> int:
        base = _integer(self.definition.get("toughness"))
        counters = self.raw.get("counters", {})
        plus = _integer(counters.get("+1/+1")) if isinstance(counters, dict) else 0
        minus = _integer(counters.get("-1/-1")) if isinstance(counters, dict) else 0
        return base + _integer(self.raw.get("toughnessModifier")) + plus - minus

    def is_type(self, card_type: str) -> bool:
        return card_type.casefold() in self.type_line.casefold()

    def rules_contain(self, *kinds_or_text: str) -> bool:
        needles = {needle.casefold() for needle in kinds_or_text}
        for value in _walk(self.rules):
            if isinstance(value, str) and any(needle in value.casefold() for needle in needles):
                return True
        return False


@dataclass(frozen=True)
class Player:
    raw: dict[str, Any]

    @property
    def id(self) -> str:
        return str(self.raw.get("id") or "")

    @property
    def name(self) -> str:
        return str(self.raw.get("name") or self.id)

    @property
    def life(self) -> int:
        return _integer(self.raw.get("life"))

    @property
    def has_lost(self) -> bool:
        return bool(self.raw.get("hasLost"))

    def zone(self, name: str) -> list[Card]:
        cards = self.raw.get(name, [])
        if not isinstance(cards, list):
            return []
        return [Card(card) for card in cards if isinstance(card, dict)]

    @property
    def hand(self) -> list[Card]:
        return self.zone("hand")

    @property
    def battlefield(self) -> list[Card]:
        return self.zone("battlefield")

    @property
    def command_zone(self) -> list[Card]:
        return self.zone("commandZone")

    @property
    def untapped_mana_sources(self) -> list[Card]:
        return [
            card
            for card in self.battlefield
            if not card.tapped and (card.is_type("Land") or card.rules_contain("addMana"))
        ]

    @property
    def available_mana_count(self) -> int:
        pool = self.raw.get("manaPool", [])
        return len(self.untapped_mana_sources) + (len(pool) if isinstance(pool, list) else 0)


class Game:
    """Friendly, read-only helpers around the engine's visible observation."""

    ZONES = ("library", "hand", "battlefield", "graveyard", "exile", "sideboard", "commandZone")

    def __init__(self, observation: dict[str, Any], player_id: str) -> None:
        self.raw = observation
        self.player_id = player_id

    @property
    def turn(self) -> int:
        return _integer(self.raw.get("turnNumber"), 1)

    @property
    def step(self) -> str:
        return str(self.raw.get("step") or "")

    @property
    def players(self) -> list[Player]:
        values = self.raw.get("players", [])
        if not isinstance(values, list):
            return []
        return [Player(value) for value in values if isinstance(value, dict)]

    @property
    def me(self) -> Player:
        found = self.player(self.player_id)
        if found is None:
            raise ValueError(f"player {self.player_id!r} is absent from the observation")
        return found

    @property
    def opponents(self) -> list[Player]:
        return [
            player
            for player in self.players
            if player.id != self.player_id and not player.has_lost
        ]

    @property
    def active_player(self) -> Player | None:
        index = _integer(self.raw.get("activePlayer"), -1)
        return self.players[index] if 0 <= index < len(self.players) else None

    @property
    def is_my_turn(self) -> bool:
        return self.active_player is not None and self.active_player.id == self.player_id

    @property
    def stack(self) -> list[dict[str, Any]]:
        value = self.raw.get("stack", [])
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    def player(self, player_id: str) -> Player | None:
        return next((player for player in self.players if player.id == player_id), None)

    def cards(self) -> Iterable[Card]:
        for player in self.players:
            for zone in self.ZONES:
                yield from player.zone(zone)
        for item in self.stack:
            card = item.get("card")
            if isinstance(card, dict):
                yield Card(card)

    def card(self, instance_id: str | None) -> Card | None:
        if not instance_id:
            return None
        return next((card for card in self.cards() if card.id == instance_id), None)

    def permanent(self, instance_id: str | None) -> Card | None:
        if not instance_id:
            return None
        for player in self.players:
            found = next((card for card in player.battlefield if card.id == instance_id), None)
            if found is not None:
                return found
        return None
