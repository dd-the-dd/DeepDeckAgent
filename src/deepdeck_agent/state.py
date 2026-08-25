from __future__ import annotations

from copy import deepcopy
from typing import Any


def apply_merge_patch(target: Any, patch: Any) -> Any:
    """Apply RFC 7396 without mutating the caller's observation."""
    if not isinstance(patch, dict):
        return deepcopy(patch)
    result = deepcopy(target) if isinstance(target, dict) else {}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = apply_merge_patch(result.get(key), value)
    return result


class ObservationReplica:
    """Keeps a full local state while the server sends compact deltas."""

    def __init__(self) -> None:
        self.sequence = 0
        self.observation: dict[str, Any] = {}

    def replace(self, sequence: int, observation: dict[str, Any]) -> dict[str, Any]:
        self.sequence = sequence
        self.observation = deepcopy(observation)
        return deepcopy(self.observation)

    def apply(self, sequence: int, previous_sequence: int, patch: dict[str, Any]) -> dict[str, Any]:
        if previous_sequence != self.sequence:
            raise ValueError(
                f"observation delta expected sequence {self.sequence}, received {previous_sequence}"
            )
        self.observation = apply_merge_patch(self.observation, patch)
        self.sequence = sequence
        return deepcopy(self.observation)

