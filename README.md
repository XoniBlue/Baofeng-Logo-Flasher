# Baofeng Logo Flasher v2 (Web)

<p align="left">
  <a href="https://github.com/XoniBlue/Baofeng-Logo-Flasher/actions/workflows/ci.yml"><img alt="Web CI" src="https://github.com/XoniBlue/Baofeng-Logo-Flasher/actions/workflows/ci.yml/badge.svg?branch=web-dev"></a>
  <a href="https://github.com/XoniBlue/Baofeng-Logo-Flasher/actions/workflows/pages.yml"><img alt="Deploy Pages" src="https://github.com/XoniBlue/Baofeng-Logo-Flasher/actions/workflows/pages.yml/badge.svg?branch=web-dev"></a>
  <img alt="Version" src="https://img.shields.io/badge/version-v2.1.1-0A7B61">
  <a href="https://vitejs.dev/"><img alt="Vite" src="https://img.shields.io/badge/Built%20With-Vite-646CFF?logo=vite&logoColor=white"></a>
  <a href="https://react.dev/"><img alt="React" src="https://img.shields.io/badge/UI-React-149ECA?logo=react&logoColor=white"></a>
  <a href="https://www.typescriptlang.org/"><img alt="TypeScript" src="https://img.shields.io/badge/Language-TypeScript-3178C6?logo=typescript&logoColor=white"></a>
</p>

Browser-based Baofeng boot logo flasher using Web Serial. This branch hosts the static app deployed to GitHub Pages.

> [!TIP]
> **Recommended workflow:** open the deployed site and flash from Chrome.
> Current Pages URL: `https://xoniblue.github.io/Baofeng-Logo-Flasher/`

---

## Quick Navigation

