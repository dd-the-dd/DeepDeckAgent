# Démarrer une partie

## Moteur local

L'agent doit d'abord être connecté. Son contrôleur devient `agent:<agent-id>`.

```python
import asyncio

from deepdeck_agent import AgentRunner, LocalGame, LocalPlayer


async def main(runner: AgentRunner):
    connection = asyncio.create_task(runner.serve())
    controller_id = await runner.wait_until_connected()
    game = LocalGame(
        format="commander",
        players=(
            LocalPlayer(
                player_id="player-1",
                deck_session_id="alexios",
                controller_id=controller_id,
                starting_life=40,
            ),
            LocalPlayer(
                player_id="player-2",
                deck_session_id="opponent",
                controller_id="ai-random",
                starting_life=40,
            ),
        ),
        free_mulligans=1,
    )
    bootstrap = await runner.start_local_game(game)
    print(bootstrap["session"]["id"])
    await connection
```

Les `deck_session_id` doivent déjà être disponibles dans le catalogue local du moteur.

## Matchmaking DDL

Une entrée de matchmaking contient les trois identifiants immuables déjà choisis sur le
site : compétition, version d'agent et version de deck.

```python
from deepdeck_agent import MatchmakingEntry

ticket = await runner.join_matchmaking(MatchmakingEntry(
    competition_version_id="...",
    agent_version_id="...",
    deck_version_id="...",
))
print(ticket["id"], ticket["status"])
```

Cette route exige un jeton appartenant au même compte DDL que la version d'agent. Le
service d'émission de ce jeton est une dépendance serveur encore à déployer.
