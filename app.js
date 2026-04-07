const cardList = document.getElementById("cardList");
const searchInput = document.getElementById("searchInput");
const filterButtons = document.querySelectorAll(".filter-btn");
const refreshBtn = document.getElementById("refreshBtn");
const saveApiKeyBtn = document.getElementById("saveApiKeyBtn");
const apiKeyInput = document.getElementById("apiKeyInput");
const statusBar = document.getElementById("statusBar");

const totalCount = document.getElementById("totalCount");
const ownedCount = document.getElementById("ownedCount");
const watchlistCount = document.getElementById("watchlistCount");
const upcomingCount = document.getElementById("upcomingCount");

let currentFilter = "all";
let liveData = {};

const FINNHUB_BASE = "https://finnhub.io/api/v1";
const STORAGE_KEY = "stock-watchlist-finnhub-key";

const marketSymbolMap = {
  "A2M": "NZX:A2M",
  "CCR": "ASX:CCR",
  "EUAD": "LSE:EUAD",
  "HGH": "NZX:HGH",
  "SIG": "ASX:SIG"
};

function getApiKey() {
  return localStorage.getItem(STORAGE_KEY) || "";
}

function setStatus(message) {
  statusBar.textContent = message;
}

function saveApiKey() {
  const key = apiKeyInput.value.trim();
  if (!key) {
    setStatus("Please paste your Finnhub API key first.");
    return;
  }
  localStorage.setItem(STORAGE_KEY, key);
  setStatus("API key saved on this device.");
}

function resolveSymbol(item) {
  return marketSymbolMap[item.ticker] || item.ticker;
}

function formatCurrency(value) {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: value < 10 ? 3 : 2
  }).format(value);
}

