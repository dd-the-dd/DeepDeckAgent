# Deep Deck Agent SDK

A small Python toolkit for writing a Magic agent that connects to the Deep Deck League
Rust engine. The engine remains responsible for the rules: your code simply chooses one
of the legal actions it provides.

This repository is in beta. Local engines and the public DDL runner use the same
`mtg-agent/v1` protocol. The public runner authenticates with an account-bound agent key;
it does not require a browser cookie or Google Cloud access.

## 1. Install

Install the official distribution from PyPI in a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install deepdeck-agent-sdk
```

Python 3.10 and newer are supported.

To contribute to the SDK, or before the first PyPI release, install it from source:

```powershell
git clone https://github.com/dd-the-dd/DeepDeckAgent.git
cd DeepDeckAgent
python -m pip install -e ".[dev]"
pytest
```

## 2. Write your first agent

```python
from deepdeck_agent import Agent, Decision


class MyFirstAgent(Agent):
    async def choose_priority(self, decision: Decision):
        # The engine has already removed every illegal action.
        spell = decision.first("castSpell")
        return spell or decision.pass_action
```

Every decision type has its own method. Override only the methods your agent needs:

```python
class MyAgent(Agent):
    async def choose_opening_hand(self, decision): ...
    async def choose_mulligan(self, decision): ...
    async def choose_mulligan_bottom(self, decision): ...
    async def choose_priority(self, decision): ...
    async def choose_discard(self, decision): ...
    async def choose_attackers(self, decision): ...
    async def choose_blockers(self, decision): ...
    async def choose_combat_damage(self, decision): ...
    async def choose_replacement(self, decision): ...
    async def choose_resolution(self, decision): ...
    async def choose_sideboarding(self, decision): ...
```

## 3. Read game state and events

```python
from deepdeck_agent import Agent, Event, Game


class ReadableAgent(Agent):
    async def on_observation(self, game: Game):
        print(game.turn, game.step, game.me.life)
        for card in game.me.hand:
            print(card.name, card.type_line, card.mana_cost)

    async def on_event(self, event: Event, game: Game):
        print(event.sequence, event.kind, event.detail)
```

`game.me`, `game.opponents`, zones, permanents, targeted cards, and actions are read-only
views. `EventReader` deduplicates events included in observations and will also accept the
pushed event stream when the engine exposes it.

## 4. Declare formats, decks, and play speeds

```python
from deepdeck_agent import AgentConfig, DeckPolicy, PlaySpeed

config = AgentConfig(
    agent_id="com.example.my-agent",
    name="My agent",
    version="0.1.0",
    author="Your name",
    description="A simple example.",
    formats=("commander", "legacy"),
    decks=DeckPolicy.all(),
    speeds=(PlaySpeed.MS_100, PlaySpeed.SECOND_1, PlaySpeed.SECONDS_10),
)
```

Available deck policies:

- `DeckPolicy.all()`: accept every deck;
- `DeckPolicy.only("deck-version-id")`: accept one deck;
- `DeckPolicy.one_of("id-1", "id-2")`: accept a fixed list.

The public `100ms`, `1s`, and `10s` speeds map to the protocol's transport budgets
(`realtime`, `standard`, and `extended`). An agent may always respond faster.

## 5. Connect to a local engine

```python
import asyncio

from deepdeck_agent import AgentRunner, ServerTarget

runner = AgentRunner(
    agent=MyFirstAgent(),
    config=config,
    target=ServerTarget.local("http://127.0.0.1:8787"),
)

asyncio.run(runner.serve())
```

If the engine requires a key, put it in `MTG_ENGINE_API_KEY`. Never hard-code it. See
[`docs/start-a-game.md`](docs/start-a-game.md) to start a local game from Python.

## 6. Connect to Deep Deck League

Generate a key from **Account → Autonomous agents**, copy it once into your `.env` file,
then start the runner:

```dotenv
DEEPDECK_API_KEY=ddl_agent_your_secret
```

```python
import asyncio

from deepdeck_agent import LeagueEventEntry

target = ServerTarget.deepdeckleague()
runner = AgentRunner(agent=MyFirstAgent(), config=config, target=target)

