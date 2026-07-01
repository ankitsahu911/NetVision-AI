from __future__ import annotations

import argparse
import concurrent.futures
import ipaddress
import json
import math
import os
import platform
import re
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
STATIC_DIR = APP_DIR / "static"
DATA_DIR = Path.cwd() / "smartnet-data"
HISTORY_FILE = DATA_DIR / "history.json"
IS_WINDOWS = platform.system().lower().startswith("win")
CACHE_TTL_SECONDS = 20

SCAN_CACHE: dict[str, object] = {"time": 0.0, "data": None}
SPEED_CACHE: dict[str, object] = {"time": 0.0, "data": None}
REPORT_CACHE: dict[str, object] = {"time": 0.0, "data": None}

PRIVATE_RANGES = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)

VENDOR_HINTS = {
    "00:1A:11": "Google",
    "00:1B:63": "Apple",
    "00:1C:B3": "Apple",
    "00:23:12": "Apple",
    "00:26:BB": "Apple",
    "08:00:27": "VirtualBox",
    "10:02:B5": "Intel",
    "18:65:90": "Apple",
    "1C:1B:0D": "Samsung",
    "20:16:B9": "Intel",
    "24:A2:E1": "Apple",
    "28:18:78": "Microsoft",
    "2C:F0:5D": "Samsung",
    "34:AB:37": "Apple",
    "38:F9:D3": "Apple",
    "3C:5A:B4": "Google",
    "40:4E:36": "HTC",
    "44:65:0D": "Amazon",
    "48:4B:AA": "Apple",
    "50:F5:DA": "Amazon",
    "54:60:09": "Google",
    "5C:F9:38": "Apple",
    "60:01:94": "Espressif",
    "64:16:66": "Samsung",
    "68:3E:34": "Apple",
    "70:3E:AC": "Apple",
    "74:E5:43": "Apple",
    "78:4F:43": "Apple",
    "80:EA:96": "Apple",
    "84:38:35": "Apple",
    "8C:85:90": "Apple",
    "90:72:40": "Apple",
    "94:65:2D": "OnePlus",
    "98:01:A7": "Apple",
    "A0:02:DC": "Amazon",
    "A4:5E:60": "Apple",
    "A4:77:33": "Google",
    "AC:37:43": "HTC",
    "B0:34:95": "Apple",
    "B4:F0:AB": "Apple",
    "B8:27:EB": "Raspberry Pi",
    "BC:92:6B": "Apple",
    "C0:EE:FB": "OnePlus",
    "C8:3A:35": "TP-Link",
    "D0:03:4B": "Apple",
    "D4:A3:3D": "Apple",
    "D8:BB:2C": "Apple",
    "DC:A6:32": "Raspberry Pi",
    "E0:CB:BC": "Cisco",
    "E4:5F:01": "Raspberry Pi",
    "E8:50:8B": "Samsung",
    "F0:18:98": "Apple",
    "F4:F5:D8": "Google",
    "FC:FC:48": "Apple",
}

LATENCY_TARGETS = (
    ("Cloudflare DNS", "1.1.1.1", 443),
    ("Google DNS", "8.8.8.8", 443),
    ("Cloudflare", "speed.cloudflare.com", 443),
)

DOWNLOAD_TESTS = (
    "https://speed.cloudflare.com/__down?bytes=12000000",
    "https://proof.ovh.net/files/10Mb.dat",
    "https://ipv4.download.thinkbroadband.com/10MB.zip",
)

UPLOAD_TESTS = (
    "https://speed.cloudflare.com/__up",
    "https://httpbin.org/post",
)

STREAMING_HOSTS = (
    "youtube.com",
    "youtu.be",
    "netflix.com",
    "primevideo.com",
    "hotstar.com",
    "disneyplus.com",
    "twitch.tv",
    "spotify.com",
    "soundcloud.com",
)

MEETING_HOSTS = (
    "meet.google.com",
    "zoom.us",
    "teams.microsoft.com",
    "webex.com",
)

DOWNLOAD_HOSTS = (
    "drive.google.com",
    "dropbox.com",
    "mega.nz",
    "mediafire.com",
    "github.com",
    "gitlab.com",
    "onedrive.live.com",
)


def command_flags() -> int:
    if IS_WINDOWS and hasattr(subprocess, "CREATE_NO_WINDOW"):
        return subprocess.CREATE_NO_WINDOW
    return 0


