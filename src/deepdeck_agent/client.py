from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from websockets.asyncio.client import ClientConnection, connect

from .agent import Agent
from .decisions import Decision
from .events import EventReader
from .protocol import (
    AgentManifest,
    DecisionRequest,
    DecisionResolvedRequest,
    DecisionResponse,
    FullObservation,
    GameEndedRequest,
    GameEventRequest,
    GameSharing,
    ObservationStream,
    RegistrationAccepted,
    StartingSituationRequest,
    TimeoutCategory,
)
from .state import ObservationReplica
from .views import Game

LOGGER = logging.getLogger("deepdeck_agent")


class AgentClient:
    """Maintains the WebSocket, visible states, deadlines and typed callbacks."""

    def __init__(
        self,
        url: str,
        manifest: AgentManifest,
        agent: Agent,
        *,
        observation_stream: ObservationStream,
        timeout_category: TimeoutCategory,
        game_sharing: GameSharing = GameSharing.PUBLIC_REPLAY,
        engine_api_key: str | None = None,
        account_token: str | None = None,
    ) -> None:
        compatibility = manifest.compatibility
        if observation_stream not in compatibility.observation_streams:
            raise ValueError("observation stream is not declared by the manifest")
        if timeout_category not in compatibility.time_controls:
            raise ValueError("timeout category is not declared by the manifest")
        if game_sharing not in compatibility.game_sharing:
            raise ValueError("sharing mode is not declared by the manifest")
        self.url = url
        self.manifest = manifest
        self.agent = agent
        self.observation_stream = observation_stream
        self.timeout_category = timeout_category
        self.game_sharing = game_sharing
        self.engine_api_key = engine_api_key
        self.account_token = account_token
        self.registration: RegistrationAccepted | None = None
        self._socket: ClientConnection | None = None
        self._send_lock = asyncio.Lock()
        self._replicas: dict[str, ObservationReplica] = {}
        self._events = EventReader()
        self._known_decks: dict[str, list[dict[str, Any]]] = {}
        self._started_contexts: set[str] = set()
        self._ended_contexts: set[str] = set()

    @property
    def controller_id(self) -> str | None:
        return self.registration.controller_id if self.registration else None

    async def _send(self, payload: dict[str, Any]) -> None:
        if self._socket is None:
            raise RuntimeError("agent is not connected")
        async with self._send_lock:
            await self._socket.send(json.dumps(payload, separators=(",", ":")))

    async def _starting(self, payload: dict[str, Any]) -> None:
        request = StartingSituationRequest.model_validate(payload)
        self._known_decks[request.context_id] = request.known_deck
        remaining = max(0.001, request.deadline_unix_ms / 1000 - time.time())
        await asyncio.wait_for(
            self.agent.analyze_starting_situation(request.observation, request.known_deck),
            timeout=remaining,
        )
        await self._send(
            {
                "type": "startingSituationCompleted",
                "requestId": request.request_id,
            }
        )

    async def _notify_state(
        self,
        context_id: str,
        player_id: str,
        observation: dict[str, Any],
    ) -> Game:
        game = Game(observation, player_id)
        if context_id not in self._started_contexts:
            self._started_contexts.add(context_id)
            await self.agent.on_game_start(game, self._known_decks.get(context_id, []))
        await self.agent.on_observation(game)
        for event in self._events.read(context_id, observation):
            await self.agent.on_event(event, game)
        outcome = observation.get("outcome")
        if isinstance(outcome, dict) and context_id not in self._ended_contexts:
            self._ended_contexts.add(context_id)
            await self.agent.on_game_end(outcome)
        return game

    async def _decision(self, payload: dict[str, Any]) -> None:
        request = DecisionRequest.model_validate(payload)
        replica = self._replicas.setdefault(request.context_id, ObservationReplica())
        update = request.observation_update
        if isinstance(update, FullObservation):
            observation = replica.replace(update.sequence, update.observation)
        else:
            observation = replica.apply(update.sequence, update.previous_sequence, update.patch)
        game = await self._notify_state(request.context_id, request.player_id, observation)
        decision = Decision(request.request_id, request.player_id, request.decision, game)
        remaining = max(0.001, request.deadline_unix_ms / 1000 - time.time())
        response = await asyncio.wait_for(self.agent.make_decision(decision), timeout=remaining)
        if not isinstance(response, DecisionResponse):
            response = DecisionResponse.model_validate(response)
        await self._send(
            {
                "type": "decisionSubmitted",
                "requestId": request.request_id,
                **response.model_dump(by_alias=True, exclude_none=True),
            }
        )

    async def _dispatch(self, payload: dict[str, Any]) -> None:
        message_type = payload.get("type")
        if message_type == "startingSituationRequested":
            await self._starting(payload)
        elif message_type == "decisionRequested":
            await self._decision(payload)
        elif message_type == "gameEvent":
            event_request = GameEventRequest.model_validate(payload)
            event = self._events.push(
                event_request.context_id,
                event_request.sequence,
                event_request.event,
            )
            replica = self._replicas.get(event_request.context_id)
            if event is not None and replica is not None:
                players = replica.observation.get("players", [])
                player_id = str(players[0].get("id", "")) if players else ""
                await self.agent.on_event(event, Game(replica.observation, player_id))
        elif message_type == "decisionResolved":
            await self.agent.on_decision_resolved(DecisionResolvedRequest.model_validate(payload))
        elif message_type == "gameEnded":
            end_request = GameEndedRequest.model_validate(payload)
            if end_request.context_id not in self._ended_contexts:
                self._ended_contexts.add(end_request.context_id)
                await self.agent.on_game_end(end_request.outcome)
        elif message_type == "ping":
            await self._send({"type": "pong", "requestId": payload.get("requestId")})
        elif message_type == "error":
            raise RuntimeError(
                f"agent protocol error {payload.get('code')}: {payload.get('message')}"
            )

    def _headers(self) -> dict[str, str] | None:
        headers: dict[str, str] = {}
        if self.engine_api_key:
            headers["x-mtg-api-key"] = self.engine_api_key
        if self.account_token:
            headers["Authorization"] = f"Bearer {self.account_token}"
        return headers or None

    async def run_once(self) -> None:
        async with connect(
            self.url,
            ping_interval=20,
            ping_timeout=20,
            additional_headers=self._headers(),
            max_size=32 * 1024 * 1024,
        ) as socket:
            self._socket = socket
            await self._send(
                {
                    "type": "registerAgent",
                    "protocolVersion": "mtg-agent/v1",
                    "manifest": self.manifest.model_dump(by_alias=True, mode="json"),
                    "observationStream": self.observation_stream.value,
                    "timeoutCategory": self.timeout_category.value,
                    "gameSharing": self.game_sharing.value,
                }
            )
            first = json.loads(await socket.recv())
            if first.get("type") == "error":
                raise RuntimeError(f"registration failed: {first.get('message', 'unknown error')}")
            self.registration = RegistrationAccepted.model_validate(first)
            async for raw in socket:
                await self._dispatch(json.loads(raw))
        self._socket = None

    async def run_forever(
        self,
        *,
        retry_seconds: float = 2.0,
        on_connected: Callable[[RegistrationAccepted], Awaitable[None]] | None = None,
    ) -> None:
        while True:
            try:
                task = asyncio.create_task(self.run_once())
                while self.registration is None and not task.done():
                    await asyncio.sleep(0.05)
                if self.registration is not None and on_connected is not None:
                    await on_connected(self.registration)
                await task
                raise ConnectionError("the engine closed the agent connection")
            except asyncio.CancelledError:
                raise
            except Exception as error:
                LOGGER.warning("agent disconnected (%s); retrying in %.1fs", error, retry_seconds)
                self.registration = None
                self._socket = None
                await asyncio.sleep(retry_seconds)
