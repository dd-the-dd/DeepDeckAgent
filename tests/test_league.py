from __future__ import annotations

import asyncio
import copy
import json
from typing import Any
from uuid import uuid4

import httpx
import pytest

from deepdeck_agent import (
    Agent,
    AgentConfig,
    AgentRunner,
    LeagueClient,
    LeagueCompatibilityError,
    LeagueEntryConflict,
    LeagueEventEntry,
    LeagueMutationUncertain,
    LeagueUnavailableError,
    MatchmakingEntry,
    ServerTarget,
)

AGENT, DECK, OTHER, ENVIRONMENT, EVENT, NEXT = (str(uuid4()) for _ in range(6))


def event(*, id: str = EVENT, phase: str = "registration", **overrides: Any) -> dict[str, Any]:
    return {
        "id": id,
        "competitionVersionId": ENVIRONMENT,
        "format": "legacy",
        "phase": phase,
        "executionEnabled": True,
        "serverNow": "2026-10-21T12:00:00Z",
        "registrationOpensAt": "2026-10-21T11:45:00Z",
        "registrationClosesAt": "2026-10-21T12:15:00Z",
        "ownEntry": None,
        "ownMatches": [],
        **overrides,
    }


def own(**overrides: Any) -> dict[str, Any]:
    return {"agentVersionId": AGENT, "deckVersionId": DECK, "withdrawnAt": None, **overrides}


def target() -> ServerTarget:
    return ServerTarget.deepdeckleague(
        platform_url="https://league.test/api/v1", api_key="ddl_agent_sdk_test_only"
    )


def api(handler: Any) -> tuple[LeagueClient, httpx.AsyncClient]:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return LeagueClient(target(), agent_version_id=AGENT, http_client=client), client


def response(data: Any) -> httpx.Response:
    return httpx.Response(200, json={"data": data})


@pytest.mark.asyncio
async def test_multi_agent_event_selects_only_connected_agents_entry_and_matches() -> None:
    mine, theirs, match = str(uuid4()), str(uuid4()), str(uuid4())
    current = event(
        entryIdentity="agent-v1",
        ownEntry=None,
        ownEntries=[own(participantId=theirs, agentVersionId=OTHER), own(participantId=mine)],
        ownMatches=[
            {"matchId": match, "participantId": theirs, "agentVersionId": OTHER},
            {"matchId": match, "participantId": mine, "agentVersionId": AGENT},
        ],
    )
    league, client = api(lambda request: response(copy.deepcopy(current)))
    async with client:
        result = await league.event(EVENT)
        assert result["ownEntry"]["participantId"] == mine
        assert result["ownMatches"] == [
            {"matchId": match, "participantId": mine, "agentVersionId": AGENT}
        ]


@pytest.mark.asyncio
async def test_multi_agent_join_does_not_replace_another_owned_agent() -> None:
    other_entry, my_entry = str(uuid4()), str(uuid4())
    current = event(
        entryIdentity="agent-v1",
        ownEntry=own(agentVersionId=OTHER),
        ownEntries=[own(participantId=other_entry, agentVersionId=OTHER)],
    )
    writes = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            writes.append(json.loads(request.content))
            current["ownEntries"].append(own(participantId=my_entry))
        return response(copy.deepcopy(current))

    league, client = api(handle)
    async with client:
        result = await league.join(EVENT, LeagueEventEntry("legacy", DECK))
        assert result["ownEntry"]["participantId"] == my_entry
        assert len(current["ownEntries"]) == 2
        assert writes == [{"agentVersionId": AGENT, "deckVersionId": DECK}]
        await league.join(EVENT, LeagueEventEntry("legacy", DECK))
        assert len(writes) == 1


@pytest.mark.asyncio
async def test_multi_agent_withdrawal_targets_only_this_registration() -> None:
    selected, other = str(uuid4()), str(uuid4())
    current = event(
        entryIdentity="agent-v1",
        ownEntries=[own(participantId=other, agentVersionId=OTHER), own(participantId=selected)],
    )
    removed = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            removed.append(request.url.params.get("entryId"))
        return response(copy.deepcopy(current))

    league, client = api(handle)
    async with client:
        await league.withdraw(EVENT)
    assert removed == [selected]


