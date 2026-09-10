const PAGE_SIZE = 40;
const cache = new Map();

const filtersEl = document.getElementById("candidate-filters");
const feedEl = document.getElementById("feed");
const emptyEl = document.getElementById("empty");
const statusEl = document.getElementById("status");
const textFilterEl = document.getElementById("text-filter");
const sentinelEl = document.getElementById("sentinel");

const config = window.DASHBOARD_CONFIG;
let activeCandidateId = "el_sayed";
let query = "";
let visibleCount = 0;
let filteredRows = [];

function candidateMeta(candidateId) {
  return config.candidates.find((item) => item.candidateId === candidateId);
}

function formatWhen(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

async function loadGzipJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to load posts (${response.status})`);
  }
  const buffer = await response.arrayBuffer();
  const stream = new Response(buffer).body.pipeThrough(
    new DecompressionStream("gzip"),
  );
  const text = await new Response(stream).text();
  return JSON.parse(text);
}

async function rowsForCandidate(candidateId) {
  if (candidateId === "all") {
    const groups = await Promise.all(
      config.candidates.map((item) => rowsForCandidate(item.candidateId)),
    );
    return groups.flat();
  }
  if (cache.has(candidateId)) {
    return cache.get(candidateId);
  }
  const meta = candidateMeta(candidateId);
  const rows = await loadGzipJson(meta.url);
  cache.set(candidateId, rows);
  return rows;
}

function applyFilters(rows) {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return rows;
  }
  return rows.filter((row) => row.text.toLowerCase().includes(needle));
}

function renderFilters() {
  const total = config.candidates.reduce((sum, item) => sum + item.rowCount, 0);
  const options = [
    { candidateId: "all", displayName: "All", rowCount: total },
    ...config.candidates,
  ];
  filtersEl.replaceChildren();
  for (const option of options) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "filter";
    button.dataset.candidate = option.candidateId;
    button.setAttribute("aria-pressed", String(option.candidateId === activeCandidateId));
    button.innerHTML = `${option.displayName}<span class="count">${option.rowCount.toLocaleString()}</span>`;
    button.addEventListener("click", () => {
      activeCandidateId = option.candidateId;
      visibleCount = 0;
      renderFilters();
      void refresh();
    });
    filtersEl.append(button);
  }
}

function postCard(row) {
  const item = document.createElement("li");
  item.className = "post";
  item.dataset.candidate = row.matched_candidate;
  const uriLink = row.bsky_url
    ? `<a href="${row.bsky_url}" target="_blank" rel="noreferrer">${row.uri}</a>`
    : row.uri;
  item.innerHTML = `
    <div class="when">${formatWhen(row.created_at)}</div>
    <div><span class="badge">${row.matched_name_string}</span></div>
    <p class="text"></p>
    <div class="ids">
      <div>${uriLink}</div>
      <div>${row.did}</div>
      <div>${row.matched_candidate}</div>
    </div>
  `;
  item.querySelector(".text").textContent = row.text;
  return item;
}

function appendPage() {
  const next = filteredRows.slice(visibleCount, visibleCount + PAGE_SIZE);
  for (const row of next) {
    feedEl.append(postCard(row));
  }
  visibleCount += next.length;
  emptyEl.hidden = filteredRows.length !== 0;
  const loadedName =
    activeCandidateId === "all"
      ? "all candidates"
      : candidateMeta(activeCandidateId).displayName;
  statusEl.textContent = `Showing ${Math.min(visibleCount, filteredRows.length).toLocaleString()} of ${filteredRows.length.toLocaleString()} posts for ${loadedName}.`;
}

async function refresh() {
  statusEl.textContent = "Loading posts…";
  feedEl.replaceChildren();
  visibleCount = 0;
  try {
    const rows = await rowsForCandidate(activeCandidateId);
    filteredRows = applyFilters(rows);
    appendPage();
  } catch (error) {
    statusEl.textContent = error instanceof Error ? error.message : String(error);
  }
}

textFilterEl.addEventListener("input", () => {
  query = textFilterEl.value;
  visibleCount = 0;
  feedEl.replaceChildren();
  void refresh();
});

const observer = new IntersectionObserver((entries) => {
  if (!entries.some((entry) => entry.isIntersecting)) {
    return;
  }
  if (visibleCount < filteredRows.length) {
    appendPage();
  }
});
observer.observe(sentinelEl);

renderFilters();
void refresh();
