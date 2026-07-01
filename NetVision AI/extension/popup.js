const DEFAULT_API_URL = "http://localhost:5000";

const refreshButton = document.querySelector("#refreshButton");
const optimizeButton = document.querySelector("#optimizeButton");
const saveButton = document.querySelector("#saveButton");
const apiUrlInput = document.querySelector("#apiUrl");
const healthScore = document.querySelector("#healthScore");
const downloadSpeed = document.querySelector("#downloadSpeed");
const deviceCount = document.querySelector("#deviceCount");
const tabCount = document.querySelector("#tabCount");
const streamingCount = document.querySelector("#streamingCount");
const gainValue = document.querySelector("#gainValue");
const loadState = document.querySelector("#loadState");
const findingList = document.querySelector("#findingList");
const tabList = document.querySelector("#tabList");
const statusText = document.querySelector("#statusText");

const STREAMING_HOSTS = [
  "youtube.com",
  "youtu.be",
  "netflix.com",
  "primevideo.com",
  "hotstar.com",
  "disneyplus.com",
  "twitch.tv",
  "spotify.com",
];

const MEETING_HOSTS = ["meet.google.com", "zoom.us", "teams.microsoft.com", "webex.com"];
const DOWNLOAD_HOSTS = ["drive.google.com", "dropbox.com", "mega.nz", "mediafire.com", "github.com", "onedrive.live.com"];

let latestBrowserStats = null;

function storageGet(key, fallback) {
  return new Promise((resolve) => {
    chrome.storage.sync.get({ [key]: fallback }, (items) => resolve(items[key]));
  });
}

function storageSet(values) {
  return new Promise((resolve) => {
    chrome.storage.sync.set(values, resolve);
  });
}

function cleanApiUrl(value) {
  return String(value || DEFAULT_API_URL).replace(/\/+$/, "");
}

function number(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toFixed(digits).replace(/\.0$/, "");
}

function setStatus(message, isError = false) {
  statusText.textContent = message || "";
  statusText.classList.toggle("error", isError);
}