asyncio.run(runner.serve_league(LeagueEventEntry(
    format="legacy",  # or "commander", if declared by the agent
    deck_version_id="replace-with-your-published-deck-version-UUID",
)))
```

The SDK defaults to production and derives the public WebSocket URL from
`DEEPDECK_PLATFORM_URL`. Never substitute the engine's global secret. Replace the deck
placeholder with a real **server deck-version UUID**, not a local deck name or file.
The League checks ownership, supported decks, legality and the account's entry allowance.

`serve_league()` registers the connected runner, joins the server's thirty-minute queue,
and serves the whole season and playoff event. The server assigns games over the same
WebSocket; the SDK never claims a worker lease or chooses its opponents. By default it
opts into the next event after this one ends. `continuous=False` means **one competition**,
not one game. An explicit `event_id` also stops after that event. A disabled or incompatible
event service never falls back to the retired continuous/ELO matchmaking queue.

For a deck collection, use `deck_version_ids=(uuid_a, uuid_b, ...)`: one eligible deck is
randomly selected and snapshotted **per competition**, not replaced between its games.
Specify `competition_version_id` to require an exact server environment; another one is
never silently selected. `runner.league_event` and the optional asynchronous `on_event`
callback expose actual event phases and authenticated `ownMatches` assignments/results.

Season games retain results, statistics and recognition but no persistent replay. Every
playoff round retains its replay, including quarterfinals and semifinals. Stopping the
Python process does not withdraw a registration or cancel games. Explicitly call
`await runner.league.withdraw(event_id)` while registration is open before disconnecting.
Once play starts, keep the runner online for the competition.

For lower-level controls and migration from `serve_matchmaking`, see
[`docs/league-events.md`](docs/league-events.md). The security contract is documented in
[`docs/authentication.md`](docs/authentication.md).

The complete registration metadata contract, serialization mode, and strict unknown-field
policy are documented in [`docs/agent-manifest.md`](docs/agent-manifest.md).

## Expose training to DeepDeckLearner

An agent can remain the owner of its training science while exposing a versioned,
model-independent cockpit to DeepDeckLearner:

```python
from pathlib import Path

from deepdeck_agent import (
    TrainingBridge,
    TrainingContract,
    TrainingMetric,
    TrainingParameter,
    TrainingPhase,
)

contract = TrainingContract(
    agent_id="org.example.legacy-agent",
    phases=(TrainingPhase(
        phase_id="self-play",
        label="Legacy Engine self-play",
        metrics=(TrainingMetric(
            key="engine_win_rate",
            label="Engine win rate",
            kind="rate",
            direction="maximize",
            description="Fixed-seed win rate against the frozen baseline.",
        ),),
        parameters=(TrainingParameter(
            key="rollout_games",
            label="Games per update",
            kind="integer",
            default=2,
            minimum=1,
            maximum=64,
        ),),
    ),),
)
bridge = TrainingBridge(Path(".deepdeck/runs/my-agent"), contract)
bridge.report_state(phase="self-play", status="running", step=12)
bridge.report_metrics(
    phase="self-play",
    step=12,
    metrics={"engine_win_rate": 0.58},
    context={"games": 200},
)
```

The bridge publishes a contract, live state, and JSON Lines metrics. DeepDeckLearner
writes requested controls to the same workspace; the trainer reads them with
`bridge.requested_control()`, validates them against its own science, and decides when
they can safely take effect. No model architecture or PyTorch dependency is imposed by
the SDK contract. Metric steps are monotonic within each phase, so a later phase can use
its own step counter. Parameter keys are unique across the complete contract because
DeepDeckLearner persists parameter values by key.

## Baselines, Alexios, and deep learning

The companion
[`DeepDeckAgentExamples`](https://github.com/dd-the-dd/DeepDeckAgentExamples) repository
contains a random baseline, a programmatic Alexios agent, and trainable PyTorch V11/V12
examples without weights. The same command accepts `--target local` or `--target ddl`
and can create a local game with `--start-local-game`.

PyTorch remains an optional dependency of the examples repository, so the SDK, random
baseline, and Alexios agent stay lightweight. Its public guide explains the JSON Lines
format, training, checkpoints, and production-compatibility limits.

## Development

```powershell
ruff check .
mypy
pytest
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md), [`SECURITY.md`](SECURITY.md), and the
[`GitHub and PyPI publishing guide`](docs/publishing.md).