def run_command(args: list[str], timeout: float = 4.0) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout,
            creationflags=command_flags(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def clean_ipv4(value: str) -> str | None:
    match = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", value)
    if not match:
        return None
    try:
        ipaddress.ip_address(match.group(1))
    except ValueError:
        return None
    return match.group(1)


def is_private_lan_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return any(ip in network for network in PRIVATE_RANGES)


def parse_windows_ipconfig() -> list[dict[str, str | None]]:
    result = run_command(["ipconfig"], timeout=5)
    if not result or not result.stdout:
        return []

    adapters: list[dict[str, str | None]] = []
    current: dict[str, str | None] | None = None
    expecting_gateway = False

    for raw_line in result.stdout.splitlines():
        line = raw_line.rstrip()
        header = re.match(r"^[^\s].*adapter\s+(.+):$", line, flags=re.IGNORECASE)
        if header:
            if current and current.get("ip"):
                adapters.append(current)
            current = {"name": header.group(1).strip(), "ip": None, "mask": None, "gateway": None}
            expecting_gateway = False
            continue

        if not current:
            continue

        if "IPv4 Address" in line:
            current["ip"] = clean_ipv4(line)
            expecting_gateway = False
        elif "Subnet Mask" in line:
            current["mask"] = clean_ipv4(line)
            expecting_gateway = False
        elif "Default Gateway" in line:
            gateway = clean_ipv4(line)
            if gateway:
                current["gateway"] = gateway
                expecting_gateway = False
            else:
                expecting_gateway = True
        elif expecting_gateway:
            gateway = clean_ipv4(line)
            if gateway:
                current["gateway"] = gateway
                expecting_gateway = False
            elif line.strip():
                expecting_gateway = False

    if current and current.get("ip"):
        adapters.append(current)

    return [adapter for adapter in adapters if adapter.get("ip") and is_private_lan_ip(str(adapter["ip"]))]


def discover_local_ip_fallback() -> str | None:
    probes = ("8.8.8.8", "1.1.1.1")
    for probe in probes:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect((probe, 80))
            local_ip = sock.getsockname()[0]
            if is_private_lan_ip(local_ip):
                return local_ip
        except OSError:
            pass
        finally:
            sock.close()

    try:
        host_ip = socket.gethostbyname(socket.gethostname())
        if is_private_lan_ip(host_ip):
            return host_ip
    except OSError:
        pass

    return None


def network_from_ip_and_mask(ip: str, mask: str | None) -> ipaddress.IPv4Network:
    if mask:
        try:
            return ipaddress.ip_network(f"{ip}/{mask}", strict=False)
        except ValueError:
            pass
    return ipaddress.ip_network(f"{ip}/24", strict=False)


def discover_network() -> dict[str, str | None]:
    adapters = parse_windows_ipconfig() if IS_WINDOWS else []
    adapters = [adapter for adapter in adapters if adapter.get("ip")]

    if adapters:
        adapters.sort(key=lambda item: 0 if item.get("gateway") else 1)
        adapter = adapters[0]
        local_ip = str(adapter["ip"])
        subnet_mask = str(adapter["mask"]) if adapter.get("mask") else None
        network = network_from_ip_and_mask(local_ip, subnet_mask)
        return {
            "adapter": adapter.get("name"),
            "local_ip": local_ip,
            "subnet_mask": subnet_mask,
            "gateway": str(adapter["gateway"]) if adapter.get("gateway") else None,
            "network": str(network),
        }

    local_ip = discover_local_ip_fallback()
    if not local_ip:
        return {
            "adapter": None,
            "local_ip": None,
            "subnet_mask": None,
            "gateway": None,
            "network": None,
        }

    network = ipaddress.ip_network(f"{local_ip}/24", strict=False)
    return {
        "adapter": None,
        "local_ip": local_ip,
        "subnet_mask": "255.255.255.0",
        "gateway": None,
        "network": str(network),
    }


def bounded_scan_network(network_value: str, local_ip: str, max_hosts: int) -> tuple[ipaddress.IPv4Network, list[str]]:
    notes: list[str] = []
    network = ipaddress.ip_network(network_value, strict=False)
    host_count = max(network.num_addresses - 2, 0)
    if host_count <= max_hosts:
        return network, notes

    limited = ipaddress.ip_network(f"{local_ip}/24", strict=False)
    notes.append(
        f"Detected {network} has {host_count} possible hosts, so this scan was limited to {limited}."
    )
    return limited, notes


def ping_host(ip: str, timeout_ms: int) -> bool:
    if IS_WINDOWS:
        args = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
        timeout = max(1.0, (timeout_ms / 1000.0) + 0.8)
    else:
        args = ["ping", "-c", "1", "-W", str(max(1, round(timeout_ms / 1000))), ip]
        timeout = max(1.5, (timeout_ms / 1000.0) + 0.8)

    result = run_command(args, timeout=timeout)
    if not result:
        return False

    output = f"{result.stdout}\n{result.stderr}".lower()
    return result.returncode == 0 or "ttl=" in output or "ttl " in output


def normalize_mac(value: str | None) -> str | None:
    if not value:
        return None
    pieces = re.findall(r"[0-9a-fA-F]{2}", value)
    if len(pieces) < 6:
        return None
    return ":".join(piece.upper() for piece in pieces[:6])


def parse_arp_table(network: ipaddress.IPv4Network) -> dict[str, dict[str, str | None]]:
    result = run_command(["arp", "-a"], timeout=4)
    entries: dict[str, dict[str, str | None]] = {}
    if not result or not result.stdout:
        return entries

    for line in result.stdout.splitlines():
        ip_value: str | None = None
        mac_value: str | None = None
        row_type: str | None = None

        windows_row = re.match(
            r"^\s*(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-fA-F:-]{17})\s+(\w+)",
            line,
        )
        if windows_row:
            ip_value = windows_row.group(1)
            mac_value = windows_row.group(2)
            row_type = windows_row.group(3)
        else:
            unix_row = re.search(
                r"\((\d{1,3}(?:\.\d{1,3}){3})\)\s+at\s+([0-9a-fA-F:-]{17})",
                line,
            )
            if unix_row:
                ip_value = unix_row.group(1)
                mac_value = unix_row.group(2)
                row_type = "dynamic"

        if not ip_value:
            continue

        try:
            ip_obj = ipaddress.ip_address(ip_value)
        except ValueError:
            continue

        if ip_obj not in network or ip_obj in {network.network_address, network.broadcast_address}:
            continue

        mac = normalize_mac(mac_value)
        if mac == "FF:FF:FF:FF:FF:FF":
            continue
        entries[ip_value] = {"ip": ip_value, "mac": mac, "arp_type": row_type}

    return entries


def resolve_hostname(ip: str, local_ip: str | None) -> str | None:
    if local_ip and ip == local_ip:
        try:
            return socket.gethostname()
        except OSError:
            return "This computer"

    if IS_WINDOWS:
        result = run_command(["nbtstat", "-A", ip], timeout=1.4)
        if result and result.stdout:
            for line in result.stdout.splitlines():
                row = re.match(r"^\s*([A-Z0-9_-]{2,15})\s+<00>\s+UNIQUE", line, flags=re.IGNORECASE)
                if row:
                    name = row.group(1).strip()
                    if name and name.upper() not in {"WORKGROUP", "MSHOME"}:
                        return name

    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(0.8)
        host, _, _ = socket.gethostbyaddr(ip)
        return host.split(".")[0] if host else None
    except OSError:
        return None
    finally:
        socket.setdefaulttimeout(old_timeout)


def vendor_from_mac(mac: str | None) -> str | None:
    if not mac:
        return None
    return VENDOR_HINTS.get(mac[:8])


def infer_device_type(role: str, hostname: str | None, vendor: str | None) -> str:
    if role == "This computer":
        return "Computer"
    if role == "Router/Gateway":
        return "Router"

    text = " ".join(part.lower() for part in (hostname or "", vendor or ""))
    if any(token in text for token in ("iphone", "ipad", "android", "galaxy", "oneplus", "redmi", "mi phone")):
        return "Phone/Tablet"
    if any(token in text for token in ("tv", "chromecast", "firetv", "roku")):
        return "TV/Streaming"
    if any(token in text for token in ("printer", "canon", "epson", "brother")):
        return "Printer"
    if any(token in text for token in ("camera", "cam", "nvr", "dvr")):
        return "Camera"
    if any(token in text for token in ("laptop", "desktop", "pc", "dell", "hp", "lenovo", "intel", "microsoft")):
        return "Computer"
    if vendor in {"Apple", "Samsung", "Google", "OnePlus", "HTC"}:
        return "Phone/Tablet"
    if vendor in {"Amazon"}:
        return "Smart device"
    if vendor in {"Raspberry Pi", "Espressif"}:
        return "IoT/Board"
    if vendor in {"TP-Link", "Cisco"}:
        return "Network device"
    return "Unknown"


def network_load(count: int) -> dict[str, str | int]:
    if count <= 5:
        return {"level": "Low", "score": 92, "message": "A small number of devices were detected."}
    if count <= 12:
        return {"level": "Medium", "score": 76, "message": "Several devices are sharing the network."}
    return {"level": "High", "score": 58, "message": "Many devices are sharing the network."}


def recommendations(count: int, unknown_count: int, gateway_seen: bool) -> list[str]:
    tips: list[str] = []
    if count == 0:
        tips.append("No devices were detected. Check that Wi-Fi or Ethernet is connected.")
    elif count > 12:
        tips.append("Many devices were detected. Disconnect unused phones, TVs, or IoT devices before speed testing.")
    elif count > 5:
        tips.append("Run the speed test once with normal usage and once after disconnecting idle devices.")
    else:
        tips.append("Device load looks light. If speed is still low, the next check should be latency and ISP speed.")

    if unknown_count:
        tips.append("Unknown devices are normal, but you can compare these IP/MAC addresses with your router page.")
    if not gateway_seen:
        tips.append("The router was not confirmed in the ARP table. A second scan may discover more devices.")
    tips.append("For a browser extension, expose this result through the local API endpoint /api/scan.")
    return tips


def scan_devices(max_hosts: int = 254, timeout_ms: int = 350, workers: int = 64) -> dict[str, object]:
    started = time.perf_counter()
    scanned_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    notes: list[str] = []
    info = discover_network()

    if not info.get("local_ip") or not info.get("network"):
        return {
            "ok": False,
            "error": "No private Wi-Fi/Ethernet network was detected.",
            "scanned_at": scanned_at,
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "network": info,
            "scan_range": None,
            "count": 0,
            "devices": [],
            "load": network_load(0),
            "notes": ["Connect to a local Wi-Fi, hotspot, or Ethernet network and scan again."],
            "recommendations": recommendations(0, 0, False),
        }

    network, range_notes = bounded_scan_network(str(info["network"]), str(info["local_ip"]), max_hosts)
    notes.extend(range_notes)
    hosts = [str(host) for host in network.hosts()]

    reachable: set[str] = set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_map = {executor.submit(ping_host, ip, timeout_ms): ip for ip in hosts}
        for future in concurrent.futures.as_completed(future_map):
            ip = future_map[future]
            try:
                if future.result():
                    reachable.add(ip)
            except Exception:
                pass

    arp_entries = parse_arp_table(network)
    devices_by_ip: dict[str, dict[str, object | None]] = {}

    for ip, entry in arp_entries.items():
        devices_by_ip[ip] = {
            "ip": ip,
            "mac": entry.get("mac"),
            "arp_type": entry.get("arp_type"),
            "reachable": ip in reachable,
        }

    for ip in reachable:
        devices_by_ip.setdefault(
            ip,
            {"ip": ip, "mac": None, "arp_type": None, "reachable": True},
        )

    local_ip = str(info["local_ip"])
    devices_by_ip.setdefault(
        local_ip,
        {"ip": local_ip, "mac": None, "arp_type": "local", "reachable": True},
    )

    gateway_ip = str(info["gateway"]) if info.get("gateway") else None
    if gateway_ip and ipaddress.ip_address(gateway_ip) in network:
        devices_by_ip.setdefault(
            gateway_ip,
            {"ip": gateway_ip, "mac": None, "arp_type": None, "reachable": gateway_ip in reachable},
        )

    devices: list[dict[str, object | None]] = []
    for ip, device in sorted(devices_by_ip.items(), key=lambda item: ipaddress.ip_address(item[0])):
        role = "Device"
        if ip == local_ip:
            role = "This computer"
        elif gateway_ip and ip == gateway_ip:
            role = "Router/Gateway"

        hostname = resolve_hostname(ip, local_ip)
        vendor = vendor_from_mac(device.get("mac") if isinstance(device.get("mac"), str) else None)
        device_type = infer_device_type(role, hostname, vendor)
        devices.append(
            {
                "ip": ip,
                "mac": device.get("mac"),
                "hostname": hostname,
                "vendor": vendor,
                "type": device_type,
                "role": role,
                "reachable": bool(device.get("reachable")),
                "arp_type": device.get("arp_type"),
            }
        )

    unknown_count = sum(1 for device in devices if device["type"] == "Unknown")
    gateway_seen = bool(gateway_ip and gateway_ip in devices_by_ip)

    if IS_WINDOWS:
        notes.append("On Windows, this uses ping plus the local ARP table, so it does not need admin rights.")
    notes.append("Routers and mobile hotspots may hide clients from each other, so the count is best-effort.")

    duration_ms = round((time.perf_counter() - started) * 1000)
    return {
        "ok": True,
        "scanned_at": scanned_at,
        "duration_ms": duration_ms,
        "network": info,
        "scan_range": str(network),
        "count": len(devices),
        "devices": devices,
        "load": network_load(len(devices)),
        "notes": notes,
        "recommendations": recommendations(len(devices), unknown_count, gateway_seen),
    }


def cached_scan(refresh: bool, max_hosts: int, timeout_ms: int, workers: int) -> dict[str, object]:
    now = time.time()
    cached = SCAN_CACHE.get("data")
    if not refresh and cached and now - float(SCAN_CACHE["time"]) < CACHE_TTL_SECONDS:
        data = dict(cached)  # shallow copy for metadata
        data["cached"] = True
        return data

    data = scan_devices(max_hosts=max_hosts, timeout_ms=timeout_ms, workers=workers)
    data["cached"] = False
    SCAN_CACHE["time"] = now
    SCAN_CACHE["data"] = data
    return data


def safe_round(value: float | None, digits: int = 1) -> float | None:
    if value is None or math.isnan(value) or math.isinf(value):
        return None
    return round(value, digits)


def tcp_latency_once(host: str, port: int, timeout: float = 1.0) -> float | None:
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return (time.perf_counter() - started) * 1000
    except OSError:
        return None


def measure_latency(samples: int = 4) -> dict[str, object]:
    latencies: list[float] = []
    attempts = 0
    per_target: list[dict[str, object]] = []

    for sample_index in range(samples):
        name, host, port = LATENCY_TARGETS[sample_index % len(LATENCY_TARGETS)]
        attempts += 1
        latency = tcp_latency_once(host, port)
        per_target.append(
            {
                "name": name,
                "host": host,
                "ok": latency is not None,
                "latency_ms": safe_round(latency, 1),
            }
        )
        if latency is not None:
            latencies.append(latency)

    failed = attempts - len(latencies)
    packet_loss = (failed / attempts) * 100 if attempts else 100
    avg_latency = sum(latencies) / len(latencies) if latencies else None

    jitter = None
    if len(latencies) >= 2:
        diffs = [abs(latencies[index] - latencies[index - 1]) for index in range(1, len(latencies))]
        jitter = sum(diffs) / len(diffs)

    return {
        "ok": bool(latencies),
        "samples": attempts,
        "successful_samples": len(latencies),
        "ping_ms": safe_round(avg_latency, 1),
        "jitter_ms": safe_round(jitter, 1),
        "packet_loss_percent": safe_round(packet_loss, 1),
        "targets": per_target,
    }


def read_http_bytes(url: str, max_bytes: int, max_seconds: float, timeout: float) -> tuple[int, float, str | None]:
    request = Request(url, headers={"User-Agent": "SmartNetAI/1.0"})
    started = time.perf_counter()
    total = 0
    try:
        with urlopen(request, timeout=timeout) as response:
            while total < max_bytes and time.perf_counter() - started < max_seconds:
                chunk = response.read(min(131072, max_bytes - total))
                if not chunk:
                    break
                total += len(chunk)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return total, time.perf_counter() - started, str(exc)
    return total, time.perf_counter() - started, None


def measure_download(max_mb: int = 6, max_seconds: float = 4.0) -> dict[str, object]:
    max_bytes = max(1, max_mb) * 1024 * 1024
    errors: list[str] = []
    best: dict[str, object] | None = None

    for url in DOWNLOAD_TESTS[:2]:
        bytes_read, elapsed, error = read_http_bytes(url, max_bytes, max_seconds, timeout=max_seconds + 1)
        if bytes_read and elapsed > 0:
            mbps = (bytes_read * 8) / elapsed / 1_000_000
            result = {
                "ok": True,
                "url": url,
                "bytes": bytes_read,
                "seconds": safe_round(elapsed, 2),
                "mbps": safe_round(mbps, 2),
            }
            if not best or float(result["mbps"] or 0) > float(best["mbps"] or 0):
                best = result
        if error:
            errors.append(f"{url}: {error}")
        if best and float(best["seconds"] or 0) >= 2.0:
            break

    if best:
        best["errors"] = errors[:2]
        return best

    return {
        "ok": False,
        "url": None,
        "bytes": 0,
        "seconds": 0,
        "mbps": None,
        "errors": errors[:3] or ["Download test could not reach a public test server."],
    }


def post_http_bytes(url: str, size_bytes: int, timeout: float) -> tuple[int, float, str | None]:
    payload = b"0" * size_bytes
    request = Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/octet-stream",
            "User-Agent": "SmartNetAI/1.0",
        },
    )
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout) as response:
            response.read(256)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return 0, time.perf_counter() - started, str(exc)
    return size_bytes, time.perf_counter() - started, None


