# ResearchNavigator 2.2.3 Public Demo Attack-Surface Audit

Baseline: frozen Core `0db09b07b3b9aa8efa8ff080c296f15bf08f5e97`; deployment baseline `e5a8fec6b1e1b06443125f087ebc174a1d55d86f`.

This is a supervised portfolio demo, not a production SaaS or a 24×7 service. The audit was completed before hardening implementation.

## Authentication and isolation

- Passwords use PBKDF2-SHA256 and sessions use opaque hashed bearer tokens with expiry/revocation.
- User-owned projects, jobs, library records, notes and uploaded documents are queried by `user_id`.
- Registration is open and schema-bounded, but currently has no demo user-count bound.
- Session TTL defaults to 168 hours.

## Public-safe product surface

Search, paper detail, favourites, PaperSet, Compare, Gap, Direction Cluster, Author Card and Dataset Card remain required demo flows. They retain the existing evidence and `not_novelty_proof` boundaries. User settings are per-user and cannot modify provider credentials.

## High-risk management surface

The backend already enforces `is_admin` for backup, staged restore, historical backfill and runtime configuration. Public demo hardening must add a second backend enforcement boundary for write operations even if an administrator token reaches a demo instance:

- `PUT /api/admin/runtime-config`
- backup creation/download/staged restore
- abstract-provenance backfill create/run/cancel

Read-only configuration status may remain administrator-only. UI hiding is not the security control.

## Resource contracts

- PDF upload: existing 25 MiB maximum; MIME, `.pdf` extension and `%PDF-` magic required; filename sanitized; path is under the configured per-user upload root.
- Search: query 1–500 characters, limit 1–100.
- Retrieval: query ≤1000, `top_k` ≤20.
- Backfill batch: ≤500, but the flow will be disabled in public-demo mode.
- Direction clustering and evaluation study tasks: ≤500.
- Job type has an allowlist, but job payload size and active job count are not bounded for public demo.

Minimum deployment-configurable limits are justified for public-demo users, active jobs, job payload/query length and upload size. No Redis or distributed rate limiter is justified for this supervised deployment.

## Deployment and browser surface

- Runtime backend selection accepts only HTTPS `*.trycloudflare.com` or localhost development origins and stores the value in `sessionStorage`.
- The frontend currently lacks a health state machine and polished behavior when `rn_backend` is missing or expired.
- CORS was verified to allow the exact Vercel origin and not an unrelated origin.
- Deployed headers include HSTS, `X-Content-Type-Options`, `X-Frame-Options` and `Referrer-Policy`; `Permissions-Policy` and CSP are absent.
- MCP is stdio-only and is not exposed through public HTTP routes.

## Lifecycle gaps

The current start/stop scripts use an isolated SQLite path and owned PIDs, but do not provide a runtime marker, idempotent start, stale-state recovery, PID creation identity, structured logs, status command, deterministic seed or safe reset. These are deployment-infrastructure gaps, not Frozen Core research-feature gaps.

## Claim boundary

Hardening may restrict risky deployment operations and add bounded public-demo resource contracts. It must not change OA policy, evidence levels, ranking, Gap semantics, LLM architecture, clustering semantics, author/dataset logic or expert-evaluation claims.
