from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part.title() for part in tail)


class ProtocolModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_camel,
        populate_by_name=True,
        extra="forbid",
    )


class ObservationStream(str, Enum):
    FULL = "full-observation-stream"
    DELTA = "delta-event-stream"


class TimeoutCategory(str, Enum):
    REALTIME = "realtime"
    STANDARD = "standard"
    EXTENDED = "extended"
    OFFLINE = "offline"


class GameSharing(str, Enum):
    PRIVATE = "private"
    RESULTS_ONLY = "results-only"
    PUBLIC_REPLAY = "public-replay"
    RESEARCH_DATASET = "research-dataset"
    TRAINING_DATASET = "training-dataset"


class AgentAuthor(ProtocolModel):
    name: str = Field(min_length=1)
    url: str | None = None


class AgentRepository(ProtocolModel):
    url: str = Field(min_length=1)
    commit: str | None = None
    license: str | None = None


class DeckSelection(ProtocolModel):
    selection: Literal["all", "allow-list"] = "all"
    deck_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_selection(self) -> DeckSelection:
        if self.selection == "allow-list" and not self.deck_ids:
            raise ValueError("allow-list requires at least one deck id")
        if self.selection == "all" and self.deck_ids:
            raise ValueError("all cannot include deck ids")
        return self


class AgentCompatibility(ProtocolModel):
    game_modes: list[str] = Field(min_length=1)
    decks: DeckSelection
    time_controls: list[TimeoutCategory] = Field(min_length=1)
    observation_streams: list[ObservationStream] = Field(min_length=1)
    game_sharing: list[GameSharing] = Field(min_length=1)


class AgentCapabilities(ProtocolModel):
    starting_situation_analysis: bool = False
    decision_exploration: bool = False
    stateful_memory: bool = False


class AgentManifest(ProtocolModel):
    schema_version: Literal["agent-manifest/v1"] = "agent-manifest/v1"
    agent_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str = ""
    agent_type: Literal[
        "deep_learning",
        "reinforcement_learning",
        "alpha_star",
        "rules_engine",
        "search",
        "hybrid",
        "human_ui",
        "other",
    ] = "other"
    authors: list[AgentAuthor] = Field(min_length=1)
    repository: AgentRepository | None = None
    compatibility: AgentCompatibility
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)


class RegistrationAccepted(ProtocolModel):
    type: Literal["registrationAccepted"]
    protocol_version: Literal["mtg-agent/v1"]
    agent_id: str
    controller_id: str
    observation_stream: ObservationStream
    timeout_category: TimeoutCategory
    decision_timeout_ms: int
    starting_analysis_timeout_ms: int
    game_sharing: GameSharing
    agent_version_id: str | None = None
    account_linked: bool = False


class StartingSituationRequest(ProtocolModel):
    type: Literal["startingSituationRequested"]
    schema_version: Literal["mtg-agent/v1"]
    request_id: str
    context_id: str
    deadline_unix_ms: int
    target_duration_ms: int
    analysis_duration_ms: int
    observation: dict[str, Any]
    known_deck: list[dict[str, Any]] = Field(default_factory=list)


class FullObservation(ProtocolModel):
    kind: Literal["fullObservation"]
    sequence: int
    observation: dict[str, Any]


class ObservationDelta(ProtocolModel):
    kind: Literal["observationDelta"]
    sequence: int
    previous_sequence: int
    patch: dict[str, Any]


class DecisionRequest(ProtocolModel):
    type: Literal["decisionRequested"]
    schema_version: Literal["mtg-agent/v1"]
    observation_schema_version: str
    request_id: str
    context_id: str
    player_id: str
    deadline_unix_ms: int
    observation_update: FullObservation | ObservationDelta = Field(discriminator="kind")
    decision: dict[str, Any]
    observation: dict[str, Any] = Field(default_factory=dict, exclude=True)


class DecisionResponse(ProtocolModel):
    action_id: str | None = None
    number_value: int | None = None
    card_instance_ids: list[str] | None = None

    @model_validator(mode="after")
    def contains_a_choice(self) -> DecisionResponse:
        if self.action_id is None and self.number_value is None and self.card_instance_ids is None:
            raise ValueError("a decision response must contain a choice")
        return self


class DecisionResolvedRequest(ProtocolModel):
    type: Literal["decisionResolved"]
    request_id: str
    action_id: str | None = None
    fallback_reason: str | None = None


class GameEventRequest(ProtocolModel):
    type: Literal["gameEvent"]
    context_id: str
    sequence: int
    event: dict[str, Any]


class GameEndedRequest(ProtocolModel):
    type: Literal["gameEnded"]
    context_id: str
    outcome: dict[str, Any]


class ProtocolError(ProtocolModel):
    type: Literal["error"]
    request_id: str | None = None
    code: str
    message: str