def measure_upload(size_mb: int = 1, max_seconds: float = 4.0) -> dict[str, object]:
    size_bytes = max(1, size_mb) * 1024 * 1024
    errors: list[str] = []

    for url in UPLOAD_TESTS[:1]:
        sent, elapsed, error = post_http_bytes(url, size_bytes, timeout=max_seconds + 1)
        if sent and elapsed > 0:
            return {
                "ok": True,
                "url": url,
                "bytes": sent,
                "seconds": safe_round(elapsed, 2),
                "mbps": safe_round((sent * 8) / elapsed / 1_000_000, 2),
                "errors": errors[:2],
            }
        if error:
            errors.append(f"{url}: {error}")

    return {
        "ok": False,
        "url": None,
        "bytes": 0,
        "seconds": 0,
        "mbps": None,
        "errors": errors[:3] or ["Upload test could not reach a public upload endpoint."],
    }


def score_speed(download_mbps: float | None) -> int:
    if download_mbps is None:
        return 0
    if download_mbps >= 100:
        return 35
    if download_mbps >= 50:
        return 31
    if download_mbps >= 25:
        return 25
    if download_mbps >= 10:
        return 17
    if download_mbps >= 3:
        return 9
    return 4


def score_latency(ping_ms: float | None) -> int:
    if ping_ms is None:
        return 0
    if ping_ms <= 25:
        return 25
    if ping_ms <= 50:
        return 21
    if ping_ms <= 90:
        return 15
    if ping_ms <= 150:
        return 8
    return 3