function hostname(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

function includesHost(host, list) {
  return list.some((item) => host === item || host.endsWith(`.${item}`));
}

function classifyTab(tab) {
  const host = hostname(tab.url || "");
  if (includesHost(host, STREAMING_HOSTS)) return "Streaming";
  if (includesHost(host, MEETING_HOSTS)) return "Meeting";
  if (includesHost(host, DOWNLOAD_HOSTS)) return "Cloud";
  if (tab.audible) return "Audio";
  return "Normal";
}

function queryTabs() {
  return new Promise((resolve) => {
    chrome.tabs.query({}, resolve);
  });
}

function discardTab(tabId) {
  return new Promise((resolve) => {
    chrome.tabs.discard(tabId, () => resolve(!chrome.runtime.lastError));
  });
}

async function getBrowserStats() {
  const tabs = await queryTabs();
  const activeIds = new Set(tabs.filter((tab) => tab.active).map((tab) => tab.id));
  const analyzed = tabs
    .filter((tab) => tab.url && tab.url.startsWith("http"))
    .map((tab) => ({ ...tab, category: classifyTab(tab), host: hostname(tab.url) }));

  const streamingTabs = analyzed.filter((tab) => tab.category === "Streaming");
  const meetingTabs = analyzed.filter((tab) => tab.category === "Meeting");
  const downloadTabs = analyzed.filter((tab) => tab.category === "Cloud");
  const inactiveTabs = analyzed.filter((tab) => !activeIds.has(tab.id) && !tab.pinned && !tab.audible);
  const candidates = inactiveTabs.filter((tab) => tab.category !== "Meeting");

  latestBrowserStats = {
    tab_count: analyzed.length,
    streaming_tabs: streamingTabs.length,
    meeting_tabs: meetingTabs.length,
    download_tabs: downloadTabs.length,
    inactive_tabs: inactiveTabs.length,
    optimizer_candidates: candidates.length,
    tabs: analyzed
      .filter((tab) => tab.category !== "Normal" || !tab.active)
      .slice(0, 12)
      .map((tab) => ({
        id: tab.id,
        title: tab.title || tab.host || "Tab",
        host: tab.host,
        category: tab.category,
        active: tab.active,
        pinned: tab.pinned,
        audible: tab.audible,
      })),
  };

  return latestBrowserStats;
}

function renderTabs(stats) {
  tabCount.textContent = stats.tab_count;
  streamingCount.textContent = stats.streaming_tabs;
  tabList.innerHTML = "";
  const tabs = stats.tabs || [];
  if (tabs.length === 0) {
    tabList.innerHTML = '<li class="empty">No heavy tabs detected.</li>';
    return;
  }

  for (const tab of tabs) {
    const item = document.createElement("li");
    item.innerHTML = `
      <div class="tab-top">
        <span title="${tab.title}">${tab.title}</span>
        <span class="tag">${tab.category}</span>
      </div>
      <span class="tab-meta">${tab.host || "unknown"}${tab.active ? " · active" : ""}${tab.audible ? " · audio" : ""}</span>
    `;
    tabList.appendChild(item);
  }
}

function renderFindings(items) {
  findingList.innerHTML = "";
  if (!items || items.length === 0) {
    findingList.innerHTML = '<li class="empty">No diagnosis yet.</li>';
    return;
  }

  for (const finding of items.slice(0, 5)) {
    const item = document.createElement("li");
    item.innerHTML = `
      <div class="finding-top">
        <span>${finding.title}</span>
        <span class="tag">${finding.confidence}%</span>
      </div>
      <span class="finding-detail">${finding.detail}</span>
    `;
    findingList.appendChild(item);
  }
}

function renderReport(report, diagnosis, stats) {
  const health = report.health || {};
  const speed = report.speed || {};
  const scan = report.scan || {};
  const load = scan.load || {};
  healthScore.textContent = health.score ?? "--";
  downloadSpeed.textContent = number(speed.download_mbps, 0);
  deviceCount.textContent = scan.count ?? "--";
  loadState.textContent = load.level ? `${load.level} load` : "--";
  gainValue.textContent = `+${diagnosis.estimated_gain_mbps || 0}`;
  renderFindings(diagnosis.findings || []);
  renderTabs(stats);
}

function renderOffline(error) {
  healthScore.textContent = "--";
  downloadSpeed.textContent = "--";
  deviceCount.textContent = "--";
  loadState.textContent = "Offline";
  renderFindings([]);
  setStatus(error.message || "Could not connect to the local companion service.", true);
}

async function runSmartScan(refresh = true) {
  refreshButton.disabled = true;
  optimizeButton.disabled = true;
  try {
    const apiUrl = cleanApiUrl(apiUrlInput.value);
    const stats = await getBrowserStats();
    const reportResponse = await fetch(`${apiUrl}/api/health-report?refresh=${refresh ? "1" : "0"}`);
    if (!reportResponse.ok) throw new Error(`Scanner returned ${reportResponse.status}`);
    const report = await reportResponse.json();
    const diagnosisResponse = await fetch(`${apiUrl}/api/diagnosis`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ browser: stats }),
    });
    const diagnosisData = diagnosisResponse.ok ? await diagnosisResponse.json() : {};
    renderReport(report, diagnosisData.diagnosis || report.diagnosis || {}, stats);
    setStatus(report.cached ? "Cached result loaded." : "Smart scan complete.");
  } catch (error) {
    renderOffline(error);
  } finally {
    refreshButton.disabled = false;
    optimizeButton.disabled = false;
  }
}

async function optimizeBrowser() {
  optimizeButton.disabled = true;
  try {
    const stats = latestBrowserStats || (await getBrowserStats());
    const candidates = (stats.tabs || []).filter((tab) => !tab.active && !tab.pinned && tab.category !== "Meeting");
    let suspended = 0;
    for (const tab of candidates) {
      if (await discardTab(tab.id)) suspended += 1;
    }
    setStatus(`Suspended ${suspended} background tab(s).`);
    await runSmartScan(false);
  } catch (error) {
    setStatus(error.message || "Optimizer failed.", true);
  } finally {
    optimizeButton.disabled = false;
  }
}

async function init() {
  apiUrlInput.value = cleanApiUrl(await storageGet("apiUrl", DEFAULT_API_URL));
  refreshButton.addEventListener("click", () => runSmartScan(true));
  optimizeButton.addEventListener("click", optimizeBrowser);
  saveButton.addEventListener("click", async () => {
    apiUrlInput.value = cleanApiUrl(apiUrlInput.value);
    await storageSet({ apiUrl: apiUrlInput.value });
    setStatus("API URL saved.");
    runSmartScan(false);
  });
  const stats = await getBrowserStats();
  renderTabs(stats);
  runSmartScan(false);
}

init();
