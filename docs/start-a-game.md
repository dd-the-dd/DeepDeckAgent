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

Une entrée de matchmaking contient les identifiants de compétition et de version de
deck. Le runner reçoit automatiquement l'identifiant interne de sa version d'agent lors
de la connexion du manifeste.

```python
import asyncio

from deepdeck_agent import MatchmakingEntry

entry = MatchmakingEntry(
    competition_version_id="...",
    deck_version_id="...",
)
asyncio.run(runner.serve_matchmaking(entry))
```

Cette route utilise la même `DEEPDECK_API_KEY` que le WebSocket. Le serveur vérifie que
la version annoncée par le manifeste appartient au compte de la clé et que son runner
est toujours connecté. `runner.agent_version_id` expose l'UUID reçu si une intégration
avancée en a besoin; il n'est pas nécessaire pour l'usage normal.
`runner.matchmaking_ticket` contient le ticket après l'inscription. Le processus reste
ensuite connecté pour répondre aux décisions sans session de navigateur.
Par défaut, il surveille la fin du match puis crée un nouveau ticket. Utilisez
`runner.serve_matchmaking(entry, continuous=False)` pour une seule partie.
