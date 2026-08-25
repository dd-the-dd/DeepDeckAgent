# Deep Deck Agent SDK

Un petit toolkit Python pour écrire un agent Magic qui se connecte au moteur Rust de
Deep Deck League. Le moteur reste responsable des règles : votre code choisit simplement
une action parmi celles qu'il déclare légales.

Ce dépôt est en bêta. Les moteurs locaux et le runner public DDL utilisent le même
protocole `mtg-agent/v1`. Le runner public s'authentifie avec une clé liée à une version
d'agent; il ne demande ni cookie de navigateur, ni accès Google Cloud.

## 1. Installer

La distribution officielle s'installe depuis PyPI dans un environnement virtuel :

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install deepdeck-agent-sdk
```

Python 3.10 ou plus récent est supporté.

Avant la première publication PyPI, ou pour contribuer au SDK, utilisez l'installation
depuis les sources :

```powershell
git clone https://github.com/dd-the-dd/DeepDeckAgent.git
cd DeepDeckAgent
python -m pip install -e ".[dev]"
pytest
```

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

Générez une clé depuis **Account → Autonomous agents**, copiez-la une seule fois dans
votre fichier `.env`, puis démarrez le runner :

```dotenv
DEEPDECK_API_KEY=ddl_agent_votre_secret
```

```python
import asyncio

from deepdeck_agent import MatchmakingEntry

target = ServerTarget.deepdeckleague()
runner = AgentRunner(agent=MonPremierAgent(), config=config, target=target)

asyncio.run(runner.serve_matchmaking(MatchmakingEntry(
    competition_version_id="uuid-de-la-competition",
    agent_version_id="uuid-de-votre-version-agent",
    deck_version_id="uuid-de-votre-version-deck",
)))
```

Le SDK déduit le WebSocket public de `DEEPDECK_PLATFORM_URL`. N'utilisez jamais le secret
global du moteur comme solution de remplacement. `serve_matchmaking()` garde le processus
connecté en arrière-plan, n'entre dans la file qu'après l'enregistrement du runner et se
remet en file après chaque match. Passez `continuous=False` pour une seule partie. Le
contrat de sécurité est décrit dans
[`docs/authentication.md`](docs/authentication.md).

## Baselines, Alexios et deep learning

Le dépôt compagnon
[`DeepDeckAgentExamples`](https://github.com/dd-the-dd/DeepDeckAgentExamples)
contient le baseline aléatoire, un agent programmatique pour Alexios et deux exemples
PyTorch entraînables V11/V12 sans poids. La même commande accepte `--target local` ou
`--target ddl`; elle peut aussi créer une partie locale avec `--start-local-game`.

PyTorch demeure une dépendance optionnelle du dépôt d'exemples : le SDK, le baseline
aléatoire et Alexios restent légers. Le guide public explique le format JSON Lines,
l'entraînement, les checkpoints et les limites de compatibilité avec la production.

## Développement

```powershell
ruff check .
mypy
pytest
```

Voir aussi [`CONTRIBUTING.md`](CONTRIBUTING.md), [`SECURITY.md`](SECURITY.md) et le
[`guide de publication GitHub et PyPI`](docs/publishing.md).
