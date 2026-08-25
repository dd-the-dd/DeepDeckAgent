from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum

from .protocol import (
    AgentAuthor,
    AgentCapabilities,
    AgentCompatibility,
    AgentManifest,
    AgentRepository,
    DeckSelection,
    GameSharing,
    ObservationStream,
    TimeoutCategory,
)


class PlaySpeed(str, Enum):
    """The three public Deep Deck League rhythms."""

    MS_100 = "100ms"
    SECOND_1 = "1s"
    SECONDS_10 = "10s"

    @property
    def protocol_timeout(self) -> TimeoutCategory:
        # The engine grants a transport safety margin around the public clock.
        return {
            PlaySpeed.MS_100: TimeoutCategory.REALTIME,
            PlaySpeed.SECOND_1: TimeoutCategory.STANDARD,
            PlaySpeed.SECONDS_10: TimeoutCategory.EXTENDED,
        }[self]


@dataclass(frozen=True)
class DeckPolicy:
    deck_ids: tuple[str, ...] = ()

    @classmethod
    def all(cls) -> DeckPolicy:
        return cls()

    @classmethod
    def only(cls, deck_id: str) -> DeckPolicy:
        return cls((deck_id,))

    @classmethod
    def one_of(cls, *deck_ids: str) -> DeckPolicy:
        if not deck_ids:
            raise ValueError("one_of requires at least one deck id")
        return cls(tuple(dict.fromkeys(deck_ids)))

    def to_protocol(self) -> DeckSelection:
        if not self.deck_ids:
            return DeckSelection(selection="all")
        return DeckSelection(selection="allow-list", deck_ids=list(self.deck_ids))


@dataclass(frozen=True)
class AgentConfig:
    agent_id: str
    name: str
    version: str
    author: str
    formats: tuple[str, ...]
    decks: DeckPolicy = field(default_factory=DeckPolicy.all)
    speeds: tuple[PlaySpeed, ...] = (PlaySpeed.SECOND_1,)
    description: str = ""
    repository_url: str | None = None
    repository_commit: str | None = None
    observation_stream: ObservationStream = ObservationStream.FULL
    game_sharing: GameSharing = GameSharing.PUBLIC_REPLAY
    stateful_memory: bool = True

    def __post_init__(self) -> None:
        for label, value in (
            ("agent_id", self.agent_id),
            ("name", self.name),
            ("version", self.version),
            ("author", self.author),
        ):
            if not value.strip():
                raise ValueError(f"{label} cannot be empty")
        if not self.formats:
            raise ValueError("at least one format is required")
        if not self.speeds:
            raise ValueError("at least one play speed is required")

    def manifest(self) -> AgentManifest:
        timeouts = list(dict.fromkeys(speed.protocol_timeout for speed in self.speeds))
        repository = None
        if self.repository_url:
            repository = AgentRepository(
                url=self.repository_url,
                commit=self.repository_commit,
                license="MIT",
            )
        return AgentManifest(
            agent_id=self.agent_id,
            name=self.name,
            version=self.version,
            description=self.description,
            authors=[AgentAuthor(name=self.author)],
            repository=repository,
            compatibility=AgentCompatibility(
                game_modes=list(self.formats),
                decks=self.decks.to_protocol(),
                time_controls=timeouts,
                observation_streams=[self.observation_stream],
                game_sharing=[self.game_sharing],
            ),
            capabilities=AgentCapabilities(
                starting_situation_analysis=True,
                stateful_memory=self.stateful_memory,
            ),
        )


@dataclass(frozen=True)
class ServerTarget:
    kind: str
    agent_url: str
    engine_http_url: str | None = None
    platform_url: str | None = None
    engine_api_key: str | None = None
    account_token: str | None = None

    @classmethod
    def local(
        cls,
        engine_url: str = "http://127.0.0.1:8787",
        *,
        api_key: str | None = None,
    ) -> ServerTarget:
        http_url = engine_url.rstrip("/")
        websocket_scheme = "wss" if http_url.startswith("https://") else "ws"
        host = http_url.split("://", 1)[-1]
        return cls(
            kind="local",
            agent_url=f"{websocket_scheme}://{host}/ai/agents/ws",
            engine_http_url=http_url,
            engine_api_key=api_key or os.getenv("MTG_ENGINE_API_KEY") or None,
        )

    @classmethod
    def deepdeckleague(
        cls,
        *,
        agent_url: str | None = None,
        platform_url: str | None = None,
        account_token: str | None = None,
    ) -> ServerTarget:
        resolved_agent_url = agent_url or os.getenv("DEEPDECK_AGENT_URL", "").strip()
        if not resolved_agent_url:
            raise ValueError(
                "DEEPDECK_AGENT_URL is required until the public runner endpoint is deployed"
            )
        return cls(
            kind="deepdeckleague",
            agent_url=resolved_agent_url,
            platform_url=(
                platform_url
                or os.getenv("DEEPDECK_PLATFORM_URL")
                or "https://staging.deepdeckleague.com/api/v1"
            ).rstrip("/"),
            account_token=account_token or os.getenv("DEEPDECK_ACCESS_TOKEN") or None,
        )

