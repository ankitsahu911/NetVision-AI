# Packaging For Users Without Python

There are three ways to share this project.

## Best For Development

Share the project folder and run:

```powershell
python app.py
```

This requires Python on the user's PC.

## Best For A Demo Without Python (Recommended)

Build a Windows `.exe` once, then share it with others.

### For The Developer

To build the EXE:

```powershell
.\build-exe.bat
```

Output:

```text
dist\SmartNetDeviceScanner.exe
```

### For End Users

Users can:

1. Download `SmartNetDeviceScanner.exe`
2. Double-click to run it (no installation or dependencies needed)
3. Open `http://localhost:5000` in a browser

**No Python, no Docker, no setup required.**

This is the best option for Windows because the scanner runs natively and can see the local network better than Docker.

## Docker Option

If the user has Docker Desktop:

```powershell
docker compose up --build
```

Then open:

```text
http://localhost:5000
```

Docker avoids installing Python, but on Windows and macOS it may scan Docker's internal network instead of the real Wi-Fi network.
