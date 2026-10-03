import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from deepdeck_agent.protocol import AgentManifest

FIXTURE = Path(__file__).parent / "fixtures" / "agent_manifest_v1_maximal.json"


def maximal_manifest_payload() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_maximal_manifest_round_trips_with_protocol_aliases() -> None:
    payload = maximal_manifest_payload()

    manifest = AgentManifest.model_validate(payload)

    assert manifest.model_dump(by_alias=True, mode="json", exclude_none=True) == payload


@pytest.mark.parametrize(
    ("path", "extra"),
    [
        ((), {"unexpected": True}),
        (("authors", 0), {"affiliation": "Example University"}),
        (("publications", 0), {"abstract": "Not part of agent-manifest/v1"}),
    ],
)
def test_manifest_rejects_unknown_fields_at_every_protocol_level(
    path: tuple[str | int, ...], extra: dict[str, object]
) -> None:
    payload = maximal_manifest_payload()
    target: object = payload
    for part in path:
        target = target[part]  # type: ignore[index]
    assert isinstance(target, dict)
    target.update(extra)

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AgentManifest.model_validate(payload)