def score_jitter(jitter_ms: float | None) -> int:
    if jitter_ms is None:
        return 0
    if jitter_ms <= 8:
        return 15
    if jitter_ms <= 20:
        return 11
    if jitter_ms <= 40:
        return 7
    return 2


def score_loss(packet_loss: float | None) -> int:
    if packet_loss is None:
        return 0
    if packet_loss <= 0:
        return 15
    if packet_loss <= 2:
        return 11
    if packet_loss <= 5:
        return 7
    return 2


def score_device_load(device_count: int) -> int:
    if device_count <= 5:
        return 10
    if device_count <= 12:
        return 7
    if device_count <= 20:
        return 4
    return 2


def activity_recommendations(download_mbps: float | None, upload_mbps: float | None, ping_ms: float | None, jitter_ms: float | None, packet_loss: float | None) -> list[dict[str, object]]:
    download = download_mbps or 0
    upload = upload_mbps or 0
    ping = ping_ms if ping_ms is not None else 999
    jitter = jitter_ms if jitter_ms is not None else 999
    loss = packet_loss if packet_loss is not None else 100

    checks = [
        ("Browsing", download >= 2 and ping <= 250 and loss <= 10, "Basic websites and email"),
        ("Zoom Meeting", download >= 4 and upload >= 1.5 and ping <= 150 and loss <= 5, "Video calls need stable upload and low loss"),
        ("Netflix 4K", download >= 25 and ping <= 150 and loss <= 3, "4K streaming mainly needs download speed"),
        ("Online Gaming", download >= 10 and upload >= 1 and ping <= 60 and jitter <= 20 and loss <= 2, "Gaming needs low ping and low jitter"),
        ("Cloud Gaming", download >= 35 and upload >= 5 and ping <= 40 and jitter <= 12 and loss <= 1, "Cloud gaming is very sensitive to latency"),
        ("8K Streaming", download >= 80 and ping <= 120 and loss <= 2, "8K needs a very high, stable download speed"),
    ]
    return [{"name": name, "ok": ok, "reason": reason} for name, ok, reason in checks]


