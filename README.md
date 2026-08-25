# Deep Deck Agent SDK

Un petit toolkit Python pour écrire un agent Magic qui se connecte au moteur Rust de
Deep Deck League. Le moteur reste responsable des règles : votre code choisit simplement
une action parmi celles qu'il déclare légales.

Ce dépôt est en bêta. Le chemin **moteur local** fonctionne avec le protocole
`mtg-agent/v1`. Le chemin public DDL est préparé dans l'API du SDK, mais l'émission de
jetons de compte pour agents doit encore être déployée par le serveur DDL.

## 1. Installer

```powershell
git clone https://github.com/dd-the-dd/deepdeck-agent-sdk.git
cd deepdeck-agent-sdk
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
```

Python 3.10 ou plus récent est supporté.

## 2. Écrire son premier agent

```python
from deepdeck_agent import Agent, Decision


class MonPremierAgent(Agent):
    async def choose_priority(self, decision: Decision):
        # Le moteur a déjà retiré toutes les actions illégales.
        sort = decision.first("castSpell")
        return sort or decision.pass_action
```

Chaque décision possède sa propre fonction. Il suffit de remplacer celles qui vous
intéressent :

```python
class MonAgent(Agent):
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

## 3. Lire l'état et les événements

```python
from deepdeck_agent import Agent, Event, Game


class AgentLisible(Agent):
    async def on_observation(self, game: Game):
        print(game.turn, game.step, game.me.life)
        for card in game.me.hand:
            print(card.name, card.type_line, card.mana_cost)

    async def on_event(self, event: Event, game: Game):
        print(event.sequence, event.kind, event.detail)
```

`game.me`, `game.opponents`, les zones, les permanents, les cartes ciblées et les actions
sont des vues en lecture seule. `EventReader` déduplique les événements inclus dans les
observations et acceptera aussi le flux événementiel poussé lorsque le moteur l'activera.

## 4. Déclarer les formats, decks et rythmes

```python
from deepdeck_agent import AgentConfig, DeckPolicy, PlaySpeed

config = AgentConfig(
    agent_id="com.example.mon-agent",
    name="Mon agent",
    version="0.1.0",
    author="Votre nom",
    description="Un exemple simple.",
    formats=("commander", "legacy"),
    decks=DeckPolicy.all(),
    speeds=(PlaySpeed.MS_100, PlaySpeed.SECOND_1, PlaySpeed.SECONDS_10),
)
```

Politiques de deck disponibles :

- `DeckPolicy.all()` : tous les decks;
- `DeckPolicy.only("deck-version-id")` : un seul deck;
- `DeckPolicy.one_of("id-1", "id-2")` : une liste fermée.

Les rythmes publics `100ms`, `1s` et `10s` sont convertis vers la marge de transport du
protocole (`realtime`, `standard`, `extended`). Répondre plus rapidement est toujours permis.

## 5. Se connecter au moteur local

```python
import asyncio

from deepdeck_agent import AgentRunner, ServerTarget

runner = AgentRunner(
    agent=MonPremierAgent(),
    config=config,
    target=ServerTarget.local("http://127.0.0.1:8787"),
)

asyncio.run(runner.serve())
```

Si le moteur exige une clé, placez-la dans `MTG_ENGINE_API_KEY`. Ne l'écrivez jamais dans
le code. Pour démarrer une partie locale depuis Python, consultez
[`docs/start-a-game.md`](docs/start-a-game.md).

## 6. Se connecter à Deep Deck League

Le SDK utilisera `DEEPDECK_ACCESS_TOKEN` pour l'identité du compte et
`DEEPDECK_AGENT_URL` pour le WebSocket public :

```python
target = ServerTarget.deepdeckleague()
runner = AgentRunner(agent=MonPremierAgent(), config=config, target=target)
```

Le serveur public n'émet pas encore ce jeton dédié. N'utilisez pas le secret global du
moteur comme solution de remplacement. Le contrat de sécurité prévu est décrit dans
[`docs/authentication.md`](docs/authentication.md).

## Baseline et exemple Alexios

Le dépôt compagnon
[`deepdeck-agent-examples`](https://github.com/dd-the-dd/deepdeck-agent-examples)
contient le baseline aléatoire et un agent programmatique pour Alexios.

## Développement

```powershell
ruff check .
mypy
pytest
```

Voir aussi [`CONTRIBUTING.md`](CONTRIBUTING.md), [`SECURITY.md`](SECURITY.md) et le
[`guide de publication GitHub`](docs/publishing.md).
