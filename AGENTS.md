# Antescofo API For Python

- This repository is the thin synchronous remote API client, not the engine.
  Distribution: `antescofo-api`; import: `antescofo_api`; class: `AntescofoClient`.
- Keep HTTP authentication isolated from signed storage requests. Never propagate
  API keys, ambient cookies, `.netrc` auth, or redirects to storage. Do not log
  signed URLs or credentials, including in exception messages and test artifacts.
- The client defaults to the public production API; an API key is the only
  required configuration. Keep the canonical origin in `DEFAULT_API_BASE_URL`.
  Constructor `base_url` overrides `ANTESCOFO_API_BASE_URL`, which overrides the
  default. Reject empty/unsafe overrides and never fail over between environments.
  Keep browser-auth/internal service URLs out of this public client. Other than
  default-origin verification, use reserved example domains in offline tests.
- Customer API requests use `/v1/` paths on that origin; never add `/platform`.
- Never retry job-creation POSTs automatically or replace failed jobs silently.
  Accepted jobs consume quota. Preserve IDs for status/output recovery.
- Preserve detailed analysis fields; do not recreate assessment logic here.
- Default automated tests must stay offline. Live smoke tests require explicit
  authorization and `--create-job`, consume real quota, and must not run in CI.
- Follow the public contract documented in [README.md](README.md) and the checks
  in [CONTRIBUTING.md](CONTRIBUTING.md). Keep documentation useful to external
  developers; do not add private repository maps, checkout paths, or rollout notes.
- Publishing, repository visibility, and license changes require maintainer approval.
- Before finishing: `uv run pytest --cov`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run mypy`, and `uv build`.
- Keep tests, examples, and README consistent with public method signatures.
  Never commit real user inputs, API keys, signed links, or local smoke reports.
