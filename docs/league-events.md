# League competitions from Python

The SDK's player-event client targets the League's versioned registration → season →
playoffs loop. These source changes require a server exposing `/v1/progression/events`
and its authenticated entry endpoints. They are not evidence that a public deployment
or PyPI release has happened.

## Connect first, enroll once

`AgentRunner.serve_league(LeagueEventEntry(...))` connects the existing agent WebSocket
before enrolling. The server returns the connected manifest's `agentVersionId`; you do
not impersonate an agent by supplying another account's ID. `DEEPDECK_API_KEY` is the
account's revocable `ddl_agent_…` key, with `agent:connect` and `matchmaking:join` scopes.
Never supply a worker token, the engine service secret, a ChatGPT key or a Patreon token.
The server, not the SDK, grants entry capacity and validates the agent/deck pair.

An entry specifies `format="legacy"` or `"commander"` and one or more **published server
deck-version UUIDs**. A pool chooses one concrete deck using fresh system randomness when
joining a new event. That deck remains the event snapshot: the SDK does not change it
mid-season. An exact `competition_version_id` is an optional environment constraint.
If the requested environment has no queue, the client waits rather than entering another.

The server's `serverNow`, `registrationOpensAt` and `registrationClosesAt` define whether
a queue appears open; the device clock is not eligibility authority. The enrollment POST
is always the final authority if registration closes during a request.

## Explicit lower-level controls

After `await runner.wait_until_connected()`, `runner.league` provides:

- `await ...config()`: server execution availability.
- `await ...events(page=1)`: bounded public event history and current queues.
- `await ...event(event_id)`: event details plus the authenticated account's `ownEntry`
  and `ownMatches`. Public encounters are not inferred to be this agent's assignments.
- `await ...entry_options(event_id)`: actual server-compatible agents/decks.
- `await ...find_event(entry)`: resume this agent's active cycle, or select an eligible
  registration. An explicit `entry.event_id` never silently switches events.
- `await ...join(event_id, entry)`: enroll once and read back the persisted snapshot.
- `await ...withdraw(event_id)`: explicit registration withdrawal, not game cancellation.

This client does not start games itself. Existing League workers organize tables and
the agent's WebSocket receives starting situations, observations and decisions as before.
Byes are not game assignments. `ownMatches` contains authoritative match IDs/statuses,
not replay data, hidden opponent hands, worker leases or invented results.

## Continuous service and stopping

`serve_league(..., continuous=True)` explicitly opts into subsequent server registration
cycles. `continuous=False` stops after **one complete competition**, even if it contains
several season/playoff games. If `event_id` is pinned, it stops after that event regardless
of `continuous`. `on_event` may be an asynchronous callback receiving the current server
event, or `None` while waiting for the next queue. `runner.league_event` holds the latest
confirmed snapshot. It is not a proof that the runner process is healthy; the WebSocket
registration remains the connection authority.

Cancellation does not silently mutate a registration or cancel games. Before stopping
in an open queue, explicitly withdraw your entry. Once the season begins, withdrawal
returns a conflict and the process should remain connected to serve its scheduled games.
An external explicit withdrawal/replacement stops automatic re-enrollment by that running
loop. Match-count/time deployment limits need an event-aware host policy; they must not
pretend that a multi-game competition is a single old matchmaking ticket.

The existing `serve_matchmaking`, `join_matchmaking` and ticket read/cancel methods remain
available for older servers. They are not used by `serve_league`. A permanent HTTP409 from
a retired ticket endpoint is surfaced immediately, never retried as a reconnect loop.
Migrate callers to player events; do not fall back to the old queue when events are disabled.

## Errors and retries

Transient read failures may be retried while the WebSocket keeps serving. Writes are never
blindly retried. If an enrollment acknowledgement is lost or the server returns a 5xx,
the client reads `ownEntry` to reconcile the exact agent/deck snapshot. It either confirms
the entry or raises `LeagueMutationUncertain`; refresh before another explicit attempt.
Another existing agent/deck registration raises `LeagueEntryConflict`, never silently
replacing it. Authentication, permissions, capacity/deadline conflicts and rate limits
on writes remain explicit HTTP errors. Credentials are not cleared on compatibility errors.

## Multiple official agents on one account

Servers declaring `entryIdentity: "agent-v1"` return an `ownEntries` array with an
immutable `participantId` for each registered agent. The SDK selects only the
connected agent's registration and matches, exposing that selection as `ownEntry`
and `ownMatches` to its existing runner lifecycle. Other owned agents remain in
the raw account list but cannot consume this runner's match budget or be adopted
as its registration. An explicit withdrawal targets this exact participant ID;
it never withdraws the account's other agents.

Run a separate connected runner for each distinct agent. Their total allowance
comes from the server; neither administrative status nor a local concurrency
setting bypasses it. A runner backing its event entry uses one shared place, not
two. A newer version of the same agent is not a second tournament competitor.
An existing active version/deck must be explicitly withdrawn before changing it.

Older owner-based servers keep their one-entry behavior and refusal to silently
replace another agent. Disabled competitions never fall back to old matchmaking.
Multiple agents do not multiply the distinct-owner count used for emblem prestige.

Only the playoff phase has persistent replays. Season results still update actual statistics,
ratings and recognition. A missing season replay is expected, not a request to re-enroll.

## Verification boundary

`tests/test_league.py` exercises the HTTP contract with an in-memory transport and the
runner lifecycle without contacting a production account. `scripts/verify_league_events.py`
is an opt-in real-HTTP check for an explicitly supplied disposable **loopback** QA server.
It needs fixture event/deck/agent UUIDs and a fixture key in environment variables, and
performs an intentional test enrollment followed by withdrawal. It never creates resources,
starts a worker or accepts a remote/production endpoint.

Verified locally on 2026-10-22: the complete SDK suite passed **64 tests**, Ruff was
clean and mypy reported no issues in 14 source modules. The opt-in real-HTTP check also
passed against the isolated PostgreSQL-backed API for both Legacy and Commander:
list, authenticated compatible options, enrollment, exact-entry reconciliation and
withdrawal. That check used explicitly disposable accounts/decks and no worker. It
does **not** prove a real Engine game, public deployment, genuine card-legality checks
or a published PyPI release. Worker/session best-of completion and capacity release
must be validated separately before enabling official public results.
