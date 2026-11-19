# Security

Report suspected security vulnerabilities privately to
[research@antescofo.com](mailto:research@antescofo.com). Do not include credentials,
signed storage URLs, personal data, or private recordings in public issues.

Include the client and Python versions, a description of the behavior, and a
minimal reproduction with sensitive data removed.

## Credentials And Files

- Keep API keys in environment variables or a secret manager, not source code,
  notebooks, logs, or version control.
- Signed upload and download URLs grant temporary access to files. Treat them
  as credentials even though they do not require an API key header.
- Avoid raw HTTP debug logging around authenticated requests and file transfers.
- If a credential is exposed, revoke or rotate it and contact Antescofo for help.

For general API access and integration support, visit
[Antescofo Platform](https://platform.antescofo.com/).
