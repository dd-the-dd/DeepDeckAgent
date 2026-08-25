# Contributing

The repository is public so people can read it, fork it, report problems, and propose
pull requests. Only the repository owner may merge or push to the protected `main`
branch. Do not request write access for ordinary contributions.

Before proposing a change, run:

```powershell
ruff check .
mypy
pytest
```

Keep the beginner-facing API small. New decision helpers must preserve the rule boundary:
Rust publishes legal actions; Python selects one of their exact IDs.