@pytest.mark.asyncio
async def test_multi_agent_contract_cannot_silently_fall_back_to_another_agent() -> None:
    requests = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request.method)
        return response(event(entryIdentity="agent-v1", ownEntry=own()))

    league, client = api(handle)
    async with client:
        with pytest.raises(LeagueCompatibilityError):
            await league.join(EVENT, LeagueEventEntry("legacy", DECK))
    assert requests == ["GET"]


@pytest.mark.parametrize("format", ["legacy", "commander"])
async def test_join_uses_server_entry_snapshot_and_assigned_agent_version(format: str) -> None:
    current = event(format=format)
    methods = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        assert request.headers["Authorization"] == "Bearer ddl_agent_sdk_test_only"
        assert "ddl_agent_" not in str(request.url)
        assert request.url.path == f"/api/v1/progression/events/{EVENT}" + (
            "/entry" if request.method == "POST" else ""
        )
        if request.method == "POST":
            body = json.loads(request.content)
            assert body == {"agentVersionId": AGENT, "deckVersionId": DECK}
            current["ownEntry"] = own()
            return response({"registered": True})
        return response(current)

    league, http = api(handler)
    try:
        result = await league.join(EVENT, LeagueEventEntry(format, DECK))
        assert result["ownEntry"]["deckVersionId"] == DECK
        assert methods == ["GET", "POST", "GET"]
        await league.join(EVENT, LeagueEventEntry(format, DECK))
        assert methods == ["GET", "POST", "GET", "GET"]  # resume, not a replacement
    finally:
        await http.aclose()


async def test_lost_post_ack_is_reconciled_without_repeating_the_write() -> None:
    current = event()
    posts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal posts
        if request.method == "POST":
            posts += 1
            current["ownEntry"] = own()
            raise httpx.ReadTimeout("simulated lost acknowledgement", request=request)
        return response(current)

    league, http = api(handler)
    try:
        assert (await league.join(EVENT, LeagueEventEntry("legacy", DECK)))["ownEntry"] == own()
        assert posts == 1
    finally:
        await http.aclose()


async def test_unknown_post_result_is_actionable_and_never_replayed() -> None:
    methods = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "POST":
            return httpx.Response(503, json={"error": {"message": "not confirmed"}})
        return response(event())

    league, http = api(handler)
    try:
        with pytest.raises(LeagueMutationUncertain, match="no write was repeated"):
            await league.join(EVENT, LeagueEventEntry("legacy", DECK))
        assert methods == ["GET", "POST", "GET"]
    finally:
        await http.aclose()


@pytest.mark.parametrize("status", [400, 401, 403, 409, 429])
async def test_join_never_retries_a_rejected_write(status: int) -> None:
    methods = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return (
            httpx.Response(status, json={"error": {"message": "denied"}})
            if request.method == "POST"
            else response(event())
        )

    league, http = api(handler)
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await league.join(EVENT, LeagueEventEntry("legacy", DECK))
        assert methods == ["GET", "POST"]
    finally:
        await http.aclose()


@pytest.mark.parametrize(
    "current",
    [
        event(ownEntry=own(agentVersionId=OTHER)),
        event(ownEntry=own(deckVersionId=OTHER)),
        event(format="commander"),
        event(competitionVersionId=OTHER),
        event(phase="season"),
    ],
)
async def test_does_not_replace_other_entries_or_choose_another_environment(
    current: dict[str, Any],
) -> None:
    methods = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return response(current)

    league, http = api(handler)
    try:
        with pytest.raises(LeagueEntryConflict):
            await league.join(
                EVENT, LeagueEventEntry("legacy", DECK, competition_version_id=ENVIRONMENT)
            )
        assert methods == ["GET"]
    finally:
        await http.aclose()


async def test_picks_a_published_deck_once_per_event_not_each_match(monkeypatch: Any) -> None:
    current = event()
    calls = []

    def choose(pool: tuple[str, ...]) -> str:
        calls.append(pool)
        return OTHER

    monkeypatch.setattr("deepdeck_agent.league.secrets.choice", choose)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert json.loads(request.content)["deckVersionId"] == OTHER
            current["ownEntry"] = own(deckVersionId=OTHER)
        return response(current)

    league, http = api(handler)
    try:
        entry = LeagueEventEntry("legacy", deck_version_ids=(DECK, OTHER, DECK))
        await league.join(EVENT, entry)
        await league.join(EVENT, entry)
        assert calls == [(DECK, OTHER)]
    finally:
        await http.aclose()


