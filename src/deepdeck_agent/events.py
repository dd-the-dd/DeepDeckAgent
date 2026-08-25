from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Event:
    sequence: int
    kind: str
    turn: int
    step: str
    player_id: str | None
    card_instance_id: str | None
    detail: dict[str, Any]
    raw: dict[str, Any]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Event:
        detail = raw.get("detail", {})
        return cls(
            sequence=int(raw.get("sequence", 0)),
            kind=str(raw.get("kind", "unknown")),
            turn=int(raw.get("turnNumber", 0)),
            step=str(raw.get("step", "")),
            player_id=str(raw["playerId"]) if raw.get("playerId") else None,
            card_instance_id=(
                str(raw["cardInstanceId"]) if raw.get("cardInstanceId") else None
            ),
            detail=detail if isinstance(detail, dict) else {"value": detail},
            raw=raw,
        )


class EventReader:
    """Returns each visible state event exactly once, in sequence order."""

    def __init__(self) -> None:
        self._last_sequence_by_context: dict[str, int] = {}

    def read(self, context_id: str, observation: dict[str, Any]) -> list[Event]:
        raw_events = observation.get("events", [])
        if not isinstance(raw_events, list):
            return []
        last = self._last_sequence_by_context.get(context_id, 0)
        events = sorted(
            (
                Event.from_dict(raw)
                for raw in raw_events
                if isinstance(raw, dict) and int(raw.get("sequence", 0)) > last
            ),
            key=lambda event: event.sequence,
        )
        if events:
            self._last_sequence_by_context[context_id] = events[-1].sequence
        return events

    def push(self, context_id: str, sequence: int, raw: dict[str, Any]) -> Event | None:
        last = self._last_sequence_by_context.get(context_id, 0)
        if sequence <= last:
            return None
        self._last_sequence_by_context[context_id] = sequence
        return Event.from_dict({"sequence": sequence, **raw})

