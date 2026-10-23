from __future__ import annotations

import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, TypeGuard

MetricDirection = Literal["minimize", "maximize", "target", "neutral"]
MetricKind = Literal["loss", "reward", "rate", "count", "duration", "scalar"]
ParameterKind = Literal["integer", "number", "boolean", "string", "choice"]
ControlAction = Literal["start", "pause", "resume", "stop", "evaluate", "checkpoint"]
JsonValue = str | int | float | bool | None

_METRIC_KINDS = {"loss", "reward", "rate", "count", "duration", "scalar"}
_METRIC_DIRECTIONS = {"minimize", "maximize", "target", "neutral"}
_PARAMETER_KINDS = {"integer", "number", "boolean", "string", "choice"}
_CONTROL_ACTIONS = {"start", "pause", "resume", "stop", "evaluate", "checkpoint"}
_APPLY_BOUNDARIES = {"live", "next-phase", "next-run"}
_REPLAY_SUPPORT = {"none", "summary", "full"}


def _required(label: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} cannot be empty")


def _one_of(label: str, value: str, allowed: set[str]) -> None:
    if value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValueError(f"{label} must be one of: {choices}")


def _is_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_finite(label: str, value: int | float) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")


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
        _one_of("metric kind", self.kind, _METRIC_KINDS)
        _one_of("metric direction", self.direction, _METRIC_DIRECTIONS)


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
        _one_of("parameter kind", self.kind, _PARAMETER_KINDS)
        _one_of("parameter apply boundary", self.apply, _APPLY_BOUNDARIES)
        if self.kind == "choice" and not self.choices:
            raise ValueError("choice parameters require at least one choice")
        if self.kind == "integer" and (
            not isinstance(self.default, int) or isinstance(self.default, bool)
        ):
            raise ValueError("integer parameter defaults must be integers")
        if self.kind == "number" and not _is_number(self.default):
            raise ValueError("number parameter defaults must be numbers")
        if self.kind == "boolean" and not isinstance(self.default, bool):
            raise ValueError("boolean parameter defaults must be booleans")
        if self.kind == "string" and not isinstance(self.default, str):
            raise ValueError("string parameter defaults must be strings")
        if self.kind == "choice" and self.default not in self.choices:
            raise ValueError("choice parameter default must be one of its choices")
        for label, value in (
            ("parameter minimum", self.minimum),
            ("parameter maximum", self.maximum),
            ("parameter step", self.step),
        ):
            if value is not None:
                _validate_finite(label, value)
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError("parameter minimum cannot exceed maximum")
        if self.step is not None and self.step <= 0:
            raise ValueError("parameter step must be greater than zero")
        if _is_number(self.default):
            _validate_finite("parameter default", self.default)
            if self.minimum is not None and self.default < self.minimum:
                raise ValueError("parameter default cannot be less than minimum")
            if self.maximum is not None and self.default > self.maximum:
                raise ValueError("parameter default cannot exceed maximum")


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
        for control in self.controls:
            _one_of("training control", control, _CONTROL_ACTIONS)
        if len(self.controls) != len(set(self.controls)):
            raise ValueError(f"phase {self.phase_id} has duplicate controls")
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
        if self.schema_version != "deepdeck-agent-training/v1":
            raise ValueError("unsupported training contract schema version")
        _one_of("replay support", self.replay_support, _REPLAY_SUPPORT)
        if not self.phases:
            raise ValueError("a training contract requires at least one phase")
        phase_ids = [phase.phase_id for phase in self.phases]
        if len(phase_ids) != len(set(phase_ids)):
            raise ValueError("training phase ids must be unique")
        parameter_keys = [
            parameter.key for phase in self.phases for parameter in phase.parameters
        ]
        if len(parameter_keys) != len(set(parameter_keys)):
            raise ValueError("training parameter keys must be unique across phases")

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
    _last_metric_steps: dict[str, int] = field(default_factory=dict, init=False, repr=False)

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
        if not isinstance(step, int) or isinstance(step, bool) or step < 0:
            raise ValueError("training step must be a non-negative integer")
        if control_revision is not None and (
            not isinstance(control_revision, int)
            or isinstance(control_revision, bool)
            or control_revision < 0
        ):
            raise ValueError("control revision must be a non-negative integer")
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
        if not isinstance(step, int) or isinstance(step, bool) or step < 0:
            raise ValueError("metric step must be a non-negative integer")
        known_metrics = {metric.key for metric in phase_contract.metrics}
        unknown = sorted(set(metrics) - known_metrics)
        if unknown:
            raise ValueError(f"unknown metrics for phase {phase}: {', '.join(unknown)}")
        invalid_values = [
            key
            for key, value in metrics.items()
            if not _is_number(value) or not math.isfinite(value)
        ]
        if invalid_values:
            raise ValueError(
                "metric values must be finite numbers: " + ", ".join(sorted(invalid_values))
            )
        if step < self._last_metric_steps.get(phase, -1):
            raise ValueError(f"metric steps must be monotonic within phase {phase}")
        self._last_metric_steps[phase] = step
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
            stream.write(json.dumps(payload, allow_nan=False, sort_keys=True) + "\n")
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
        pending.write_text(
            json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        pending.replace(path)
