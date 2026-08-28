from __future__ import annotations

import asyncio
from typing import Any

import pytest

from deepdeck_agent import (
    Agent,
    AgentConfig,
    AgentRunner,
    MatchmakingEntry,
    ServerTarget,
)


def runner() -> AgentRunner:
    return AgentRunner(
        Agent(),
        AgentConfig(
            agent_id="example-agent",
            name="Example",
            version="1.0.0",
            author="Tester",
            formats=("legacy",),
        ),
        ServerTarget.deepdeckleague(api_key="ddl_agent_test"),
    )


async def test_serve_matchmaking_connects_before_joining(monkeypatch) -> None:
    subject = runner()
    order: list[str] = []
    keep_serving = asyncio.Event()

    async def serve(*, retry_seconds: float = 2.0) -> None:
        del retry_seconds
        order.append("serve")
        await keep_serving.wait()

    async def wait_until_connected(*, timeout: float = 10.0) -> str:
        del timeout
        order.append("connected")
        return "agent:example-agent"

    async def join_matchmaking(entry: MatchmakingEntry) -> dict[str, Any]:
        assert entry.deck_version_id == "deck-version"
        order.append("join")
        return {"id": "ticket", "status": "queued"}

    async def wait_for_match_id(ticket: dict[str, Any], poll_seconds: float) -> str:
        assert ticket["id"] == "ticket"
        del poll_seconds
        order.append("matched")
        return "match"

    async def wait_for_match_end(match_id: str, poll_seconds: float) -> str:
        assert match_id == "match"
        del poll_seconds
        order.append("complete")
        return "complete"

    monkeypatch.setattr(subject, "serve", serve)
    monkeypatch.setattr(subject, "wait_until_connected", wait_until_connected)
    monkeypatch.setattr(subject, "join_matchmaking", join_matchmaking)
    monkeypatch.setattr(subject, "_wait_for_match_id", wait_for_match_id)
    monkeypatch.setattr(subject, "_wait_for_match_end", wait_for_match_end)
    await subject.serve_matchmaking(
        MatchmakingEntry("competition", "deck-version"),
        continuous=False,
    )

    assert order == ["serve", "connected", "join", "matched", "complete"]
    assert subject.matchmaking_ticket == {"id": "ticket", "status": "queued"}


async def test_serve_matchmaking_requeues_after_match_completion(monkeypatch) -> None:
    subject = runner()
    keep_serving = asyncio.Event()
    joins = 0

    async def serve(*, retry_seconds: float = 2.0) -> None:
        del retry_seconds
        await keep_serving.wait()

    async def wait_until_connected(*, timeout: float = 10.0) -> str:
        del timeout
        return "agent:example-agent"

    async def join_matchmaking(entry: MatchmakingEntry) -> dict[str, Any]:
        nonlocal joins
        del entry
        joins += 1
        return {"id": f"ticket-{joins}", "status": "matched", "matchId": "match"}

    async def wait_for_match_id(ticket: dict[str, Any], poll_seconds: float) -> str:
        del ticket, poll_seconds
        return "match"

    async def wait_for_match_end(match_id: str, poll_seconds: float) -> str:
        del match_id, poll_seconds
        return "complete"

    monkeypatch.setattr(subject, "serve", serve)
    monkeypatch.setattr(subject, "wait_until_connected", wait_until_connected)
    monkeypatch.setattr(subject, "join_matchmaking", join_matchmaking)
    monkeypatch.setattr(subject, "_wait_for_match_id", wait_for_match_id)
    monkeypatch.setattr(subject, "_wait_for_match_end", wait_for_match_end)
    task = asyncio.create_task(
        subject.serve_matchmaking(
            MatchmakingEntry("competition", "deck-version"),
            requeue_seconds=0,
        )
    )
    while joins < 2:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert joins >= 2


async def test_match_end_reads_the_public_match_summary(monkeypatch) -> None:
    subject = runner()

    async def match(match_id: str) -> dict[str, Any]:
        assert match_id == "match"
        return {"summary": {"status": "complete"}, "games": []}

    monkeypatch.setattr(subject, "match", match)

    assert await subject._wait_for_match_end("match", 0) == "complete"
