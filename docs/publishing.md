# Publier le dépôt et la distribution PyPI

Le SDK est distribué sous licence MIT. GitHub contient la source publique et PyPI fournit
l'installation officielle avec `python -m pip install deepdeck-agent-sdk`.

## 1. Publier le dépôt GitHub

Le fichier `.github/rulesets/protect-main.json` interdit les mises à jour, suppressions et
réécritures directes de `main`, sauf pour le compte `@dd-the-dd`. Il doit être appliqué une
fois depuis une session GitHub du propriétaire :

```powershell
gh auth login
.\scripts\publish.ps1
```

Le script crée `https://github.com/dd-the-dd/DeepDeckAgent`, pousse `main`, puis
applique le ruleset. Ne donnez pas de droits d'écriture ou d'administration à un compte
qui ne doit pas pouvoir publier le SDK.

## 2. Créer les environnements GitHub

Dans **Settings → Environments**, créez :

- `testpypi`, utilisé uniquement par un lancement manuel du workflow;
- `pypi`, utilisé uniquement lorsqu'une GitHub Release est publiée.

Sur `pypi`, activez une approbation manuelle et limitez les branches/tags de déploiement
aux tags de release. Aucun secret PyPI ne doit être ajouté à ces environnements.

## 3. Enregistrer les Trusted Publishers

Créez un compte séparé sur PyPI et TestPyPI si nécessaire. Sur chaque service, ouvrez la
page **Publishing** du compte et ajoutez un *pending publisher* avec exactement ces
valeurs :

| Champ | PyPI | TestPyPI |
| --- | --- | --- |
| PyPI project name | `deepdeck-agent-sdk` | `deepdeck-agent-sdk` |
| GitHub owner | `dd-the-dd` | `dd-the-dd` |
| GitHub repository | `DeepDeckAgent` | `DeepDeckAgent` |
| Workflow filename | `publish.yml` | `publish.yml` |
| Environment name | `pypi` | `testpypi` |

Le publisher en attente créera le projet au premier envoi réussi. Il ne réserve toutefois
pas le nom avant ce premier envoi.

## 4. Valider sur TestPyPI

Dans **Actions → Publish Python distribution**, choisissez **Run workflow**. Le job
`publish-testpypi` construit les deux distributions, vérifie leurs métadonnées et les
publie avec un jeton OIDC temporaire.

Testez ensuite dans un environnement vide :

```powershell
python -m venv .venv-testpypi
.\.venv-testpypi\Scripts\Activate.ps1
python -m pip install --index-url https://test.pypi.org/simple/ `
  --extra-index-url https://pypi.org/simple/ deepdeck-agent-sdk
python -c "from deepdeck_agent import Agent; print(Agent.__name__)"
```

`--extra-index-url` permet d'obtenir les dépendances depuis PyPI, car elles ne sont pas
nécessairement toutes présentes sur TestPyPI.

## 5. Publier la version officielle

1. Exécutez `ruff check .`, `mypy`, `pytest` et `python -m build`.
2. Mettez à jour la version dans `pyproject.toml`; une version PyPI publiée est immuable.
3. Fusionnez la version testée dans `main`.
4. Créez et publiez une GitHub Release dont le tag correspond, par exemple `v0.1.0`.
5. Approuvez le déploiement de l'environnement `pypi`.
6. Vérifiez la page `https://pypi.org/project/deepdeck-agent-sdk/` et une installation
   dans un environnement virtuel vide.

Le workflow `.github/workflows/publish.yml` sépare la construction de la publication. Il
n'accorde `id-token: write` qu'aux jobs de publication et n'utilise aucun jeton PyPI
persistant.
