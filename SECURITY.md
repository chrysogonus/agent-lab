# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's
[private vulnerability reporting](https://github.com/chrysogonus/agent-lab/security/advisories/new)
(Security tab → "Report a vulnerability"). Do not open a public issue.

Include what is affected, how to reproduce it, and the impact you see.

## Supported versions

Agent Lab has no releases yet; only the latest commit on `main` is supported.

## Response

This is a personal project. Expect an acknowledgement within 7 days and an assessment within
30 days. Fixes land on `main`; reporters are credited in the advisory unless they prefer not to
be.

## Scope

Agent Lab is meant to run on your own machine: both servers bind to 127.0.0.1. Reports about the
backend or frontend exposing data beyond localhost, leaking API keys (into spans, logs or API
responses), or executing model output are in scope. Running it deliberately on a public
interface is not a supported setup.
