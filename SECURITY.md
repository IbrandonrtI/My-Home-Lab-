# Security

This is a personal home lab. The guide [Security and credentials](docs/security.md) lists how it is protected and where its weak spots are.

## If you find a problem

- Use the **Report a vulnerability** button on the repository's Security tab if it is there. That keeps the report private.
- Otherwise open an issue and describe the problem. **Never paste a password, key, token or the contents of `secrets.env`.** If you found a real secret in a file or in the history, say which file and commit but leave the value out.

## If a secret was ever committed

Treat it as public: replace it where it is used. Deleting the line from the file does not remove it from older commits. [Security and credentials](docs/security.md#if-you-think-a-secret-has-leaked) has the steps.