def classify_quality(score: int) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 50:
        return "Fair"
    return "Poor"


def build_diagnosis(speed: dict[str, object], scan: dict[str, object] | None = None, browser: dict[str, object] | None = None) -> dict[str, object]:
    scan = scan or {}
    browser = browser or {}
    download = speed.get("download_mbps")
    upload = speed.get("upload_mbps")
    ping = speed.get("ping_ms")
    jitter = speed.get("jitter_ms")
    loss = speed.get("packet_loss_percent")
    device_count = int(scan.get("count") or 0)
    tab_count = int(browser.get("tab_count") or 0)
    streaming_tabs = int(browser.get("streaming_tabs") or 0)
    meeting_tabs = int(browser.get("meeting_tabs") or 0)
    download_tabs = int(browser.get("download_tabs") or 0)

    findings: list[dict[str, object]] = []
    actions: list[dict[str, object]] = []
    estimated_gain = 0

    if download is None:
        findings.append({"title": "Speed test incomplete", "confidence": 90, "detail": "Public speed-test servers could not be reached."})
        actions.append({"title": "Check internet access or try again", "gain_mbps": 0, "type": "manual"})
    elif float(download) < 10:
        findings.append({"title": "Low download speed", "confidence": 88, "detail": "Browsing may work, but HD/4K streaming and downloads may feel slow."})
        actions.append({"title": "Close streaming/download tabs and retest", "gain_mbps": 8, "type": "browser"})
        estimated_gain += 8

    if upload is not None and float(upload) < 2:
        findings.append({"title": "Weak upload speed", "confidence": 82, "detail": "Video calls, cloud backup, and screen sharing may struggle."})
        actions.append({"title": "Pause cloud backup or large uploads", "gain_mbps": 4, "type": "browser"})
        estimated_gain += 4

    if ping is not None and float(ping) > 100:
        findings.append({"title": "High latency", "confidence": 86, "detail": "Gaming and calls may lag even if download speed is acceptable."})
        actions.append({"title": "Move closer to router or switch to 5 GHz/Ethernet", "gain_mbps": 5, "type": "wifi"})
        estimated_gain += 5

    if jitter is not None and float(jitter) > 30:
        findings.append({"title": "Unstable latency", "confidence": 84, "detail": "Jitter means the connection is fluctuating, which hurts calls and gaming."})
        actions.append({"title": "Reduce active devices and avoid router interference", "gain_mbps": 6, "type": "wifi"})
        estimated_gain += 6

    if loss is not None and float(loss) > 2:
        findings.append({"title": "Packet loss detected", "confidence": 90, "detail": "Packet loss usually points to Wi-Fi interference, congestion, or ISP instability."})
        actions.append({"title": "Restart router and retest near the router", "gain_mbps": 6, "type": "wifi"})
        estimated_gain += 6

    if device_count > 12:
        findings.append({"title": "Router/device overload possible", "confidence": 80, "detail": f"{device_count} devices were detected on the network."})
        actions.append({"title": "Disconnect idle TVs, phones, and IoT devices", "gain_mbps": 10, "type": "network"})
        estimated_gain += 10
    elif device_count > 5:
        findings.append({"title": "Several connected devices", "confidence": 65, "detail": f"{device_count} devices are sharing the network."})

    if tab_count > 25:
        findings.append({"title": "Too many browser tabs", "confidence": 78, "detail": f"{tab_count} open tabs can consume memory and background network."})
        actions.append({"title": "Suspend inactive browser tabs", "gain_mbps": 5, "type": "one_click"})
        estimated_gain += 5

    if streaming_tabs:
        findings.append({"title": "Streaming tabs detected", "confidence": 90, "detail": f"{streaming_tabs} streaming tab(s) may be consuming bandwidth."})
        actions.append({"title": "Suspend background streaming tabs", "gain_mbps": 10, "type": "one_click"})
        estimated_gain += 10

    if meeting_tabs and ping is not None and float(ping) > 80:
        findings.append({"title": "Video meeting may be unstable", "confidence": 76, "detail": "Meeting tabs are open while latency is high."})

    if download_tabs:
        findings.append({"title": "Possible download/cloud activity", "confidence": 72, "detail": f"{download_tabs} cloud/download tab(s) were found."})
        actions.append({"title": "Pause cloud uploads or downloads", "gain_mbps": 8, "type": "manual"})
        estimated_gain += 8

    if not findings:
        findings.append({"title": "Connection looks healthy", "confidence": 82, "detail": "No major bottleneck was detected from this test."})
        actions.append({"title": "Keep monitoring during slow hours", "gain_mbps": 0, "type": "monitor"})

    return {
        "summary": diagnosis_summary(speed, device_count, browser),
        "findings": findings[:8],
        "actions": actions[:8],
        "estimated_gain_mbps": min(estimated_gain, 45),
    }


