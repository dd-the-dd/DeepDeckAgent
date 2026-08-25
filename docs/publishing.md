# Publier le dépôt public

Le dépôt est public et sous licence MIT. Le public peut le lire, le cloner, le forker et
proposer une pull request. Le fichier `.github/rulesets/protect-main.json` interdit les
mises à jour, suppressions et réécritures de `main`, sauf pour le compte `@dd-the-dd`.

Le fichier de règles n'est pas appliqué automatiquement par GitHub. Après avoir installé
GitHub CLI et ouvert la session du propriétaire, exécuter une seule fois :

```powershell
gh auth login
.\scripts\publish.ps1
```

Le script crée le dépôt public, pousse `main`, puis applique le ruleset avec l'API GitHub.
Une personne ayant reçu plus tard un rôle d'administration pourrait modifier les règles;
ne pas ajouter de collaborateur disposant de droits d'écriture ou d'administration.
