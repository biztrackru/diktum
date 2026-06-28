# Review packet — security hardening branch

**Branch:** `security/hardening-2026-06-28`
**Base:** `codex/ux-f1-f2`
**Commit:** `4fb1c2c` — "Harden web server and packaging for public release"
**Audit it implements:** `docs/security-audit-2026-06-28.md`

This branch makes the project safe to publish. It is meant to be reviewed
(functionally and for security) by another AI agent or a human before merge.

---

## 1. What changed and why (mapped to audit findings)

| Finding | Change | File |
|---|---|---|
| **H-1** DNS-rebinding / CSRF | `Host` allowlist + `Origin`/`Sec-Fetch-Site` checks on POST/DELETE | `app/src/voice_recognizer/web.py` (`_guard`, `_host_allowed`, `_origin_allowed`) |
| **M-1** CSRF via non-JSON | JSON endpoints now require `Content-Type: application/json` | `web.py` (`_read_json_body`) |
| **M-2** DoS / disk fill | Caps on request body (`MAX_JSON_BODY_BYTES`) and uploads (`MAX_UPLOAD_BYTES`), env-overridable | `web.py` |
| **M-3** `cgi` removed in 3.13 | New dependency-free streaming multipart parser; Python ceiling raised to `<3.14` | `web.py`, `app/src/voice_recognizer/multipart.py`, `app/pyproject.toml` |
| **M-4** unpinned deps | Upper bounds added; `gigaam` git dep flagged to be commit-pinned | `app/pyproject.toml` |
| **M-5** model integrity | SHA-256 verification framework for GigaAM v3 model files | `app/scripts/setup_gigastt.sh` |
| **L-2** stdout leak | Subprocess output kept in server log, not returned to client | `web.py` (`_apply_result_speaker_names`) |
| **L-3** memory spike | `/outputs/` responses streamed instead of `read_bytes()` | `web.py` (`_serve_output`) |
| **L-4** dead LM Studio config | Removed from `.env.example` | `app/.env.example` |
| **L-5** LAN exposure | Warning printed when bound to a non-local host | `web.py` (`run_web_server`) |
| **L-1** broken git ref | `refs/heads/_t/x` removed; repo `fsck`-clean | repository |
| docs | Privacy/network section, LICENSE (MIT), SECURITY.md | `README.md`, `LICENSE`, `SECURITY.md` |

Design notes:
- No authentication was added: by design this is a local single-user tool. The
  guard layer is what makes "localhost-only" actually safe in a browser context.
- The multipart parser streams part bodies to disk so large audio uploads are
  never fully buffered in memory.
- The frontend already sends `application/json` and `Origin` on same-origin
  requests, so the new checks do not change the UX. Verified against the JS in
  `web.py`.

## 2. How to run the tests

```bash
# from the repo root, no third-party deps required (stdlib only):
python3 tests/test_web_security.py     # 12 tests: guards, limits, traversal, upload
python3 tests/test_multipart.py        # 6 tests: parser correctness + size cap
# or, if pytest is available:
python3 -m pytest tests/ -q
```

Expected: `12/12 passed` and `6/6 passed`.

## 3. Manual verification (server running on 127.0.0.1:8765)

```bash
# allowed (local Host) -> 200
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8765/

# DNS-rebinding simulation (foreign Host) -> 403
curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: evil.example.com' http://127.0.0.1:8765/api/results

# CSRF simulation (cross-origin POST) -> 403
curl -s -o /dev/null -w '%{http_code}\n' -X POST -H 'Origin: http://evil.example.com' \
  -H 'Content-Type: application/json' --data '{}' http://127.0.0.1:8765/api/jobs

# wrong content-type -> 400
curl -s -o /dev/null -w '%{http_code}\n' -X POST -H 'Content-Type: text/plain' \
  --data '{}' http://127.0.0.1:8765/api/jobs

# path traversal -> 403/404
curl -s -o /dev/null -w '%{http_code}\n' --path-as-is http://127.0.0.1:8765/outputs/../../etc/passwd
```

## 4. Suggested prompt for the reviewing AI agent

> You are a security reviewer. Branch `security/hardening-2026-06-28` hardens a
> local macOS transcription web app (stdlib `http.server`, bound to 127.0.0.1,
> no auth by design). Review `app/src/voice_recognizer/web.py` and
> `app/src/voice_recognizer/multipart.py` for:
> 1. Bypasses of the `Host`/`Origin`/`Sec-Fetch-Site` guard (`_guard`,
>    `_host_allowed`, `_origin_allowed`). Consider missing/IPv6/null-origin and
>    header-casing cases.
> 2. Correctness and memory-safety of the multipart parser (boundary spanning
>    reads, oversized parts, malformed headers, filename edge cases).
> 3. Path-traversal containment in `_serve_output`, `_unique_inbox_path`,
>    `_resolve_output_dir`, `_resolve_source`, and manifest source resolution.
> 4. Any remaining command-injection, SSRF, or info-leak paths.
> 5. Whether the size limits and content-type checks are enforced before any
>    expensive work.
> Run `tests/` and try to add a failing test for any weakness you find. Report
> findings as: severity, file:line, concrete risk, suggested fix.

## 5. Residual risks / maintainer to-do before public release

These need a human decision or a real macOS run with the models:

1. **License confirmation.** `LICENSE` is MIT with a placeholder copyright line
   (`2026 Voice Recognizer authors`). Confirm the license and the holder name.
2. **Pin `gigaam`.** Replace the unpinned git dependency in `pyproject.toml`
   with a reviewed `@<commit>` (cannot be chosen safely from here).
3. **Fill model SHA-256.** Run `setup_gigastt.sh` once on a Mac; paste the
   printed `[UNPINNED]` hashes into `EXPECTED_MODEL_SHA256` to enable model
   integrity checks (M-5 framework is in place but values are empty).
4. **Apple signing/notarization (L-6).** The install pack is still unsigned;
   wide distribution should be Developer ID signed + notarized so users don't
   have to strip quarantine.
5. **`SECURITY.md` contact.** Add a contact address or rely on GitHub Security
   Advisories (placeholder TODO is in the file).
6. **Run the full pipeline on macOS** with GigaSTT + pyannote installed
   (the sandbox here has no models/binary, so end-to-end transcription was not
   executed; only the HTTP/security layer was tested).
7. Optionally regenerate a dependency **lock file** (pip-tools/uv) for fully
   reproducible installs.

## 6. Local verification already done in this changeset

- `python3 -m compileall app/src` — OK
- `bash -n app/scripts/setup_gigastt.sh` — OK
- `tests/` — 18/18 passing
- `git fsck` — clean (broken ref removed)
- Confirmed no secrets/audio/`.pyc` staged in the commit.
- `zsh -n` on the zsh launchers was **not** run here (no zsh in the build
  sandbox); run it on macOS as a final check:
  `zsh -n app/scripts/start_server.sh app/scripts/stop_server.sh`