function formatPercent(value) {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function formatDate(dateStr) {
  if (!dateStr) return "—";
  const d = new Date(dateStr + "T00:00:00");
  if (Number.isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function daysUntil(dateStr) {
  if (!dateStr) return null;
  const today = new Date();
  const target = new Date(dateStr + "T00:00:00");
  const ms = target - new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round(ms / 86400000);
}

function updateSummary(filteredForDisplay) {
  totalCount.textContent = stocks.length;
  ownedCount.textContent = stocks.filter(x => x.status === "owned").length;
  watchlistCount.textContent = stocks.filter(x => x.status === "watchlist").length;

  const upcoming = stocks.filter(item => {
    const earningDate = liveData[item.ticker]?.earningsDate;
    const d = daysUntil(earningDate);
    return d != null && d >= 0 && d <= 30;
  }).length;
  upcomingCount.textContent = upcoming;
}

function getMetricClass(value) {
  if (value > 0) return "pos";
  if (value < 0) return "neg";
  return "";
}

function buildCard(item) {
  const data = liveData[item.ticker] || {};
  const earningsDate = data.earningsDate || null;
  const dte = daysUntil(earningsDate);

  let earningsText = "—";
  if (earningsDate) {
    earningsText = formatDate(earningsDate);
    if (dte != null && dte >= 0) earningsText += ` (${dte}d)`;
  }

  const quote = data.quote || {};
  const current = quote.c;
  const pct = quote.dp;

  return `
    <article class="stock-card ${item.status}">
      <div class="card-head">
        <div>
          <h2 class="company">${item.company}</h2>
          <div class="ticker-line">${item.ticker} · ${item.market}</div>
        </div>
        <span class="badge ${item.status}">${item.status === "owned" ? "Owned" : "Watchlist"}</span>
      </div>

      <div class="metrics-grid">
        <div class="metric">
          <div class="metric-label">Price</div>
          <div class="metric-value">${formatCurrency(current)}</div>
        </div>
        <div class="metric">
          <div class="metric-label">Day %</div>
          <div class="metric-value ${getMetricClass(pct)}">${formatPercent(pct)}</div>
        </div>
        <div class="metric">
          <div class="metric-label">Next earnings</div>
          <div class="metric-value">${earningsText}</div>
        </div>
        <div class="metric">
          <div class="metric-label">Source symbol</div>
          <div class="metric-value">${resolveSymbol(item)}</div>
        </div>
      </div>

      <div class="notes">${item.notes}</div>
      <div class="small-note">Some ETFs, OTC lines and non-US tickers may have patchy coverage depending on the data provider and exchange mapping.</div>
    </article>
  `;
}

function renderCards() {
  const searchText = searchInput.value.trim().toLowerCase();

  const filtered = stocks.filter(item => {
    const matchesFilter = currentFilter === "all" ? true : item.status === currentFilter;
    const searchable = `${item.company} ${item.ticker} ${item.market} ${item.notes}`.toLowerCase();
    return matchesFilter && searchable.includes(searchText);
  });

  updateSummary(filtered);

  if (!filtered.length) {
    cardList.innerHTML = `<div class="empty">No matching stocks found.</div>`;
    return;
  }

  cardList.innerHTML = filtered.map(buildCard).join("");
}

async function fetchQuote(symbol, apiKey) {
  const url = `${FINNHUB_BASE}/quote?symbol=${encodeURIComponent(symbol)}&token=${encodeURIComponent(apiKey)}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Quote failed for ${symbol}`);
  return await res.json();
}

async function fetchEarnings(symbol, apiKey) {
  const today = new Date();
  const from = today.toISOString().slice(0, 10);
  const toObj = new Date(today.getTime() + 180 * 86400000);
  const to = toObj.toISOString().slice(0, 10);
  const url = `${FINNHUB_BASE}/calendar/earnings?symbol=${encodeURIComponent(symbol)}&from=${from}&to=${to}&token=${encodeURIComponent(apiKey)}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Earnings failed for ${symbol}`);
  const json = await res.json();
  const earningsCalendar = json.earningsCalendar || [];
  const nextItem = earningsCalendar
    .filter(x => x.date)
    .sort((a, b) => a.date.localeCompare(b.date))[0];
  return nextItem ? nextItem.date : null;
}

async function refreshLiveData() {
  const apiKey = getApiKey();
  if (!apiKey) {
    setStatus("Add your Finnhub API key and tap Save key.");
    return;
  }

  setStatus("Refreshing live prices and earnings dates...");
  refreshBtn.disabled = true;

  const nextLiveData = {};

  for (let i = 0; i < stocks.length; i++) {
    const item = stocks[i];
    const symbol = resolveSymbol(item);

    try {
      const [quote, earningsDate] = await Promise.all([
        fetchQuote(symbol, apiKey),
        fetchEarnings(symbol, apiKey)
      ]);

      nextLiveData[item.ticker] = { quote, earningsDate, sourceSymbol: symbol };
      setStatus(`Loaded ${i + 1} of ${stocks.length}: ${item.ticker}`);
    } catch (err) {
      nextLiveData[item.ticker] = {
        quote: {},
        earningsDate: null,
        sourceSymbol: symbol,
        error: err.message
      };
      setStatus(`Loaded ${i + 1} of ${stocks.length}, with some gaps.`);
    }

    renderCards();
    await new Promise(r => setTimeout(r, 250));
  }

  liveData = nextLiveData;
  renderCards();
  refreshBtn.disabled = false;
  setStatus("Refresh finished.");
}

searchInput.addEventListener("input", renderCards);

filterButtons.forEach(button => {
  button.addEventListener("click", () => {
    filterButtons.forEach(btn => btn.classList.remove("active"));
    button.classList.add("active");
    currentFilter = button.dataset.filter;
    renderCards();
  });
});

saveApiKeyBtn.addEventListener("click", saveApiKey);
refreshBtn.addEventListener("click", refreshLiveData);

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("./service-worker.js").catch(() => {});
  });
}

apiKeyInput.value = getApiKey();
renderCards();
