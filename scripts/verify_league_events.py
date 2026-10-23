"""Opt-in real-HTTP SDK verification against an operator-owned loopback QA API.

This intentionally enrolls and withdraws a fixture entry. No production endpoint,
ordinary account, worker, real game, external API or paid resource is accepted.
"""

from __future__ import annotations

import asyncio
import os
from urllib.parse import urlsplit

from deepdeck_agent import LeagueClient, LeagueEventEntry, ServerTarget


async def main() -> None:
    endpoint = os.environ["DDL_SDK_QA_URL"].rstrip("/")
    url = urlsplit(endpoint)
    if (
        url.scheme != "http"
        or url.hostname not in {"127.0.0.1", "localhost", "::1"}
        or url.username
        or url.password
        or url.query
        or url.fragment
        or not url.path.endswith("/v1")
    ):
        raise RuntimeError("Use an explicit disposable loopback HTTP QA API ending in /v1.")
    if os.environ.get("DDL_SDK_QA_CONFIRM_DISPOSABLE") != "yes":
        raise RuntimeError(
            "Confirm that these are disposable QA entries before this intentional write."
        )
    token = os.environ["DDL_SDK_QA_KEY"]
    if not token.startswith("ddl_agent_"):
        raise RuntimeError("Use only an account-bound fixture agent key.")
    league = LeagueClient(
        ServerTarget.deepdeckleague(platform_url=endpoint, api_key=token),
        agent_version_id=os.environ["DDL_SDK_QA_AGENT_VERSION_ID"],
    )
    config = await league.config()
    assert config["executionEnabled"] is True, "QA admission must be explicitly enabled."
    listing = await league.events()
    ids = {row["id"] for row in listing["items"]}
    for format in ("legacy", "commander"):
        event_id = os.environ[f"DDL_SDK_QA_{format.upper()}_EVENT_ID"]
        deck_id = os.environ[f"DDL_SDK_QA_{format.upper()}_DECK_VERSION_ID"]
        assert event_id in ids, "Seed the requested fixture queue before testing."
        before = await league.event(event_id)
        assert before["format"] == format and before["phase"] == "registration"
        previous = before.get("ownEntry")
        assert previous is None or previous.get("withdrawnAt") is not None, (
            "Never overwrite an existing registration in a QA check."
        )
        options = await league.entry_options(event_id)
        assert options["eligible"] is True
        assert any(
            agent["agentVersionId"] == league.agent_version_id
            and deck_id in agent["deckVersionIds"]
            for agent in options["agents"]
        )
        entry = LeagueEventEntry(
            format,
            deck_id,
            event_id=event_id,
            competition_version_id=before["competitionVersionId"],
        )
        registered = False
        try:
            saved = await league.join(event_id, entry)
            registered = True
            assert saved["ownEntry"]["agentVersionId"] == league.agent_version_id
            assert saved["ownEntry"]["deckVersionId"] == deck_id
            assert saved.get("ownMatches", []) == [], "This test must not launch a worker/game."
            reconciled = await league.join(event_id, entry)
            assert reconciled["ownEntry"] == saved["ownEntry"]
        finally:
            if registered:
                await league.withdraw(event_id)
        after = await league.event(event_id)
        assert after["ownEntry"]["withdrawnAt"] is not None
        assert after.get("ownMatches", []) == []
        print(f"{format}: real API list/options/enroll/reconcile/withdraw passed; no game launched")


if __name__ == "__main__":
    asyncio.run(main())
