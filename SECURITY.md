# Security Policy

## Reporting a vulnerability

Please report security issues **privately**, not in public issues.

- Preferred: open a private vulnerability report via GitHub Security Advisories
  ("Security" tab → "Report a vulnerability").
- Alternatively, email the maintainer. <!-- TODO: add a contact address you are
  comfortable publishing, or rely on GitHub Security Advisories. -->

Please include steps to reproduce, affected version/commit, and impact. We aim
to acknowledge reports within a few days. Please give us reasonable time to fix
an issue before public disclosure.

## Threat model

Voice Recognizer is a **local, single-user macOS tool**. The web UI binds to
`127.0.0.1` and has **no authentication by design**. The trust assumption is
that the person running the app controls the machine.

In scope:

- Path traversal / arbitrary file read or write through the web API.
- Command injection through filenames, speaker names, or job parameters.
- CSRF / DNS-rebinding against the local server (a malicious website abusing
  the localhost server while it runs).
- Secret handling (the Hugging Face token in `.env`).
- Supply-chain integrity of the downloaded binary/models.
- Leaking audio or transcripts off the machine.

Out of scope:

- Attacks that require the attacker to already have local OS-level access to the
  user's account (they can read `Inbox/`, `outputs/`, and `.env` directly).
- Running the server intentionally on `0.0.0.0` / a LAN. This is not a supported
  configuration; the app prints a warning and provides no auth for it.
- Vulnerabilities in third-party models/dependencies themselves (report those
  upstream), though packaging/pinning issues here are in scope.

## Hardening already in place

- `Host` allowlist (anti DNS-rebinding) and `Origin`/`Sec-Fetch-Site` checks on
  state-changing requests (anti CSRF).
- `Content-Type: application/json` required on JSON endpoints; request-body and
  upload size limits.
- Upload filenames are reduced to a safe basename with an extension allowlist;
  all served/stored paths are confined to `outputs/` and `Inbox/` via
  `resolve()` + containment checks.
- All subprocess calls use argument lists (no shell), so filenames and names
  cannot inject commands.
- The downloaded GigaSTT binary and RUPunct model are verified by SHA-256.
- `.env` is created with `chmod 600`; secrets are never committed and never
  printed to logs or HTTP responses.

## Supported versions

The latest commit on the default branch is supported. This is an early-stage
project (0.x); older versions are not maintained.