async def test_finder_uses_server_time_and_exact_environment_never_the_device_clock() -> None:
    candidates = [
        event(id=OTHER, competitionVersionId=OTHER),
        event(id=NEXT, registrationClosesAt="2026-10-21T11:59:00Z"),
        event(),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/events"):
            return response(
                {"items": candidates, "executionEnabled": True, "pageSize": 50, "total": 3}
            )
        assert request.url.path.endswith(EVENT)
        return response(event())

    league, http = api(handler)
    try:
        result = await league.find_event(
            LeagueEventEntry("legacy", DECK, competition_version_id=ENVIRONMENT)
        )
        assert result is not None and result["id"] == EVENT
    finally:
        await http.aclose()


async def test_finder_resumes_own_running_event_before_joining_another_queue() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/events"):
            return response(
                {
                    "items": [event(id=NEXT), event(phase="season")],
                    "executionEnabled": True,
                    "total": 2,
                    "pageSize": 50,
                }
            )
        return response(
            event(
                phase="season", ownEntry=own(), ownMatches=[{"matchId": OTHER, "status": "running"}]
            )
        )

    league, http = api(handler)
    try:
        selected = await league.find_event(LeagueEventEntry("legacy", DECK))
        assert selected is not None and selected["id"] == EVENT
        assert selected["ownMatches"][0]["matchId"] == OTHER
    finally:
        await http.aclose()


@pytest.mark.parametrize(
    "invalid",
    [
        {"items": [], "executionEnabled": False},
        {"items": [event(phase="invented")], "executionEnabled": True},
        {"items": [event(competitionVersionId=None)], "executionEnabled": True},
        {"items": [event(serverNow="not a timestamp")], "executionEnabled": True},
    ],
)
async def test_disabled_and_incompatible_servers_never_fall_back_to_old_tickets(
    invalid: dict[str, Any],
) -> None:
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return response(invalid)

    league, http = api(handler)
    try:
        with pytest.raises((LeagueUnavailableError, LeagueCompatibilityError)):
            await league.find_event(LeagueEventEntry("legacy", DECK))
        assert paths == ["/api/v1/progression/events"]
    finally:
        await http.aclose()


@pytest.mark.parametrize("continuous", [True, False])
async def test_runner_serves_all_assigned_rounds_then_optionally_joins_next_cycle(
    monkeypatch: Any,
    continuous: bool,
) -> None:
    subject = AgentRunner(
        Agent(), AgentConfig("sdk-test", "SDK test", "1", "QA", ("legacy",)), target()
    )
    keep_running = asyncio.Event()
    connected = []
    phases = []
    joined = []
    current = event(ownEntry=own())

    async def serve(**kwargs: Any) -> None:
        connected.append("serve")
        await keep_running.wait()

    async def wait(**kwargs: Any) -> str:
        connected.append("connected")
        return "agent:sdk-test"

    class League:
        agent_version_id = AGENT

        async def find_event(self, entry: LeagueEventEntry) -> dict[str, Any]:
            assert entry.format == "legacy"
            return event(id=EVENT if not joined else NEXT)

        async def join(self, id: str, entry: LeagueEventEntry) -> dict[str, Any]:
            joined.append(id)
            if id == NEXT:
                raise asyncio.CancelledError
            return copy.deepcopy(current)

        async def event(self, id: str) -> dict[str, Any]:
            assert id == EVENT
            current["phase"] = {
                "registration": "season",
                "season": "playoffs",
                "playoffs": "complete",
            }[current["phase"]]
            return copy.deepcopy(current)

    async def callback(value: dict[str, Any] | None) -> None:
        assert value is not None
        phases.append(value["phase"])

    monkeypatch.setattr(subject, "serve", serve)
    monkeypatch.setattr(subject, "wait_until_connected", wait)
    monkeypatch.setattr(AgentRunner, "league", property(lambda _: League()))
    if continuous:
        with pytest.raises(asyncio.CancelledError):
            await subject.serve_league(
                LeagueEventEntry("legacy", DECK), poll_seconds=0, on_event=callback
            )
    else:
        await subject.serve_league(
            LeagueEventEntry("legacy", DECK),
            poll_seconds=0,
            on_event=callback,
            continuous=False,
        )
    assert joined == ([EVENT, NEXT] if continuous else [EVENT])
    assert phases == ["registration", "season", "playoffs", "complete"]
    assert connected[0:2] == ["serve", "connected"]


async def test_retired_ticket_conflict_is_not_a_retry_loop(monkeypatch: Any) -> None:
    subject = AgentRunner(
        Agent(), AgentConfig("sdk-test", "SDK test", "1", "QA", ("legacy",)), target()
    )
    attempts = 0

    async def join(entry: MatchmakingEntry) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        request = httpx.Request("POST", "https://league.test/api/v1/matchmaking/tickets")
        raise httpx.HTTPStatusError(
            "retired", request=request, response=httpx.Response(409, request=request)
        )

    monkeypatch.setattr(subject, "join_matchmaking", join)
    with pytest.raises(httpx.HTTPStatusError):
        await subject.join_matchmaking_with_retry(
            MatchmakingEntry(ENVIRONMENT, DECK), retry_seconds=0
        )
    assert attempts == 1


async def test_incompatible_ack_is_reconciled_but_never_reposted() -> None:
    current = event()
    methods = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "POST":
            current["ownEntry"] = own()
            return httpx.Response(200, json={"unknownAck": True})
        return response(current)

    league, http = api(handler)
    try:
        saved = await league.join(EVENT, LeagueEventEntry("legacy", DECK))
        assert saved["ownEntry"] == own()
        assert methods == ["GET", "POST", "GET"]
    finally:
        await http.aclose()


async def test_event_identity_mismatch_and_pinned_event_never_write() -> None:
    methods = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return response(event(id=NEXT))

    league, http = api(handler)
    try:
        with pytest.raises(LeagueCompatibilityError, match="identity"):
            await league.event(EVENT)
        with pytest.raises(LeagueEntryConflict, match="pinned"):
            await league.join(NEXT, LeagueEventEntry("legacy", DECK, event_id=EVENT))
        assert methods == ["GET"]
    finally:
        await http.aclose()


def test_entries_require_canonical_server_ids_and_supported_formats() -> None:
    with pytest.raises(ValueError):
        LeagueEventEntry("other", DECK)
    with pytest.raises(ValueError):
        LeagueEventEntry("legacy")
    with pytest.raises(LeagueCompatibilityError):
        LeagueEventEntry("legacy", "local-deck-name-is-not-a-published-version")
    entry = LeagueEventEntry("legacy", DECK.upper(), competition_version_id=ENVIRONMENT.upper())
    assert entry.deck_version_id == DECK and entry.competition_version_id == ENVIRONMENT


async def test_revoked_read_permission_stops_and_does_not_retry_or_withdraw(
    monkeypatch: Any,
) -> None:
    subject = AgentRunner(
        Agent(), AgentConfig("sdk-test", "SDK test", "1", "QA", ("legacy",)), target()
    )
    calls = []

    async def serve(**kwargs: Any) -> None:
        try:
            await asyncio.Event().wait()
        finally:
            calls.append("disconnected")

    async def connected(**kwargs: Any) -> str:
        return "agent:sdk-test"

    class League:
        agent_version_id = AGENT

        async def find_event(self, entry: LeagueEventEntry) -> dict[str, Any]:
            return event(ownEntry=own())

        async def join(self, id: str, entry: LeagueEventEntry) -> dict[str, Any]:
            return event(ownEntry=own())

        async def event(self, id: str) -> dict[str, Any]:
            calls.append("read")
            request = httpx.Request("GET", f"https://league.test/events/{EVENT}")
            raise httpx.HTTPStatusError(
                "revoked", request=request, response=httpx.Response(403, request=request)
            )

        async def withdraw(self, id: str) -> dict[str, Any]:
            raise AssertionError("Cancellation must not secretly mutate the registration")

    monkeypatch.setattr(subject, "serve", serve)
    monkeypatch.setattr(subject, "wait_until_connected", connected)
    monkeypatch.setattr(AgentRunner, "league", property(lambda _: League()))
    with pytest.raises(httpx.HTTPStatusError):
        await subject.serve_league(
            LeagueEventEntry("legacy", DECK), poll_seconds=0, retry_seconds=0
        )
    assert calls == ["read", "disconnected"]
