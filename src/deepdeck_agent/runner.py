from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, cast

import httpx

from .agent import Agent
from .client import AgentClient
from .config import AgentConfig, PlaySpeed, ServerTarget


@dataclass(frozen=True)
class LocalPlayer:
    player_id: str
    deck_session_id: str
    controller_id: str
    name: str | None = None
    starting_life: int = 20


@dataclass(frozen=True)
class LocalGame:
    players: tuple[LocalPlayer, ...]
    format: str = "legacy"
    seed: int = 1
    max_turns: int = 200
    mulligan_enabled: bool = True
    free_mulligans: int = 0
    max_mulligans: int | None = None
    starting_player: int = 0

    def payload(self) -> dict[str, Any]:
        return {
            "players": [
                {
                    "id": player.player_id,
                    "deckSessionId": player.deck_session_id,
                    "name": player.name,
                    "startingLife": player.starting_life,
                }
                for player in self.players
            ],
            "seed": self.seed,
            "gameMode": self.format,
            "maxTurns": self.max_turns,
            "startingPlayer": self.starting_player,
            "humanPlayerIds": [],
            "aiControllerByPlayerId": {
                player.player_id: player.controller_id for player in self.players
            },
            "mulliganEnabled": self.mulligan_enabled,
            "freeMulligans": self.free_mulligans,
            "maxMulligans": self.max_mulligans,
        }


@dataclass(frozen=True)
class MatchmakingEntry:
    competition_version_id: str
    agent_version_id: str
    deck_version_id: str


@dataclass
class AgentRunner:
    agent: Agent
    config: AgentConfig
    target: ServerTarget
    speed: PlaySpeed | None = None
    client: AgentClient = field(init=False)

    def __post_init__(self) -> None:
        selected_speed = self.speed or self.config.speeds[0]
        if selected_speed not in self.config.speeds:
            raise ValueError(f"{selected_speed.value} is not declared by this agent")
        self.speed = selected_speed
        self.client = AgentClient(
            self.target.agent_url,
            self.config.manifest(),
            self.agent,
            observation_stream=self.config.observation_stream,
            timeout_category=selected_speed.protocol_timeout,
            game_sharing=self.config.game_sharing,
            engine_api_key=self.target.engine_api_key,
            account_token=self.target.account_token,
        )

    async def serve(self, *, retry_seconds: float = 2.0) -> None:
        await self.client.run_forever(retry_seconds=retry_seconds)

    @property
    def controller_id(self) -> str:
        return self.client.controller_id or f"agent:{self.config.agent_id}"

    async def wait_until_connected(self, *, timeout: float = 10.0) -> str:
        """Wait until the engine confirms registration and return the controller ID."""

        async def wait() -> str:
            controller_id = self.client.controller_id
            while controller_id is None:
                await asyncio.sleep(0.05)
                controller_id = self.client.controller_id
            return controller_id

        return await asyncio.wait_for(wait(), timeout=timeout)

    async def start_local_game(self, game: LocalGame) -> dict[str, Any]:
        if self.target.kind != "local" or self.target.engine_http_url is None:
            raise ValueError("start_local_game requires ServerTarget.local()")
        headers = (
            {"x-mtg-api-key": self.target.engine_api_key}
            if self.target.engine_api_key
            else None
        )
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.target.engine_http_url}/game/sessions/from-local-decks",
                headers=headers,
                json=game.payload(),
            )
            response.raise_for_status()
            return cast(dict[str, Any], response.json())

    async def join_matchmaking(self, entry: MatchmakingEntry) -> dict[str, Any]:
        if self.target.kind != "deepdeckleague" or self.target.platform_url is None:
            raise ValueError("join_matchmaking requires ServerTarget.deepdeckleague()")
        if not self.target.account_token:
            raise ValueError("DEEPDECK_ACCESS_TOKEN is required for account-owned matchmaking")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.target.platform_url}/matchmaking/tickets",
                headers={"Authorization": f"Bearer {self.target.account_token}"},
                json={
                    "competitionVersionId": entry.competition_version_id,
                    "agentVersionId": entry.agent_version_id,
                    "deckVersionId": entry.deck_version_id,
                },
            )
            response.raise_for_status()
            payload = cast(dict[str, Any], response.json())
            return cast(dict[str, Any], payload.get("data", payload))
