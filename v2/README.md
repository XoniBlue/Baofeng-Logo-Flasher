# Baofeng Logo Flasher v2 (Web)

Static GitHub Pages app for flashing boot logos in-browser via Web Serial.

## Requirements

- Google Chrome / Chromium
- HTTPS origin (GitHub Pages) or localhost
- Supported radio and data USB cable

## Local run

```bash
cd v2/web
npm install
npm test
npm run dev
```

## Build for Pages

```bash
cd v2/web
npm run build
```

Publish `v2/web/dist`.