- [1) Project overview](#1-project-overview)
- [2) What this app does / does not do](#2-what-this-app-does--does-not-do)
- [3) Requirements](#3-requirements)
- [4) Quick start (deployed app)](#4-quick-start-deployed-app)
- [5) Local development](#5-local-development)
- [6) Testing and build](#6-testing-and-build)
- [7) GitHub Pages deployment](#7-github-pages-deployment)
- [8) Client diagnostic logging (Cloudflare)](#8-client-diagnostic-logging-cloudflare)
- [9) Safety notes](#9-safety-notes)
- [10) Supported models and behavior](#10-supported-models-and-behavior)
- [11) Troubleshooting](#11-troubleshooting)
- [12) Repository layout](#12-repository-layout)

---

## 1) Project overview

This web client flashes boot logos to supported Baofeng radios directly from the browser via Web Serial.

Highlights:
- Runs fully client-side (no hosted flashing backend).
- Converts images to radio payload format (RGB565) in-browser.
- Supports simulation mode and explicit write confirmation.
- Includes protocol logging for troubleshooting.

---

## 2) What this app does / does not do

### What it does

- Selects a serial port with Chrome Web Serial.
- Converts uploaded images to `160x128` RGB565 payload data.
- Uploads frames using the A5 logo protocol flow used by this project.
- Supports simulation (dry-run) without radio writes.

### What it does not do

- Does not provide cloud or remote flashing.
- Does not run in Safari/Firefox (Web Serial not supported there).
- Does not bypass write confirmation safeguards.

---

## 3) Requirements

| Requirement | Details |
|---|---|
| Browser | Chrome / Chromium with Web Serial support |
| Connection | Data-capable USB cable + accessible serial device |
| Origin security | HTTPS (GitHub Pages) or localhost |
| Runtime | Node.js `22` for local development |

---

## 4) Quick start (deployed app)

1. Open: `https://xoniblue.github.io/Baofeng-Logo-Flasher/`
2. Choose model profile.
3. Select serial port.
4. Upload logo image.
5. Run simulation first, then enable write mode and flash.

---

## 5) Local development

```bash
git clone https://github.com/XoniBlue/Baofeng-Logo-Flasher.git
cd Baofeng-Logo-Flasher
npm --prefix web ci
npm --prefix web run dev
```

Then open the local Vite URL shown in terminal (typically `http://localhost:5173`).

---

## 6) Testing and build

Run tests:

```bash
npm --prefix web test
```

Build production assets:

```bash
npm --prefix web run build
```

Preview built output locally:

```bash
npm --prefix web run preview
```

### Root command shortcuts (Makefile)

From repository root, you can run the common workflow without changing directories:

```bash
make dev            # web + worker local dev
make preflight      # web test + web build + worker typecheck
make errors LIMIT=20 ADMIN_TOKEN=...   # recent errors
make success        # unified successful flash count
make cf-migrate     # apply telemetry migration remotely
make cf-deploy      # deploy Cloudflare worker
```

---

## 7) GitHub Pages deployment

This branch uses `.github/workflows/pages.yml`.

Deployment behavior:
- Trigger: push to `web-dev`.
- Build/test working directory: `web/`.
- Published artifact: `web/dist`.
- Target URL: `https://xoniblue.github.io/Baofeng-Logo-Flasher/`

If a push does not appear immediately, check Actions:
- `Deploy Pages (web-dev)` workflow run status.

---

## 8) Client diagnostic logging (Cloudflare)

The web app can optionally send client-side error diagnostics (for example Web Serial failures) to a Cloudflare Worker.

Transparency policy:
- Logging is error-focused only (no full session/activity tracking).
- Logs are used for troubleshooting radio flash failures and compatibility issues.

What is sent:
- Error type/message/stack (truncated).
- Model, write mode, and connection state.
- Timestamped in-app protocol log lines (truncated).

What is not sent:
- Uploaded image payload bytes.
- Serial frame binary data.
- Browser user-agent, URL path/query, origin header, or IP-derived fields.

### Setup steps

1. Deploy the Worker in `cloudflare/log-intake-worker/`:
```bash
cd cloudflare/log-intake-worker
npm ci
wrangler d1 create baofeng_logs
# paste returned database_id into wrangler.toml
wrangler d1 execute baofeng_logs --file ./schema.sql --remote
wrangler d1 execute baofeng_logs --file ./migrations/001_telemetry_events.sql --remote
wrangler secret put ADMIN_TOKEN
npm run deploy
```
2. Copy Worker ingest URL:
   - `https://<worker-subdomain>.workers.dev/client-log`
3. In GitHub repo settings, add **Repository variable**:
   - `VITE_LOG_INGEST_URL` = Worker ingest URL.
   - `VITE_TELEMETRY_BASE_URL` = Log Worker base URL (for unified `/event` and `/metrics` endpoints).
   - `VITE_TELEMETRY_UNIFIED` = `1` to enable unified event writes.
4. Push to `web-dev` so Pages rebuilds with that env var.

### Local development

Create `web/.env.local`:
```bash
VITE_APP_VERSION=dev-local
VITE_LOG_INGEST_URL=https://<worker-subdomain>.workers.dev/client-log
VITE_TELEMETRY_BASE_URL=https://<worker-subdomain>.workers.dev
VITE_TELEMETRY_UNIFIED=1
```

### Reading logs

Direct D1 query:
```bash
cd cloudflare/log-intake-worker
wrangler d1 execute baofeng_logs --remote --file ./queries/recent_failures.sql
```

API query (admin token required):
```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "https://<worker-subdomain>.workers.dev/recent?limit=50"
```

Retention cleanup (delete logs older than 30 days):
```bash
cd cloudflare/log-intake-worker
npm run retention:30d
```

---

## 9) Safety notes

- Keep **Write mode off** until simulation succeeds.
- When prompted, type `WRITE` only when you are sure the model/profile is correct.
- Use stable power/cable connection during writes.
- If upload fails mid-write, retry only after reconnecting and re-entering programming mode on the radio.

---

## 10) Supported models and behavior

This app targets UV-5RM / UV-17-family logo flashing workflows and follows the protocol reference captured in:

- `MAIN_APP_PROTOCOL_REFERENCE.md`

The reference defines constants, frame structure, CRC behavior, safety expectations, and parity requirements with the main Python app.

---

## 11) Troubleshooting

### Browser does not show serial devices

- Use Chrome/Chromium.
- Confirm cable is data-capable.
- Confirm OS serial permissions.

### Pages site looks stale after deploy

- Hard refresh (`Cmd+Shift+R` / `Ctrl+F5`).
- Open the full repository Pages URL (not root user site).

### Flash button disabled

- Ensure image is loaded.
- If write mode is enabled, ensure port is selected.

---

## 12) Repository layout

```text
.
├─ cloudflare/
│  └─ log-intake-worker/    # Worker + D1 schema for client diagnostics
├─ web/
│  ├─ src/                  # React app source
│  ├─ package.json          # Scripts and deps
│  └─ vite.config.ts        # Vite config
├─ .github/workflows/
│  ├─ ci.yml                # Test + build checks
│  └─ pages.yml             # GitHub Pages deployment
└─ MAIN_APP_PROTOCOL_REFERENCE.md
```

---

For the Python CLI/Streamlit app and full project docs, see the `main` branch of this repository.
