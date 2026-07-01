const testButton = document.querySelector("#testButton");
const scanButton = document.querySelector("#scanButton");
const healthScore = document.querySelector("#healthScore");
const healthQuality = document.querySelector("#healthQuality");
const diagnosisSummary = document.querySelector("#diagnosisSummary");
const downloadSpeed = document.querySelector("#downloadSpeed");
const uploadSpeed = document.querySelector("#uploadSpeed");
const pingValue = document.querySelector("#pingValue");
const jitterValue = document.querySelector("#jitterValue");
const lossValue = document.querySelector("#lossValue");
const deviceCount = document.querySelector("#deviceCount");
const networkRange = document.querySelector("#networkRange");
const adapterName = document.querySelector("#adapterName");
const gatewayIp = document.querySelector("#gatewayIp");
const loadLabel = document.querySelector("#loadLabel");
const lastRun = document.querySelector("#lastRun");
const activityGrid = document.querySelector("#activityGrid");
const deviceRows = document.querySelector("#deviceRows");
const historyBars = document.querySelector("#historyBars");
const findingList = document.querySelector("#findingList");
const actionList = document.querySelector("#actionList");
const gainValue = document.querySelector("#gainValue");

let latestReport = null;

function text(value, fallback = "--") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function number(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toFixed(digits).replace(/\.0$/, "");
}

function formatDate(value) {
  if (!value) return "No test";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    day: "2-digit",
    month: "short",
  });
}

function setBusy(button, busy, label) {
  button.disabled = busy;
  button.querySelector("span:last-child").textContent = busy ? "Running" : label;
}

function setQualityClass(score) {
  document.body.classList.remove("quality-excellent", "quality-good", "quality-fair", "quality-poor");
  if (score >= 85) document.body.classList.add("quality-excellent");
  else if (score >= 70) document.body.classList.add("quality-good");
  else if (score >= 50) document.body.classList.add("quality-fair");
  else document.body.classList.add("quality-poor");
}

function deviceLabel(device) {
  if (device.role === "This computer") return device.hostname || "This computer";
  if (device.role === "Router/Gateway") return device.hostname || "Router";
  return device.hostname || device.vendor || "Unknown device";
}

function renderActivities(items) {
  activityGrid.innerHTML = "";
  if (!items || items.length === 0) {
    activityGrid.innerHTML = '<div class="empty-card">No activity result yet.</div>';
    return;
  }

  for (const item of items) {
    const card = document.createElement("article");
    card.className = item.ok ? "activity-card ok" : "activity-card bad";
    card.innerHTML = `
      <div class="activity-status">${item.ok ? "OK" : "NO"}</div>
      <div>
        <strong>${item.name}</strong>
        <span>${item.reason}</span>
      </div>
    `;
    activityGrid.appendChild(card);
  }
}

function renderDevices(devices) {
  deviceRows.innerHTML = "";
  if (!devices || devices.length === 0) {
    const row = document.createElement("tr");
    row.innerHTML = '<td colspan="5" class="empty-state">No devices detected.</td>';
    deviceRows.appendChild(row);
    return;
  }

  for (const device of devices) {
    const row = document.createElement("tr");
    const statusClass = device.reachable ? "status" : "status sleeping";
    const statusText = device.reachable ? "Active" : "ARP only";
    row.innerHTML = `
      <td>${text(device.ip)}</td>
      <td>
        <span class="device-name">
          <strong title="${text(deviceLabel(device))}">${text(deviceLabel(device))}</strong>
          <span class="subtle">${text(device.role)}</span>
        </span>
      </td>
      <td>${text(device.type)}</td>
      <td>${text(device.mac, "Not available")}</td>
      <td><span class="${statusClass}">${statusText}</span></td>
    `;
    deviceRows.appendChild(row);
  }
}

function renderFindings(items) {
  findingList.innerHTML = "";
  if (!items || items.length === 0) {
    findingList.innerHTML = '<div class="empty-card">No diagnosis yet.</div>';
    return;
  }

  for (const finding of items) {
    const item = document.createElement("article");
    item.className = "finding";
    item.innerHTML = `
      <div>
        <strong>${finding.title}</strong>
        <span>${finding.detail}</span>
      </div>
      <span class="confidence">${finding.confidence}%</span>
    `;
    findingList.appendChild(item);
  }
}

