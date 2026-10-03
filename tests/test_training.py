from __future__ import annotations

import json

import pytest

from deepdeck_agent import (
    TrainingBridge,
    TrainingContract,
    TrainingMetric,
    TrainingParameter,
    TrainingPhase,
)


def contract() -> TrainingContract:
    return TrainingContract(
        agent_id="org.example.legacy-agent",
        display_name="Legacy Scientist",
        phases=(
            TrainingPhase(
                phase_id="self-play",
                label="Legacy self-play",
                metrics=(
                    TrainingMetric(
                        key="policy_loss",
                        label="Policy loss",
                        kind="loss",
                        direction="minimize",
                        description="PPO clipped policy objective.",
                    ),
                    TrainingMetric(
                        key="engine_win_rate",
                        label="Engine win rate",
                        kind="rate",
                        direction="maximize",
                    ),
                ),
                parameters=(
                    TrainingParameter(
                        key="rollout_games",
                        label="Games per update",
                        kind="integer",
                        default=2,
                        minimum=1,
                        maximum=64,
                        apply="next-phase",
                    ),
                ),
                controls=("start", "pause", "resume", "stop", "evaluate"),
            ),
        ),
    )


def test_training_contract_serializes_for_deepdecklearner() -> None:
    payload = contract().to_dict()

    assert payload["schemaVersion"] == "deepdeck-agent-training/v1"
    assert payload["agentId"] == "org.example.legacy-agent"
    assert payload["phases"][0]["id"] == "self-play"
    assert payload["phases"][0]["metrics"][0]["direction"] == "minimize"
    assert payload["phases"][0]["parameters"][0]["min"] == 1


def test_training_bridge_publishes_state_metrics_and_reads_control(tmp_path) -> None:
    bridge = TrainingBridge(tmp_path, contract())
    bridge.report_state(phase="self-play", status="running", step=12)
    bridge.report_metrics(
        phase="self-play",
        step=12,
        metrics={"policy_loss": 0.25, "engine_win_rate": 0.6},
        context={"games": 20},
    )
    bridge.control_path.write_text(
        json.dumps(
            {
                "schemaVersion": "deepdeck-agent-training-control/v1",
                "revision": 3,
                "desiredState": "paused",
                "parameters": {"rollout_games": 4},
            }
        ),
        encoding="utf-8",
    )

    assert json.loads(bridge.contract_path.read_text())["agentId"] == contract().agent_id
    assert json.loads(bridge.state_path.read_text())["phase"] == "self-play"
    metric = json.loads(bridge.metrics_path.read_text().splitlines()[0])
    assert metric["metrics"]["engine_win_rate"] == 0.6
    assert bridge.requested_control()["revision"] == 3


def test_training_bridge_rejects_unknown_metrics(tmp_path) -> None:
    bridge = TrainingBridge(tmp_path, contract())

    with pytest.raises(ValueError, match="unknown metrics"):
        bridge.report_metrics(phase="self-play", step=1, metrics={"mystery": 1.0})