def diagnosis_summary(speed: dict[str, object], device_count: int, browser: dict[str, object]) -> str:
    download = speed.get("download_mbps")
    ping = speed.get("ping_ms")
    jitter = speed.get("jitter_ms")
    tabs = int(browser.get("tab_count") or 0)
    streaming = int(browser.get("streaming_tabs") or 0)

    if download is None:
        return "SmartNet could not complete the speed test. Check internet access and run the test again."
    if float(download) >= 25 and ping is not None and float(ping) <= 60 and jitter is not None and float(jitter) <= 20:
        return "Your internet is suitable for HD/4K streaming and most video meetings. Gaming should also be stable."
    if float(download) >= 25 and ping is not None and float(ping) > 100:
        return "Download speed is good, but latency is high. The issue is likely Wi-Fi stability, router congestion, or ISP routing."
    if float(download) < 10 and device_count > 8:
        return "Speed is low and many devices are connected. Router load or background usage is a likely bottleneck."
    if streaming or tabs > 25:
        return "Browser activity may be slowing the connection. Try the optimizer, then rerun the speed test."
    return "SmartNet found a usable connection, but the recommendations below can improve stability."


def health_score(speed: dict[str, object], scan: dict[str, object]) -> dict[str, object]:
    download = speed.get("download_mbps")
    ping = speed.get("ping_ms")
    jitter = speed.get("jitter_ms")
    loss = speed.get("packet_loss_percent")
    devices = int(scan.get("count") or 0)
    parts = {
        "speed": score_speed(float(download)) if download is not None else 0,
        "latency": score_latency(float(ping)) if ping is not None else 0,
        "jitter": score_jitter(float(jitter)) if jitter is not None else 0,
        "packet_loss": score_loss(float(loss)) if loss is not None else 0,
        "device_load": score_device_load(devices),
    }
    total = min(100, max(0, sum(parts.values())))
    return {"score": total, "quality": classify_quality(total), "parts": parts}