function renderActions(items) {
  actionList.innerHTML = "";
  if (!items || items.length === 0) {
    actionList.innerHTML = '<div class="empty-card">No actions yet.</div>';
    return;
  }

  for (const action of items) {
    const item = document.createElement("article");
    item.className = "action-item";
    item.innerHTML = `
      <strong>${action.title}</strong>
      <span>${action.gain_mbps ? `Estimated gain +${action.gain_mbps} Mbps` : "Monitor"}</span>
    `;
    actionList.appendChild(item);
  }
}

function renderHistory(items) {
  historyBars.innerHTML = "";
  const history = (items || []).slice(-12);
  if (history.length === 0) {
    historyBars.innerHTML = '<div class="empty-card">No history yet.</div>';
    return;
  }

  const maxDownload = Math.max(...history.map((item) => Number(item.download_mbps || 0)), 1);
  for (const entry of history) {
    const bar = document.createElement("div");
    const download = Number(entry.download_mbps || 0);
    const height = Math.max(10, Math.round((download / maxDownload) * 100));
    bar.className = "history-bar";
    bar.innerHTML = `
      <span style="height:${height}%"></span>
      <strong>${number(download, 0)}</strong>
      <em>${new Date(entry.scanned_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</em>
    `;
    historyBars.appendChild(bar);
  }
}

function renderReport(report) {
  latestReport = report;
  const health = report.health || {};
  const speed = report.speed || {};
  const scan = report.scan || {};
  const network = scan.network || {};
  const diagnosis = report.diagnosis || {};

  setQualityClass(Number(health.score || 0));
  healthScore.textContent = text(health.score);
  healthQuality.textContent = text(health.quality, "Waiting");
  diagnosisSummary.textContent = text(diagnosis.summary, "No diagnosis yet.");
  downloadSpeed.textContent = number(speed.download_mbps, 1);
  uploadSpeed.textContent = number(speed.upload_mbps, 1);
  pingValue.textContent = number(speed.ping_ms, 0);
  jitterValue.textContent = `${number(speed.jitter_ms, 1)} ms`;
  lossValue.textContent = `${number(speed.packet_loss_percent, 1)}%`;
  deviceCount.textContent = text(scan.count, "0");
  networkRange.textContent = scan.scan_range ? `Network ${scan.scan_range}` : "Network --";
  adapterName.textContent = text(network.adapter, "Unknown");
  gatewayIp.textContent = text(network.gateway, "Not found");
  loadLabel.textContent = scan.load ? `${scan.load.level} load` : "--";
  lastRun.textContent = formatDate(report.scanned_at);
  gainValue.textContent = `+${diagnosis.estimated_gain_mbps || 0} Mbps`;

  renderActivities(report.activities || []);
  renderDevices(scan.devices || []);
  renderFindings(diagnosis.findings || []);
  renderActions(diagnosis.actions || []);
  renderHistory(report.history || []);
}

function renderScan(scan) {
  const previous = latestReport || {};
  renderReport({
    ...previous,
    scanned_at: scan.scanned_at,
    health: previous.health || { score: "--", quality: "Devices scanned" },
    speed: previous.speed || {},
    scan,
    activities: previous.activities || [],
    diagnosis: previous.diagnosis || {
      summary: "Device scan complete. Run a full test for speed diagnosis.",
      findings: [],
      actions: [],
      estimated_gain_mbps: 0,
    },
    history: previous.history || [],
  });
}

function renderError(error) {
  diagnosisSummary.textContent = error.message || "SmartNet could not connect to the companion service.";
  healthQuality.textContent = "Offline";
}

async function fullTest(refresh = true) {
  setBusy(testButton, true, "Run Full Test");
  scanButton.disabled = true;
  try {
    const response = await fetch(`/api/health-report?refresh=${refresh ? "1" : "0"}`);
    if (!response.ok) throw new Error(`Server returned ${response.status}`);
    renderReport(await response.json());
  } catch (error) {
    renderError(error);
  } finally {
    setBusy(testButton, false, "Run Full Test");
    scanButton.disabled = false;
  }
}

async function scanDevices() {
  setBusy(scanButton, true, "Scan Devices");
  testButton.disabled = true;
  try {
    const response = await fetch("/api/scan?refresh=1");
    if (!response.ok) throw new Error(`Server returned ${response.status}`);
    renderScan(await response.json());
  } catch (error) {
    renderError(error);
  } finally {
    setBusy(scanButton, false, "Scan Devices");
    testButton.disabled = false;
  }
}

testButton.addEventListener("click", () => fullTest(true));
scanButton.addEventListener("click", scanDevices);
fullTest(false);
