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


def test_training_contract_rejects_values_the_learner_cannot_render() -> None:
    with pytest.raises(ValueError, match="metric kind"):
        TrainingMetric(key="loss", label="Loss", kind="histogram")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="default cannot exceed maximum"):
        TrainingParameter(
            key="rollout_games",
            label="Games per update",
            kind="integer",
            default=65,
            maximum=64,
        )
    with pytest.raises(ValueError, match="default must be one of"):
        TrainingParameter(
            key="device",
            label="Device",
            kind="choice",
            default="tpu",
            choices=("cpu", "cuda"),
        )


def test_training_parameter_keys_are_unique_across_phases() -> None:
    shared = TrainingParameter(
        key="seed",
        label="Seed",
        kind="integer",
        default=1,
    )

    with pytest.raises(ValueError, match="unique across phases"):
        TrainingContract(
            agent_id="org.example.agent",
            phases=(
                TrainingPhase("first", "First", parameters=(shared,)),
                TrainingPhase("second", "Second", parameters=(shared,)),
            ),
        )


def test_training_bridge_tracks_metric_steps_per_phase(tmp_path) -> None:
    multi_phase = TrainingContract(
        agent_id="org.example.agent",
        phases=(
            TrainingPhase(
                "first",
                "First",
                metrics=(TrainingMetric("score", "Score"),),
            ),
            TrainingPhase(
                "second",
                "Second",
                metrics=(TrainingMetric("score", "Score"),),
            ),
        ),
    )
    bridge = TrainingBridge(tmp_path, multi_phase)

    bridge.report_metrics(phase="first", step=10, metrics={"score": 1.0})
    bridge.report_metrics(phase="second", step=1, metrics={"score": 2.0})
    with pytest.raises(ValueError, match="within phase first"):
        bridge.report_metrics(phase="first", step=9, metrics={"score": 3.0})


@pytest.mark.parametrize("value", [True, float("nan"), float("inf")])
def test_training_bridge_rejects_non_json_metric_values(tmp_path, value) -> None:
    bridge = TrainingBridge(tmp_path, contract())

    with pytest.raises(ValueError, match="finite numbers"):
        bridge.report_metrics(phase="self-play", step=1, metrics={"policy_loss": value})
