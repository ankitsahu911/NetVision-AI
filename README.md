# NetVision-AI
# SmartNet AI

A local network and Wi-Fi analyzer that runs on your computer to help you understand your connection quality, connected devices, and browser performance — paired with a companion browser extension.

## Overview

SmartNet AI helps you understand:
- How strong your Wi-Fi connection is
- Which devices are connected to your network
- Whether your connection is good enough for streaming, meetings, gaming, and browsing
- How to improve your browser's performance

The project has two main parts:
1. **A local companion service** written in Python
2. **A browser extension** for Chrome, Edge, and Brave

---

## Technologies Used

| Language / Tool | Purpose | Key Files |
|---|---|---|
| **Python** | Core logic: network scanning, device detection, speed/latency testing, health reports, local API, web server | `app.py` |
| **HTML** | Web page structure | `index.html`, `popup.html` |
| **CSS** | Styling and layout | `styles.css`, `popup.css` |
| **JavaScript** | Dashboard and extension interactivity | `app.js`, `popup.js` |
| **JSON** | Manifest/config files | `manifest.json` |
| **Docker** | Containerized deployment | `Dockerfile`, `docker-compose.yml`, `docker-compose.linux-host.yml` |
| **Batch scripts** | Windows execution and EXE packaging | `build-exe.bat`, `run.bat`, `run-docker.bat`, `SmartNetDeviceScanner.spec` |

### Internal Libraries

The project relies primarily on Python's standard library and has minimal third-party dependencies:
- `socket` — network communication
- `subprocess` — running system commands
- `urllib` — web requests
- `ipaddress` — IP and network handling
- `json` — data processing
- `http.server` — local web server
- `threading` / `concurrent` — concurrent operations

---

## Features

### 🔍 Wi-Fi Health Analysis
Checks your connection quality and gives it a score out of 100.

### ⚡ Speed Testing
Measures:
- Download speed
- Upload speed
- Ping / latency
- Jitter
- Packet loss

### 📡 Device Scanning
Discovers devices connected to your local network — phones, laptops, smart TVs, routers, and more.

### 🩺 Network Diagnosis
Provides a rule-based diagnosis, flagging issues such as:
- Weak signal
- High latency
- Excess network load
- Possible bandwidth issues

### 🎯 Activity Readiness
Tells you whether your connection is suitable for:
- Browsing
- Meetings
- Streaming
- Gaming
- Cloud gaming
- 8K streaming

### 🧹 Browser Optimization
The extension can inspect browser tabs and suspend inactive background tabs, reducing memory usage and improving performance.

### 📊 History & Export
Stores past results and supports exporting history as CSV.

### 🖥️ Local Web Dashboard
View all results visually in your browser.

### 📦 Packaging Support
Run SmartNet AI as:
- A native Python app
- A Docker container
- A Windows executable

---

## Browser Extension

Yes — SmartNet AI includes a browser extension.

- Built with **Manifest V3**
- Communicates with the local Python service running on `localhost:5000`
- Displays:
  - Network health
  - Device count
  - Tab info
  - Streaming/meeting activity status
  - Optimization suggestions

> **Note:** The extension alone cannot fully scan all devices on the network — it depends on the local companion service running in the background. Think of it as a companion UI for the main app, not a standalone tool.

---

## Project Structure

```
├── app.py                              # Core backend logic
├── static/
│   ├── index.html                      # Web dashboard page
│   └── app.js                          # Dashboard logic
├── extension/
│   ├── popup.html                      # Extension popup UI
│   ├── popup.js                        # Extension popup logic
│   └── manifest.json                   # Extension manifest (Manifest V3)
├── manifest.json                       # App-level manifest/config
├── Dockerfile                          # Container image definition
├── docker-compose.yml                  # Docker Compose setup
├── docker-compose.linux-host.yml       # Docker Compose (Linux host networking)
├── build-exe.bat                       # Build Windows executable
├── run.bat                             # Run app on Windows
├── run-docker.bat                      # Run app via Docker on Windows
├── SmartNetDeviceScanner.spec          # PyInstaller packaging spec
└── PACKAGING.md                        # Packaging instructions
```

---

## Getting Started

### Option 1: Run with Python
```bash
python app.py
```
Then open your browser to `http://localhost:5000`.

### Option 2: Run with Docker
```bash
docker-compose up
```

### Option 3: Run as Windows Executable
See `PACKAGING.md` for build instructions, or use the prebuilt executable if available.

### Install the Browser Extension
1. Open Chrome/Edge/Brave and go to the extensions page (`chrome://extensions`).
2. Enable **Developer Mode**.
3. Click **Load unpacked** and select the `extension/` folder.
4. Make sure the local companion service is running on `localhost:5000`.

---

## Summary

SmartNet AI is a local, Python-based Wi-Fi analyzer and browser optimization tool that scans your network, tests connection quality, diagnoses issues, and works alongside a Chrome/Edge/Brave extension all without heavy third-party dependencies.
