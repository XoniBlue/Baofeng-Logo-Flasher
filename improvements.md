# Workspace Improvements and Upgrade Analysis

This document captures a deep analysis of the current workspace and prioritized improvements.

Migration planning reference: see `v1migration.md` for the detailed Cloudflare telemetry unification plan.

## Scope reviewed
- Frontend app: `web/`
- Cloudflare Worker: `cloudflare/log-intake-worker/`
- CI/CD: `.github/workflows/`
- Root repo structure and docs

## High-priority upgrades

### 1. Unify Cloudflare telemetry pipeline (success + errors)
- Why:
  - Success counter and error telemetry are split across different contracts and configuration styles.
  - Success path is hardcoded: `web/src/ui/flashCounter.ts`.
  - Error path is env-driven + D1-backed: `web/src/ui/clientLogReporter.ts`, `cloudflare/log-intake-worker/src/index.ts`.
- Upgrade:
  - Implement unified event pipeline described in `v1migration.md`.

### 2. Fix query drift in failure reporting SQL
- Finding:
  - `cloudflare/log-intake-worker/queries/recent_failures.sql` filters old event names (`flash_fail`, `connect_fail`, `unhandledrejection`).
  - Current app emits `flash_error`, `connect_error`, `unhandled_rejection`.
- Impact:
  - Recent failure query can silently miss real failures.
- Upgrade:
  - Update SQL filter to current event type set.

### 3. Add Worker CI coverage
- Finding:
  - `.github/workflows/ci.yml` only validates `web/**`.
  - No automated typecheck/test gate for `cloudflare/log-intake-worker/**`.
- Upgrade:
  - Add a Worker CI job for:
    - `npm ci`
    - `npx tsc --noEmit -p tsconfig.json`
    - Worker tests (once added).

### 4. Remove hardcoded runtime service URL
- Finding:
  - `COUNTER_BASE_URL` is hardcoded in `web/src/ui/flashCounter.ts`.
- Impact:
  - Harder environment promotion and incident response.
- Upgrade:
  - Move to `VITE_COUNTER_BASE_URL` (or unified `VITE_TELEMETRY_BASE_URL`).

## Medium-priority upgrades

### 5. Add versioned D1 migrations
- Finding:
  - Worker uses single `schema.sql`; no migration history or schema-version checks.
- Upgrade:
  - Introduce `migrations/00x_*.sql` and migration script in CI/deploy runbook.

### 6. Harden Worker payload validation
- Finding:
  - Worker defines `MAX_LINE_CHARS` and `MAX_LOG_LINES`, but currently trusts `log_lines_json` string shape.
  - `event_type` currently accepts any string.
- Upgrade:
  - Parse and validate `log_lines_json` shape and enforce current limits.
  - Enforce `event_type` enum.
  - Gracefully handle JSON parse failures in `/recent` response mapping.

### 7. Expand test coverage beyond protocol core
- Current coverage is solid for protocol internals:
  - `web/src/protocol/*.test.ts`
  - `web/src/serial/webSerialPort.test.ts`
- Gaps:
  - No frontend integration tests for primary flows.
  - No Worker endpoint tests.
- Upgrade:
  - Add integration tests for:
    - connect failure -> telemetry
    - flash success -> telemetry/counter
    - write gate behavior
    - Worker `/client-log` and `/recent` behavior.

### 8. Break up orchestration-heavy files
- Finding:
  - `web/src/App.tsx` and `web/src/protocol/uploader.ts` are large orchestration centers.
- Upgrade:
  - Extract hooks/services:
    - `useFlashFlow`
    - `useTelemetry`
    - `useSerialSession`
  - Keep UI components mostly declarative.

### 9. Root-level workspace tooling
- Finding:
  - Root has placeholder `package-lock.json` but no workspace `package.json`.
- Upgrade:
  - Create root npm workspace and unify scripts:
    - `npm run test`
    - `npm run typecheck`
    - `npm run lint`

## Low-priority upgrades

### 10. Dependency modernization roadmap
- Current state:
  - `web` stack is healthy and builds cleanly, but major updates are available (React 19, Vite 7, Vitest 4).
- Upgrade:
  - Plan a controlled major-version uplift with one compatibility branch and CI diff checks.

### 11. UX and operability polish
- Improvements:
  - Add explicit disconnect action and serial reset in UI.
  - Add retry CTA for counter/telemetry network failures.
  - Add optional copy/download for protocol logs from `StatusLog`.

### 12. Documentation synchronization
- Improve docs to reduce drift:
  - Keep event taxonomy in one source-of-truth section.
  - Document telemetry schema and endpoint contracts once unified.

## Notable strengths (keep as-is)
- Strong TypeScript strictness in frontend and Worker.
- Protocol parity test coverage is good for critical serial flow behavior.
- Frontend failure handling avoids breaking flash operations on telemetry errors.
- Privacy-conscious telemetry defaults (blank UA/page URL) are explicitly documented and implemented.

## Suggested execution order
1. Complete `v1migration.md` Phase 0-1.
2. Fix `recent_failures.sql` event filters.
3. Add Worker CI + tests.
4. Move hardcoded counter URL to env (or remove after unified telemetry cutover).
5. Introduce root workspace scripts and lint/typecheck standardization.
