# SmartNet AI WiFi Health Analyzer

SmartNet AI is a local WiFi speed checker, device scanner, browser optimizer, and rule-based network diagnosis project.

It has two parts:

- Companion service: runs on the PC and scans speed, latency, packet loss, and visible network devices.
- Browser extension: runs in Chrome, Edge, or Brave and shows the report, detects heavy tabs, and can suspend background tabs.

## Quick Start (No Dependencies)

**Best for sharing with others:**

1. Download `dist\SmartNetDeviceScanner.exe`
2. Double-click to run
3. Open `http://localhost:5000` in your browser

No Python, Docker, or installation needed.

## Project Structure

```text
connected-device-scanner/
  app.py                         Companion service, API, speed test, diagnosis
  static/                        Full web dashboard
  extension/                     Chrome/Edge/Brave extension
  manifest.json                  Root extension manifest
  Dockerfile                     Docker image for the companion service
  docker-compose.yml             Standard Docker run
  docker-compose.linux-host.yml  Linux host-network Docker run
  run.bat                        Native Python starter
  run-docker.bat                 Docker starter
  build-exe.bat                  Windows EXE builder
  PACKAGING.md                   Sharing and packaging notes
```

## Run With Python

```powershell
cd C:\Users\anknk\Documents\Codex\2026-06-21\bu\outputs\connected-device-scanner
python app.py
```

Open:

```text
http://localhost:5000
```

Useful terminal commands:

```powershell
python app.py scan
python app.py speed
python app.py report
python app.py report --json
```

## Run With Docker

Use this if Python is not installed but Docker Desktop is installed.

```powershell
cd C:\Users\anknk\Documents\Codex\2026-06-21\bu\outputs\connected-device-scanner
docker compose up --build
```

Open:

```text
http://localhost:5000
```

Important: Docker on Windows/macOS may scan Docker's internal network instead of the real WiFi network. For best device detection on Windows, use Python or build the `.exe`.

On Linux:

```bash
docker compose -f docker-compose.linux-host.yml up --build
```

## Build A Windows EXE

```powershell
build-exe.bat
```

Output:

```text
dist\SmartNetDeviceScanner.exe
```

This is the best sharing option for users who do not have Python.

## Load The Browser Extension

Start the companion service first.

Then in Chrome, Edge, or Brave:

1. Open `chrome://extensions`, `edge://extensions`, or `brave://extensions`.
2. Turn on Developer mode.
3. Click Load unpacked.
4. Select the main project folder:

```text
C:\Users\anknk\Documents\Codex\2026-06-21\bu\outputs\connected-device-scanner
```

The extension calls:

```text
http://localhost:5000
```

## Main APIs

```text
GET  /api/scan
GET  /api/speed-test
GET  /api/health-report
GET  /api/history
GET  /api/history.csv
POST /api/diagnosis
```

## Features

- Download speed test.
- Best-effort upload speed test.
- TCP latency, jitter, and packet-loss estimate.
- Connected-device scanner.
- WiFi Health Score out of 100.
- Activity readiness for browsing, meetings, 4K streaming, gaming, cloud gaming, and 8K streaming.
- AI-style local diagnosis engine.
- Potential speed-gain suggestions.
- Browser tab analyzer.
- One-click browser optimizer using Chrome tab discard.
- History dashboard and CSV export.
- Docker and Windows EXE packaging support.

## Important Limitations

- A browser extension alone cannot count all WiFi devices. The local companion service is required.
- Some routers and hotspots isolate clients, so device count is best effort.
- Browser APIs cannot see bandwidth used by apps outside the browser.
- Upload testing depends on public upload endpoints and may fail on restricted networks.
- The AI diagnosis is a local rule engine, not a paid cloud AI model.

## Suggested Final-Year Project Title

```text
SmartNet AI: An Intelligent WiFi Performance Analyzer with Browser Optimization and Automated Network Diagnosis
```