def read_history() -> list[dict[str, object]]:
    try:
        if HISTORY_FILE.exists():
            with HISTORY_FILE.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                return data[-100:]
    except (OSError, json.JSONDecodeError):
        pass
    return []


def write_history(history: list[dict[str, object]]) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with HISTORY_FILE.open("w", encoding="utf-8") as handle:
            json.dump(history[-100:], handle, indent=2)
    except OSError:
        pass


def append_history(entry: dict[str, object]) -> None:
    history = read_history()
    history.append(entry)
    write_history(history)


def export_history_csv() -> bytes:
    rows = read_history()
    fields = [
        "scanned_at",
        "health_score",
        "download_mbps",
        "upload_mbps",
        "ping_ms",
        "jitter_ms",
        "packet_loss_percent",
        "device_count",
    ]
    output: list[str] = []
    output.append(",".join(fields))
    for row in rows:
        output.append(",".join(str(row.get(field, "")) for field in fields))
    return ("\n".join(output) + "\n").encode("utf-8")


def run_speed_test(download_mb: int = 6, upload_mb: int = 1, include_upload: bool = True) -> dict[str, object]:
    started = time.perf_counter()
    scanned_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    latency = measure_latency(samples=4)
    download = measure_download(max_mb=download_mb)
    upload = measure_upload(size_mb=upload_mb) if include_upload else {
        "ok": False,
        "url": None,
        "bytes": 0,
        "seconds": 0,
        "mbps": None,
        "errors": ["Upload test skipped."],
    }

    return {
        "ok": bool(latency.get("ok") or download.get("ok") or upload.get("ok")),
        "scanned_at": scanned_at,
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "download_mbps": download.get("mbps"),
        "upload_mbps": upload.get("mbps"),
        "ping_ms": latency.get("ping_ms"),
        "jitter_ms": latency.get("jitter_ms"),
        "packet_loss_percent": latency.get("packet_loss_percent"),
        "download": download,
        "upload": upload,
        "latency": latency,
        "notes": [
            "Download and upload tests use public endpoints, so results can vary by server and route.",
            "Latency is measured using TCP connection time, not raw ICMP ping.",
        ],
    }


def cached_speed_test(refresh: bool, download_mb: int, upload_mb: int, include_upload: bool) -> dict[str, object]:
    now = time.time()
    cached = SPEED_CACHE.get("data")
    if not refresh and cached and now - float(SPEED_CACHE["time"]) < 60:
        data = dict(cached)
        data["cached"] = True
        return data

    data = run_speed_test(download_mb=download_mb, upload_mb=upload_mb, include_upload=include_upload)
    data["cached"] = False
    SPEED_CACHE["time"] = now
    SPEED_CACHE["data"] = data
    return data


def build_health_report(refresh: bool = True, browser: dict[str, object] | None = None) -> dict[str, object]:
    now = time.time()
    cached = REPORT_CACHE.get("data")
    if not refresh and cached and now - float(REPORT_CACHE["time"]) < 60:
        data = dict(cached)
        data["cached"] = True
        return data

    scan = cached_scan(refresh=refresh, max_hosts=254, timeout_ms=350, workers=64)
    speed = cached_speed_test(refresh=refresh, download_mb=6, upload_mb=1, include_upload=True)
    score = health_score(speed, scan)
    activities = activity_recommendations(
        speed.get("download_mbps") if isinstance(speed.get("download_mbps"), (int, float)) else None,
        speed.get("upload_mbps") if isinstance(speed.get("upload_mbps"), (int, float)) else None,
        speed.get("ping_ms") if isinstance(speed.get("ping_ms"), (int, float)) else None,
        speed.get("jitter_ms") if isinstance(speed.get("jitter_ms"), (int, float)) else None,
        speed.get("packet_loss_percent") if isinstance(speed.get("packet_loss_percent"), (int, float)) else None,
    )
    diagnosis = build_diagnosis(speed, scan, browser)
    entry = {
        "scanned_at": speed.get("scanned_at"),
        "health_score": score["score"],
        "download_mbps": speed.get("download_mbps"),
        "upload_mbps": speed.get("upload_mbps"),
        "ping_ms": speed.get("ping_ms"),
        "jitter_ms": speed.get("jitter_ms"),
        "packet_loss_percent": speed.get("packet_loss_percent"),
        "device_count": scan.get("count"),
    }
    if refresh:
        append_history(entry)

    data = {
        "ok": bool(scan.get("ok") or speed.get("ok")),
        "cached": False,
        "scanned_at": speed.get("scanned_at"),
        "health": score,
        "speed": speed,
        "scan": scan,
        "activities": activities,
        "diagnosis": diagnosis,
        "history": read_history(),
    }
    REPORT_CACHE["time"] = now
    REPORT_CACHE["data"] = data
    return data


