# Baofeng Logo Flasher

Flash custom boot logos to your Baofeng radio directly from your browser—no installation required.

**[🚀 Try it now](https://xoniblue.github.io/Baofeng-Logo-Flasher/)** | **[📖 Quick Start](#-quick-start)** | **[🛠️ Development](#-local-development)**

<p align="left">
  <a href="https://github.com/XoniBlue/Baofeng-Logo-Flasher/actions/workflows/ci.yml"><img alt="Web CI" src="https://github.com/XoniBlue/Baofeng-Logo-Flasher/actions/workflows/ci.yml/badge.svg?branch=web-dev"></a>
  <a href="https://github.com/XoniBlue/Baofeng-Logo-Flasher/actions/workflows/pages.yml"><img alt="Deploy Pages" src="https://github.com/XoniBlue/Baofeng-Logo-Flasher/actions/workflows/pages.yml/badge.svg?branch=web-dev"></a>
  <img alt="Version" src="https://img.shields.io/badge/version-v0.9.0-0A7B61">
  <a href="https://vitejs.dev/"><img alt="Vite" src="https://img.shields.io/badge/Built%20With-Vite-646CFF?logo=vite&logoColor=white"></a>
  <a href="https://react.dev/"><img alt="React" src="https://img.shields.io/badge/UI-React-149ECA?logo=react&logoColor=white"></a>
  <a href="https://www.typescriptlang.org/"><img alt="TypeScript" src="https://img.shields.io/badge/Language-TypeScript-3178C6?logo=typescript&logoColor=white"></a>
</p>

---

<!-- TODO: Add demo GIF showing the flash process -->
<!-- ![Demo GIF](docs/demo.gif) -->

<!-- TODO: Add screenshot of the app interface -->
<!-- ![App Screenshot](docs/screenshot.png) -->

---

> [!CAUTION]
> **CHROME/CHROMIUM ONLY**
>
> This app requires **Chrome** or **Chromium-based browsers** (Edge, Brave, Opera) to function. It will **NOT work** in:
> - ❌ Firefox (no Web Serial API support)
> - ❌ Safari (no Web Serial API support)
> - ❌ Mobile browsers (Web Serial unavailable)
>
> **Web Serial API is only available in Chrome/Chromium desktop browsers.**

> [!WARNING]
> **First-time users:** Always run in **simulation mode** first. Incorrect flashing can damage your radio. Read [Safety Notes](#-safety-notes) before proceeding.

---

## 🚀 Quick Start

### Prerequisites
- **Chrome** or **Chromium-based browser** (Edge, Brave, Opera)
- USB cable with **data capability** (not charge-only)
- Radio in programming mode (consult your manual)

### Steps

1. **Open the app**: [xoniblue.github.io/Baofeng-Logo-Flasher](https://xoniblue.github.io/Baofeng-Logo-Flasher/)

2. **Select your radio model** from the dropdown

3. **Connect your radio**:
   - Put radio in programming mode (consult your manual)
   - Click "Select Serial Port"
   - Choose your USB cable from the browser dialog

4. **Upload your logo**: 160×128 pixel image (PNG, JPG, or BMP)

5. **Test first**: Click "Flash (Simulation)" and verify it completes successfully

6. **Flash for real**:
   - Enable write mode
   - Type `WRITE` when prompted to confirm
   - Click "Flash"

💡 **Tip**: Keep write mode OFF until simulation succeeds. The app will prompt you to type `WRITE` as a safety confirmation before any actual flashing occurs.

---

## 📋 Requirements

| Requirement | Details |
|-------------|---------|
| **Browser** | Chrome / Chromium / Edge / Brave / Opera (desktop only) |
| **Connection** | Data-capable USB cable + accessible serial device |
| **Security** | HTTPS (GitHub Pages) or `localhost` for Web Serial access |
| **Image** | 160×128 pixels (auto-converted to RGB565 format) |
| **Development** | Node.js 22+ (only for local development) |

---

## ✨ Features & Compatibility

### What it does

✅ Runs fully client-side (no backend server needed)
✅ Converts images to radio-compatible RGB565 format in-browser
✅ Supports simulation mode (dry-run) without writing to radio
✅ Explicit write confirmation safeguard (type `WRITE` to proceed)
✅ Protocol logging for troubleshooting
✅ Direct Web Serial connection to Baofeng radios

### What it does not do

❌ Does not provide cloud or remote flashing
❌ Does not run in Safari/Firefox (Web Serial not supported)
❌ Does not bypass write confirmation safeguards
❌ Does not support mobile browsers

### Supported Models

This app targets **UV-5RM / UV-17-family** logo flashing workflows. Protocol reference documented in `MAIN_APP_PROTOCOL_REFERENCE.md`.

| Model Family | Status | Notes |
|--------------|--------|-------|
| UV-5RM | ✅ Tested | Primary target |
| UV-17 series | ✅ Tested | Full support |
| Other UV-5R variants | ⚠️ Untested | May work, use simulation first |

> [!NOTE]
> For other Baofeng models, always run simulation mode first to verify compatibility.

---

## ⚠️ Safety Notes

**Critical safety guidelines:**

- ✋ Keep **Write mode OFF** until simulation succeeds
- ✋ Type `WRITE` only when you are **certain** the model/profile is correct
- 🔌 Use stable power and cable connection during writes
- 🔁 If upload fails mid-write, **reconnect and re-enter programming mode** before retrying
- 📖 When in doubt, consult your radio's manual for programming mode instructions

**Why these precautions matter:** Incorrect logo data or interrupted writes can potentially brick your radio's boot process. The simulation mode and write confirmation are your safety nets.

---

## ❓ FAQ

### Can I run this offline?

Yes! Clone the repository and run it locally (see [Local Development](#-local-development)). Once running, it works without internet access.

### What image formats are supported?

PNG, JPG, and BMP. The app automatically converts and resizes to 160×128 RGB565 format.

### Why does it ask me to type "WRITE"?

This is a safety confirmation to prevent accidental flashing. It ensures you consciously choose to write to your radio after simulation succeeds.

### My radio isn't listed in the models dropdown

Try the closest family match (e.g., UV-5RM or UV-17). Always test with simulation mode first. If it works, your radio is compatible.

### Can I use this on my phone?

No. Web Serial API is not available on mobile browsers (iOS or Android).

### Does this work with Chirp cables?

Yes, as long as the cable presents a serial port to your system and your browser can access it.

---

## 🔧 Troubleshooting

### No serial ports appear

**Symptoms**: Browser shows no devices when clicking "Select Serial Port"

**Solutions**:
- ✅ Confirm you're using Chrome/Chromium (not Firefox/Safari)
- ✅ Check USB cable supports data transfer (not charge-only)
- ✅ Try a different USB port on your computer
- ✅ **Windows**: Install CH340 or CP2102 drivers ([link](http://www.wch-ic.com/downloads/CH341SER_ZIP.html))
- ✅ **Linux**: Add your user to the `dialout` group:
  ```bash
  sudo usermod -a -G dialout $USER
  # Log out and back in for changes to take effect
  ```
- ✅ **macOS**: No special drivers usually needed, but check System Preferences → Security if port access is blocked

### Flash fails immediately

**Symptoms**: Flash button clicks but operation fails instantly

**Solutions**:
- ✅ Confirm radio is in programming mode (consult manual)
- ✅ Try disconnecting/reconnecting the USB cable
- ✅ Close other apps that might be using the serial port (Chirp, putty, etc.)
- ✅ Check protocol logs (enabled in app settings) for error details

### App shows "Stale" or doesn't update after deployment

**Symptoms**: GitHub Pages shows old version after updates

**Solutions**:
- Hard refresh: `Cmd+Shift+R` (Mac) or `Ctrl+F5` (Windows/Linux)
- Clear browser cache for the GitHub Pages domain
- Verify the Pages workflow completed successfully in Actions tab

### Upload succeeds in simulation but fails in write mode

**Symptoms**: Simulation completes but real write fails

**Solutions**:
- ✅ Ensure radio remains in programming mode
- ✅ Check cable connection is secure
- ✅ Verify battery is charged (low power can cause write failures)
- ✅ Try a different USB port or cable
- ✅ Re-enter programming mode on radio and retry

### Browser crashes or freezes during flash

**Symptoms**: Tab becomes unresponsive mid-flash

**Solutions**:
- ✅ Close other Chrome tabs to free memory
- ✅ Disable browser extensions that might interfere
- ✅ Try a different USB port
- ✅ Check for Chrome updates
- ✅ If persistent, test on a different computer

---

## 🛠️ Local Development

Want to run the app locally or contribute? Here's how to set it up:

### Clone and Install

```bash
git clone https://github.com/XoniBlue/Baofeng-Logo-Flasher.git
cd Baofeng-Logo-Flasher
npm --prefix web ci
```

### Run Development Server

```bash
npm --prefix web run dev
```

**Expected output:**
```
VITE v5.x.x  ready in 234 ms
➜  Local:   http://localhost:5173/
➜  Network: use --host to expose
```

Open the local URL in Chrome (typically `http://localhost:5173`).

### Testing

Run the test suite:

```bash
npm --prefix web test
```

### Build for Production

Generate optimized static files:

```bash
npm --prefix web run build
```

Preview the production build locally:

```bash
npm --prefix web run preview
```

### Optional local shortcuts

If you keep a personal root `Makefile`/`GNUmakefile`, you can use local command aliases
for dev/build/deploy. These convenience targets are **not tracked in this branch** by default.

---

## 📊 Client Diagnostic Logging

<details>
<summary><b>ℹ️ Transparency: What Gets Logged</b></summary>

The deployed GitHub Pages app sends anonymous error diagnostics to help improve compatibility and troubleshoot flash failures.

**What is sent:**
- Error type/message/stack (truncated)
- Model selection, write mode state, connection status
- Timestamped protocol log lines (truncated)

**What is NOT sent:**
- ❌ Your uploaded image data
- ❌ Serial frame binary content
- ❌ Browser fingerprints, IP addresses, or personal info
- ❌ Session tracking or usage analytics

**If you run locally:** Logging is automatically disabled unless you configure worker endpoints (which you probably won't). Your local instance runs completely isolated.

> **For maintainers:** Worker deployment and log query setup is documented in `cloudflare/log-intake-worker/README.md`

</details>

---

## 📁 Repository Layout

```text
.
├─ cloudflare/
│  └─ log-intake-worker/    # Worker + D1 schema for client diagnostics
├─ web/
│  ├─ src/                  # React app source
│  ├─ package.json          # Scripts and dependencies
│  └─ vite.config.ts        # Vite configuration
├─ .github/workflows/
│  ├─ ci.yml                # Test + build checks
│  └─ pages.yml             # GitHub Pages deployment
├─ MAIN_APP_PROTOCOL_REFERENCE.md  # Protocol documentation
└─ README.md                # This file
```

---

## 📄 License

<!-- TODO: Add license information -->

---

## 🙏 Contributing

Contributions welcome! For the Python CLI/Streamlit app and full project documentation, see the `main` branch of this repository.

**Bug reports and feature requests**: Open an issue on GitHub.

---

**Open-source firmware tools. Built by radio hackers, for radio hackers.** 🛠️📻
