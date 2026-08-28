# Authentification des agents publics

## Ce qui peut être public

- l'identifiant de l'application cliente;
- la clé publique qui vérifie une version signée de l'agent;
- le code, le manifeste, le dépôt et le digest de l'artefact.

Une clé publique prouve qu'une version a été signée par son propriétaire. Elle ne doit
jamais accorder, à elle seule, le droit de jouer ou de modifier l'agent.

## Ce qui doit rester secret

- la clé privée de publication;
- la clé API d'agent de chaque personne qui exécute l'agent;
- le secret interne du moteur et les jetons des workers.

Le secret global `MTG_ENGINE_API_KEY` n'est acceptable que sur une machine locale ou
entre services privés. Le publier permettrait d'enregistrer n'importe quel agent sous
n'importe quelle identité.

## Contrat serveur

1. La personne se connecte au site avec son compte DDL.
2. Elle crée une clé opaque révocable limitée aux scopes `agent:connect` et
   `matchmaking:join`, puis la copie une seule fois dans `.env`.
3. PostgreSQL conserve le compte, l'expiration, la révocation et le SHA-256; jamais la
   clé en clair. La clé n'est pas liée à un agent choisi dans le site.
4. L'API publique valide la clé, puis crée ou met à jour sous ce compte l'agent et la
   version décrits par le manifeste. Un slug appartenant à un autre compte est refusé.
5. L'API relaie le protocole vers le moteur privé et injecte sa propre clé interne. Le SDK
   ne connaît jamais ce secret de service.
6. La plateforme retourne l'UUID de version au SDK après l'inscription; le développeur
   ne le copie pas dans sa configuration de matchmaking. Une modification du comportement
   ou des poids doit changer la version du manifeste.
7. La publication d'une nouvelle version officielle pourra exiger séparément une
   signature dont la clé publique est enregistrée sur l'agent appartenant au compte.

Ce découpage permet à plusieurs personnes d'exécuter le même code public avec leurs
propres agents, sans leur donner le droit de publier une nouvelle version officielle ou
de se faire passer pour un autre slug.

## Stockage local

Le SDK charge automatiquement `DEEPDECK_API_KEY` depuis le fichier `.env` du dossier
courant et ne le sauvegarde pas. Une future commande de connexion pourra employer le stockage sécurisé du
système d'exploitation. Aucun fichier `.env` ne doit être commité.
