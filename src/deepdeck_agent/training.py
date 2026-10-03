from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

MetricDirection = Literal["minimize", "maximize", "target", "neutral"]
MetricKind = Literal["loss", "reward", "rate", "count", "duration", "scalar"]
ParameterKind = Literal["integer", "number", "boolean", "string", "choice"]
ControlAction = Literal["start", "pause", "resume", "stop", "evaluate", "checkpoint"]
JsonValue = str | int | float | bool | None


def _required(label: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} cannot be empty")


@dataclass(frozen=True)
class TrainingMetric:
    """One agent-defined metric that a learner UI can render generically."""

    key: str
    label: str
    kind: MetricKind = "scalar"
    direction: MetricDirection = "neutral"
    unit: str = ""
    description: str = ""
    group: str = "training"

    def __post_init__(self) -> None:
        _required("metric key", self.key)
        _required("metric label", self.label)


@dataclass(frozen=True)
class TrainingParameter:
    """A typed training control owned and validated by the agent."""

    key: str
    label: str
    kind: ParameterKind
    default: JsonValue
    description: str = ""
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    choices: tuple[JsonValue, ...] = ()
    apply: Literal["live", "next-phase", "next-run"] = "next-run"

    def __post_init__(self) -> None:
        _required("parameter key", self.key)
        _required("parameter label", self.label)
        if self.kind == "choice" and not self.choices:
            raise ValueError("choice parameters require at least one choice")
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError("parameter minimum cannot exceed maximum")


@dataclass(frozen=True)
class TrainingPhase:
    """A model-specific phase exposed through the common training contract."""

    phase_id: str
    label: str
    description: str = ""
    metrics: tuple[TrainingMetric, ...] = ()
    parameters: tuple[TrainingParameter, ...] = ()
    controls: tuple[ControlAction, ...] = ("start", "pause", "resume", "stop")

    def __post_init__(self) -> None:
        _required("phase id", self.phase_id)
        _required("phase label", self.label)
        metric_keys = [metric.key for metric in self.metrics]
        parameter_keys = [parameter.key for parameter in self.parameters]
        if len(metric_keys) != len(set(metric_keys)):
            raise ValueError(f"phase {self.phase_id} has duplicate metric keys")
        if len(parameter_keys) != len(set(parameter_keys)):
            raise ValueError(f"phase {self.phase_id} has duplicate parameter keys")


@dataclass(frozen=True)
class TrainingContract:
    """Versioned description of how an agent trains and can be controlled."""

    agent_id: str
    phases: tuple[TrainingPhase, ...]
    schema_version: str = "deepdeck-agent-training/v1"
    display_name: str = ""
    owns_curriculum: bool = True
    owns_promotion_criteria: bool = True
    proposes_experiments: bool = True
    replay_support: Literal["none", "summary", "full"] = "full"

    def __post_init__(self) -> None:
        _required("agent id", self.agent_id)
        if not self.phases:
            raise ValueError("a training contract requires at least one phase")
        phase_ids = [phase.phase_id for phase in self.phases]
        if len(phase_ids) != len(set(phase_ids)):
            raise ValueError("training phase ids must be unique")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["schemaVersion"] = value.pop("schema_version")
        value["agentId"] = value.pop("agent_id")
        value["displayName"] = value.pop("display_name")
        value["ownsCurriculum"] = value.pop("owns_curriculum")
        value["ownsPromotionCriteria"] = value.pop("owns_promotion_criteria")
        value["proposesExperiments"] = value.pop("proposes_experiments")
        value["replaySupport"] = value.pop("replay_support")
        for phase in value["phases"]:
            phase["id"] = phase.pop("phase_id")
            for parameter in phase["parameters"]:
                parameter["min"] = parameter.pop("minimum")
                parameter["max"] = parameter.pop("maximum")
        return value


@dataclass
class TrainingBridge:
    """Filesystem bridge between an agent scientist and DeepDeckLearner.

    The agent owns the algorithms and periodically reads the requested control
    document. DeepDeckLearner owns orchestration and writes desired state or
    parameter changes without importing model-specific code.
    """

    workspace: Path
    contract: TrainingContract
    _last_metric_step: int = field(default=-1, init=False, repr=False)

    def __post_init__(self) -> None:
        self.workspace = Path(self.workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.publish_contract()

    @property
    def contract_path(self) -> Path:
        return self.workspace / "agent-training-contract.json"

    @property
    def state_path(self) -> Path:
        return self.workspace / "agent-training-state.json"

    @property
    def metrics_path(self) -> Path:
        return self.workspace / "agent-training-metrics.jsonl"

    @property
    def control_path(self) -> Path:
        return self.workspace / "agent-training-control.json"

    def publish_contract(self) -> None:
        self._write_json(self.contract_path, self.contract.to_dict())

    def report_state(
        self,
        *,
        phase: str,
        status: Literal["idle", "running", "paused", "completed", "failed"],
        step: int,
        control_revision: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if phase not in {item.phase_id for item in self.contract.phases}:
            raise ValueError(f"unknown training phase: {phase}")
        payload: dict[str, Any] = {
            "schemaVersion": "deepdeck-agent-training-state/v1",
            "agentId": self.contract.agent_id,
            "phase": phase,
            "status": status,
            "step": int(step),
            "updatedAtUnixMs": int(time.time() * 1000),
        }
        if control_revision is not None:
            payload["controlRevision"] = int(control_revision)
        if details:
            payload["details"] = details
        self._write_json(self.state_path, payload)

    def report_metrics(
        self,
        *,
        phase: str,
        step: int,
        metrics: dict[str, int | float],
        context: dict[str, Any] | None = None,
    ) -> None:
        phase_contract = next(
            (item for item in self.contract.phases if item.phase_id == phase), None
        )
        if phase_contract is None:
            raise ValueError(f"unknown training phase: {phase}")
        known_metrics = {metric.key for metric in phase_contract.metrics}
        unknown = sorted(set(metrics) - known_metrics)
        if unknown:
            raise ValueError(f"unknown metrics for phase {phase}: {', '.join(unknown)}")
        if step < self._last_metric_step:
            raise ValueError("metric steps must be monotonic")
        self._last_metric_step = step
        payload: dict[str, Any] = {
            "schemaVersion": "deepdeck-agent-training-metrics/v1",
            "agentId": self.contract.agent_id,
            "phase": phase,
            "step": int(step),
            "metrics": metrics,
            "recordedAtUnixMs": int(time.time() * 1000),
        }
        if context:
            payload["context"] = context
        with self.metrics_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, sort_keys=True) + "\n")
            stream.flush()

    def requested_control(self) -> dict[str, Any] | None:
        try:
            value = json.loads(self.control_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        pending = path.with_suffix(path.suffix + f".{os.getpid()}.pending")
        pending.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        pending.replace(path)
