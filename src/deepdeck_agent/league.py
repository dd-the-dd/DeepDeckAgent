"""Account-owned admission to the League's season/playoff cycles.

The existing AgentClient WebSocket receives game assignments and decisions.
These REST calls enroll the owner; they do not claim a worker lease or create a
match, decide an outcome, or revive the retired continuous matchmaking queue.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, NoReturn, cast
from uuid import UUID

import httpx

from .config import ServerTarget


class LeagueCompatibilityError(RuntimeError):
    """The server does not expose the supported player-event contract."""


class LeagueUnavailableError(RuntimeError):
    """Execution is explicitly disabled, not an invitation to use old tickets."""


class LeagueEntryConflict(RuntimeError):
    """An existing registration must not be silently replaced."""


class LeagueMutationUncertain(RuntimeError):
    """A write was not confirmed; read it again before another user action."""


def _uuid(value: Any, label: str) -> str:
    try:
        return str(UUID(value)) if isinstance(value, str) else _invalid(label)
    except ValueError:
        return _invalid(label)


def _invalid(label: str) -> NoReturn:
    raise LeagueCompatibilityError(
        f"League response has an invalid {label}; update the client/server."
    )


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        return _invalid(label)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            return _invalid(label)
        return result.astimezone(timezone.utc)
    except ValueError:
        return _invalid(label)


@dataclass(frozen=True)
class LeagueEventEntry:
    """A fixed deck or eligible pool; one concrete deck is snapshotted per cycle.

    Leave event_id unset to opt into the next registration for this format.
    competition_version_id, when provided, is an exact environment constraint.
    No other environment is silently selected if it is unavailable.
    """

    format: str
    deck_version_id: str | None = None
    deck_version_ids: tuple[str, ...] = ()
    event_id: str | None = None
    competition_version_id: str | None = None

    def __post_init__(self) -> None:
        if self.format not in {"legacy", "commander"}:
            raise ValueError("Choose legacy or commander for League competition.")
        if not self.deck_pool:
            raise ValueError("A League entry requires at least one published deck version.")
        for value in self.deck_pool:
            _uuid(value, "deck version ID")
        for label, optional_value in (
            ("event ID", self.event_id),
            ("competition version ID", self.competition_version_id),
        ):
            if optional_value is not None:
                _uuid(optional_value, label)
        object.__setattr__(
            self,
            "deck_version_ids",
            tuple(_uuid(v, "deck version ID") for v in self.deck_version_ids),
        )
        if self.deck_version_id is not None:
            object.__setattr__(
                self, "deck_version_id", _uuid(self.deck_version_id, "deck version ID")
            )
        if self.event_id is not None:
            object.__setattr__(self, "event_id", _uuid(self.event_id, "event ID"))
        if self.competition_version_id is not None:
            object.__setattr__(
                self,
                "competition_version_id",
                _uuid(self.competition_version_id, "competition version ID"),
            )

    @property
    def deck_pool(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                value
                for value in (*self.deck_version_ids, self.deck_version_id)
                if value is not None and value.strip()
            )
        )


def _event(data: dict[str, Any]) -> dict[str, Any]:
    _uuid(data.get("id"), "event ID")
    _uuid(data.get("competitionVersionId"), "competition version ID")
    if data.get("format") not in {"legacy", "commander"}:
        return _invalid("event format")
    if data.get("phase") not in {"registration", "season", "playoffs", "complete", "cancelled"}:
        return _invalid("event phase")
    if type(data.get("executionEnabled")) is not bool:
        return _invalid("execution flag")
    for name in ("serverNow", "registrationOpensAt", "registrationClosesAt"):
        _timestamp(data.get(name), name)
    own = data.get("ownEntry")
    if own is not None:
        if not isinstance(own, dict):
            return _invalid("own entry")
        _uuid(own.get("agentVersionId"), "registered agent version ID")
        _uuid(own.get("deckVersionId"), "registered deck version ID")
    identity = data.get("entryIdentity")
    if identity not in {None, "owner-v1", "agent-v1"}:
        return _invalid("registration identity policy")
    if identity == "agent-v1":
        entries = data.get("ownEntries")
        if not isinstance(entries, list) or len(entries) > 64:
            return _invalid("owned agent registrations")
        seen: set[str] = set()
        for registered in entries:
            if not isinstance(registered, dict):
                return _invalid("owned agent registration")
            entry_id = _uuid(registered.get("participantId"), "registration ID")
            _uuid(registered.get("agentVersionId"), "registered agent version ID")
            _uuid(registered.get("deckVersionId"), "registered deck version ID")
            if entry_id in seen:
                return _invalid("duplicate registration ID")
            seen.add(entry_id)
    if "ownMatches" in data:
        matches = data["ownMatches"]
        if not isinstance(matches, list):
            return _invalid("own matches")
        for match in matches:
            if not isinstance(match, dict):
                return _invalid("assigned match")
            _uuid(match.get("matchId"), "assigned match ID")
            if identity == "agent-v1":
                _uuid(match.get("participantId"), "assigned registration ID")
                _uuid(match.get("agentVersionId"), "assigned agent version ID")
    return data


class LeagueClient:
    """Small REST companion to a connected AgentRunner (no hidden retrying writes)."""

    def __init__(
        self,
        target: ServerTarget,
        *,
        agent_version_id: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if target.kind != "deepdeckleague" or target.platform_url is None:
            raise ValueError("LeagueClient requires ServerTarget.deepdeckleague().")
        self._url = target.platform_url
        self._token = target.account_token
        self.agent_version_id = agent_version_id
        self._client = http_client

    async def _request(
        self, method: str, path: str, *, body: dict[str, Any] | None = None, public: bool = False
    ) -> dict[str, Any]:
        if not public and not self._token:
            raise ValueError("DEEPDECK_API_KEY is required for account-owned League entries.")
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        if self._client is not None:
            response = await self._client.request(
                method, f"{self._url}{path}", headers=headers, json=body
            )
        else:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.request(
                    method, f"{self._url}{path}", headers=headers, json=body
                )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as error:
            raise LeagueCompatibilityError(
                "League returned invalid JSON; keep your API key."
            ) from error
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            raise LeagueCompatibilityError(
                "League returned an incompatible response; keep your API key."
            )
        return cast(dict[str, Any], payload["data"])

    async def config(self) -> dict[str, Any]:
        result = await self._request("GET", "/progression/config", public=True)
        if type(result.get("executionEnabled")) is not bool:
            return _invalid("execution flag")
        return result

    async def events(self, *, page: int = 1) -> dict[str, Any]:
        if type(page) is not int or page < 1:
            raise ValueError("Choose a positive League events page.")
        result = await self._request("GET", f"/progression/events?page={page}", public=True)
        if (
            not isinstance(result.get("items"), list)
            or type(result.get("executionEnabled")) is not bool
        ):
            return _invalid("event listing")
        for item in result["items"]:
            if not isinstance(item, dict):
                return _invalid("event")
            _event(item)
        return result

    async def event(self, event_id: str) -> dict[str, Any]:
        expected = _uuid(event_id, "event ID")
        result = _event(await self._request("GET", f"/progression/events/{expected}"))
        if _uuid(result["id"], "event ID") != expected:
            return _invalid("event identity")
        if result.get("entryIdentity") == "agent-v1":
            # Expose only this connected agent to the runner's existing lifecycle.
            # Another owned agent must never replace it or consume its budget.
            owned = [
                item
                for item in result["ownEntries"]
                if item["agentVersionId"] == self.agent_version_id
            ]
            if len(owned) > 1:
                return _invalid("duplicate agent registration")
            own = owned[0] if owned else None
            result = dict(result)
            result["ownEntry"] = own
            result["ownMatches"] = [
                item
                for item in result.get("ownMatches", [])
                if own is not None
                and item["participantId"] == own["participantId"]
                and item["agentVersionId"] == self.agent_version_id
            ]
        return result

    async def entry_options(self, event_id: str) -> dict[str, Any]:
        return await self._request(
            "GET", f"/progression/events/{_uuid(event_id, 'event ID')}/entry-options"
        )

    def _same_entry(self, event: dict[str, Any], entry: LeagueEventEntry) -> bool:
        own = event.get("ownEntry")
        return (
            isinstance(own, dict)
            and own.get("withdrawnAt") is None
            and own.get("agentVersionId") == self.agent_version_id
            and own.get("deckVersionId") in entry.deck_pool
        )

    @staticmethod
    def _matches(event: dict[str, Any], entry: LeagueEventEntry) -> bool:
        return event["format"] == entry.format and (
            entry.competition_version_id is None
            or event["competitionVersionId"] == entry.competition_version_id
        )

    async def find_event(
        self, entry: LeagueEventEntry, *, max_pages: int = 20
    ) -> dict[str, Any] | None:
        """Resume this agent's own active cycle, or find an open server-timed queue."""
        if type(max_pages) is not int or not 1 <= max_pages <= 100:
            raise ValueError("Inspect one to one hundred bounded event pages.")
        if entry.event_id is not None:
            candidate = await self.event(entry.event_id)
            if not self._matches(candidate, entry):
                raise LeagueEntryConflict("The selected event uses another format or environment.")
            return candidate
        registrations: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            listing = await self.events(page=page)
            if not listing["executionEnabled"]:
                raise LeagueUnavailableError(
                    "League competition execution is disabled on this server; "
                    "no old matchmaking ticket was created."
                )
            items = listing["items"]
            for candidate in items:
                if not self._matches(candidate, entry) or not candidate["executionEnabled"]:
                    continue
                if candidate["phase"] in {"season", "playoffs"}:
                    detail = await self.event(candidate["id"])
                    if self._same_entry(detail, entry):
                        return detail
                elif candidate["phase"] == "registration" and _timestamp(
                    candidate["registrationOpensAt"], "registration start"
                ) <= _timestamp(candidate["serverNow"], "server time") < _timestamp(
                    candidate["registrationClosesAt"], "registration deadline"
                ):
                    registrations.append(candidate)
            size = listing.get("pageSize", len(items))
            total = listing.get("total")
            if registrations or not items or (isinstance(size, int) and len(items) < size):
                break
            if isinstance(total, int) and page * len(items) >= total:
                break
        if not registrations:
            return None
        registrations.sort(key=lambda item: _timestamp(item["registrationClosesAt"], "deadline"))
        return await self.event(registrations[0]["id"])

    async def join(self, event_id: str, entry: LeagueEventEntry) -> dict[str, Any]:
        """Explicitly enroll once; reconcile an uncertain acknowledgement by GET.

        Never silently replace another agent/deck owned by the same account.
        Registration's upsert semantics make an exact entry safe to reconcile,
        but a write with an unknown outcome is never automatically reissued.
        """
        if not self.agent_version_id:
            raise RuntimeError("Connect the runner before enrolling an agent in a League event.")
        _uuid(self.agent_version_id, "connected agent version ID")
        if entry.event_id is not None and _uuid(event_id, "event ID") != entry.event_id:
            raise LeagueEntryConflict("This entry is pinned to a different League event.")
        event = await self.event(event_id)
        if not self._matches(event, entry):
            raise LeagueEntryConflict("The selected event uses another format or environment.")
        if not event["executionEnabled"]:
            raise LeagueUnavailableError("Competition execution is disabled for this event.")
        if self._same_entry(event, entry):
            return event
        own = event.get("ownEntry")
        if isinstance(own, dict) and own.get("withdrawnAt") is None:
            raise LeagueEntryConflict(
                "This account already entered another agent or deck. "
                "Withdraw it explicitly before replacing it."
            )
        if event["phase"] != "registration":
            raise LeagueEntryConflict("Registration is closed; this agent was not enrolled.")
        deck = secrets.choice(entry.deck_pool)
        uncertain: Exception | None = None
        try:
            await self._request(
                "POST",
                f"/progression/events/{_uuid(event_id, 'event ID')}/entry",
                body={"agentVersionId": self.agent_version_id, "deckVersionId": deck},
            )
        except httpx.TransportError as error:
            uncertain = error
        except LeagueCompatibilityError as error:
            uncertain = error
        except httpx.HTTPStatusError as error:
            if error.response.status_code < 500:
                raise
            uncertain = error
        try:
            confirmed = await self.event(event_id)
        except (httpx.HTTPError, LeagueCompatibilityError) as error:
            raise LeagueMutationUncertain(
                "The League entry was not confirmed. Refresh this event before "
                "trying another registration; no write was repeated."
            ) from error
        if self._same_entry(confirmed, entry) and confirmed["ownEntry"]["deckVersionId"] == deck:
            return confirmed
        if uncertain is not None:
            raise LeagueMutationUncertain(
                "The League entry outcome is uncertain. "
                "Refresh this event before retrying; no write was repeated."
            ) from uncertain
        raise LeagueMutationUncertain(
            "The server acknowledged entry but its saved registration does not match. "
            "Refresh before retrying."
        )

    async def withdraw(self, event_id: str) -> dict[str, Any]:
        """Explicit owner action, registration only. Never cancels a running match."""
        event = await self.event(event_id)
        suffix = ""
        if event.get("entryIdentity") == "agent-v1":
            own = event.get("ownEntry")
            if not isinstance(own, dict) or own.get("withdrawnAt") is not None:
                raise LeagueEntryConflict(
                    "This connected agent has no active registration to withdraw."
                )
            suffix = "?entryId=" + _uuid(own.get("participantId"), "registration ID")
        return await self._request(
            "DELETE", f"/progression/events/{_uuid(event_id, 'event ID')}/entry{suffix}"
        )
