from __future__ import annotations

from deepdeck_agent import ActionBinder, ActionIntent, Decision, Game


def test_action_binder_matches_structured_engine_targets() -> None:
    decision = Decision(
        "decision-1",
        "us",
        {
            "kind": "priority",
            "options": [
                {
                    "id": "wrong-target",
                    "kind": "castSpell",
                    "cardInstanceId": "bolt",
                    "targets": {"target": {"kind": "player", "playerId": "us"}},
                },
                {
                    "id": "right-target",
                    "kind": "castSpell",
                    "cardInstanceId": "bolt",
                    "targets": {"target": {"kind": "player", "playerId": "them"}},
                },
            ],
        },
        Game({"players": [{"id": "us"}, {"id": "them"}]}, "us"),
    )

    action = ActionBinder().bind(
        ActionIntent("castSpell", source_id="bolt", target_ids=("them",)), decision
    )

    assert action is not None
    assert action.id == "right-target"


def test_action_binder_never_returns_an_unauthorized_action_id() -> None:
    decision = Decision(
        "decision-2",
        "us",
        {"kind": "priority", "options": [{"id": "pass", "kind": "passPriority"}]},
        Game({"players": [{"id": "us"}]}, "us"),
    )

    action = ActionBinder().bind(
        ActionIntent("castSpell", engine_action_id="not-in-engine-options"), decision
    )

    assert action is None
