# Changelog

## 0.3.0

- Select the public production API automatically: an API key is now the only
  required client configuration.
- Keep `base_url` and `ANTESCOFO_API_BASE_URL` as optional overrides for other
  API environments. Constructor arguments take precedence over the environment;
  explicitly empty or unsafe origins remain errors. No environment failover is
  attempted, and authentication isolation and job-creation behavior are unchanged.

## 0.2.0

- Use `/v1/` routes on the configured customer API origin for job creation,
  status, files, history, and usage. The origin remains explicitly configured
  through `base_url` or `ANTESCOFO_API_BASE_URL`, without a path suffix.
- This changes the request URLs from 0.1.x; use the current Base URL provided
  in your organization's Account > API Access and upgrade the client together.
- Method names, result fields, API-key authentication, and credential-free
  signed storage transfers are unchanged. Creation POSTs are never retried.

## 0.1.0

- Initial Python client with submit, upload, wait, result retrieval, job history,
  and usage helpers.
