# Security policy

Do not open a public issue containing an engine key, account token, private signing key,
session cookie, deck-reader token, worker token, or database URL.

Report a vulnerability privately through GitHub's security advisory interface for this
repository. Revoke any exposed token immediately.

The SDK never needs a private release-signing key to play a match. Public examples must
read runtime credentials from environment variables and must never contain usable
production credentials.

