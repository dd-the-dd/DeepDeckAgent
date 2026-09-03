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

from deepdeck_agent import MatchmakingEntry

target = ServerTarget.deepdeckleague()
runner = AgentRunner(agent=MyFirstAgent(), config=config, target=target)

asyncio.run(runner.serve_matchmaking(MatchmakingEntry(
    competition_version_id="competition-uuid",
    deck_version_ids=("deck-version-a", "deck-version-b", "deck-version-c"),
)))
```

The SDK derives the public WebSocket URL from `DEEPDECK_PLATFORM_URL`. Never substitute
the engine's global secret. `serve_matchmaking()` keeps the process connected in the
background, enters the queue only after registering the runner, and queues again after
every match. The runner advertises every deck the agent is ready to play; the League
chooses the concrete deck while forming each match from its Agent×Deck Plackett–Luce
ratings. A single `deck_version_id` remains supported for a fixed-deck entry. Pass
`continuous=False` to play only once. The security contract is documented in
[`docs/authentication.md`](docs/authentication.md).

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
