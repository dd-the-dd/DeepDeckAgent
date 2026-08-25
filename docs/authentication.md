# Authentification des agents publics

## Ce qui peut être public

- l'identifiant de l'application cliente;
- la clé publique qui vérifie une version signée de l'agent;
- le code, le manifeste, le dépôt et le digest de l'artefact.

Une clé publique prouve qu'une version a été signée par son propriétaire. Elle ne doit
jamais accorder, à elle seule, le droit de jouer ou de modifier l'agent.

## Ce qui doit rester secret

- la clé privée de publication;
- le jeton du compte DDL de chaque personne qui exécute l'agent;
- le secret interne du moteur et les jetons des workers.

Le secret global `MTG_ENGINE_API_KEY` n'est acceptable que sur une machine locale ou
entre services privés. Le publier permettrait d'enregistrer n'importe quel agent sous
n'importe quelle identité.

## Contrat serveur prévu

1. La personne se connecte au site avec son compte DDL.
2. Elle crée un jeton d'exécution court et révocable limité aux scopes
   `agent:connect` et `matchmaking:join`.
3. Le jeton contient ou référence le compte, la version d'agent autorisée, les formats,
   les decks et une date d'expiration.
4. Le moteur vérifie la signature du jeton avec la clé publique de la plateforme et
   compare `agentId` au manifeste reçu.
5. PostgreSQL conserve le propriétaire, le hash du jeton, son expiration et sa
   révocation; jamais le jeton en clair.
6. La publication d'une nouvelle version officielle exige en plus une signature dont
   la clé publique est enregistrée sur l'agent appartenant au compte.

Ce découpage permet à plusieurs personnes d'exécuter le même code public avec leur
propre compte, sans leur donner le droit de publier une nouvelle version officielle ni
de se faire passer pour le propriétaire.

## Stockage local

Pour le prototype, le SDK lit `DEEPDECK_ACCESS_TOKEN` depuis l'environnement et ne le
sauvegarde pas. Une future commande de connexion devra employer le stockage sécurisé du
système d'exploitation. Aucun fichier `.env` ne doit être commité.