class DeviceScannerHandler(SimpleHTTPRequestHandler):
    server_version = "SmartNetAI/1.0"

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def write_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def write_bytes(self, status: int, body: bytes, content_type: str, filename: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/diagnosis":
            body = self.read_json_body()
            browser = body.get("browser") if isinstance(body.get("browser"), dict) else {}
            scan = cached_scan(refresh=False, max_hosts=254, timeout_ms=350, workers=64)
            speed = cached_speed_test(refresh=False, download_mb=6, upload_mb=1, include_upload=True)
            self.write_json(
                200,
                {
                    "ok": True,
                    "diagnosis": build_diagnosis(speed, scan, browser),
                    "health": health_score(speed, scan),
                    "speed": speed,
                    "scan": scan,
                },
            )
            return
        self.write_json(404, {"ok": False, "error": "Unknown endpoint"})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path in {"/api/scan", "/api/devices"}:
            refresh = query.get("refresh", ["0"])[0] in {"1", "true", "yes"}
            max_hosts = int(query.get("max_hosts", ["254"])[0])
            timeout_ms = int(query.get("timeout_ms", ["350"])[0])
            workers = int(query.get("workers", ["64"])[0])
            max_hosts = min(max(max_hosts, 1), 1024)
            timeout_ms = min(max(timeout_ms, 100), 2000)
            workers = min(max(workers, 1), 128)
            self.write_json(200, cached_scan(refresh, max_hosts, timeout_ms, workers))
            return

        if parsed.path == "/api/speed-test":
            refresh = query.get("refresh", ["1"])[0] in {"1", "true", "yes"}
            download_mb = min(max(int(query.get("download_mb", ["6"])[0]), 1), 100)
            upload_mb = min(max(int(query.get("upload_mb", ["1"])[0]), 1), 20)
            include_upload = query.get("upload", ["1"])[0] not in {"0", "false", "no"}
            self.write_json(200, cached_speed_test(refresh, download_mb, upload_mb, include_upload))
            return

        if parsed.path == "/api/health-report":
            refresh = query.get("refresh", ["1"])[0] in {"1", "true", "yes"}
            self.write_json(200, build_health_report(refresh=refresh))
            return

        if parsed.path == "/api/history":
            self.write_json(200, {"ok": True, "history": read_history()})
            return

        if parsed.path == "/api/history.csv":
            self.write_bytes(200, export_history_csv(), "text/csv; charset=utf-8", "smartnet-history.csv")
            return

        if parsed.path == "/health":
            self.write_json(200, {"ok": True, "service": "smartnet-ai"})
            return

        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()


def serve(host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), DeviceScannerHandler)
    url_host = "localhost" if host in {"127.0.0.1", "0.0.0.0"} else host
    print(f"Connected Device Scanner running at http://{url_host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping scanner.")
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="SmartNet AI WiFi health analyzer.")
    parser.add_argument("command", nargs="?", choices=["serve", "scan", "speed", "report"], default="serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--max-hosts", type=int, default=254)
    parser.add_argument("--timeout-ms", type=int, default=350)
    parser.add_argument("--workers", type=int, default=64)
    parser.add_argument("--json", action="store_true", help="Print scan result as JSON.")
    args = parser.parse_args()

    if args.command == "scan":
        data = scan_devices(max_hosts=args.max_hosts, timeout_ms=args.timeout_ms, workers=args.workers)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(f"Network: {data.get('scan_range')}")
            print(f"Connected devices detected: {data.get('count')}")
            for device in data.get("devices", []):
                label = device.get("hostname") or device.get("vendor") or device.get("type") or "Unknown"
                print(f"- {device.get('ip')}  {device.get('mac') or 'no-mac'}  {label}  {device.get('role')}")
        return 0 if data.get("ok") else 1

    if args.command == "speed":
        data = run_speed_test()
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(f"Download: {data.get('download_mbps') or 'not available'} Mbps")
            print(f"Upload: {data.get('upload_mbps') or 'not available'} Mbps")
            print(f"Ping: {data.get('ping_ms') or 'not available'} ms")
            print(f"Jitter: {data.get('jitter_ms') or 'not available'} ms")
            print(f"Packet loss: {data.get('packet_loss_percent') or 'not available'}%")
        return 0 if data.get("ok") else 1

    if args.command == "report":
        data = build_health_report(refresh=True)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            health = data.get("health", {})
            speed = data.get("speed", {})
            scan = data.get("scan", {})
            diagnosis = data.get("diagnosis", {})
            print(f"WiFi Health Score: {health.get('score')}/100 ({health.get('quality')})")
            print(f"Download: {speed.get('download_mbps') or 'not available'} Mbps")
            print(f"Upload: {speed.get('upload_mbps') or 'not available'} Mbps")
            print(f"Ping: {speed.get('ping_ms') or 'not available'} ms")
            print(f"Connected devices: {scan.get('count')}")
            print(f"Diagnosis: {diagnosis.get('summary')}")
        return 0 if data.get("ok") else 1

    serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
