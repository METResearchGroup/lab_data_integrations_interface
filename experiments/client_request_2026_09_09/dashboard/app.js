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
let loadGeneration = 0;

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

function dataUrls(candidateId) {
  const meta = candidateMeta(candidateId);
  const relative = meta.url;
  const proxy = `/api/posts?candidate=${encodeURIComponent(candidateId)}`;
  if (/\.vercel\.app$/.test(window.location.hostname)) {
    return [proxy, relative];
  }
  return [relative];
}

async function parsePostsPayload(buffer) {
  try {
    const stream = new Response(buffer).body.pipeThrough(
      new DecompressionStream("gzip"),
    );
    const text = await new Response(stream).text();
    return JSON.parse(text);
  } catch (_gzipError) {
    const text = new TextDecoder().decode(buffer);
    return JSON.parse(text);
  }
}

async function loadGzipJson(urls) {
  let lastError = new Error("Failed to load posts");
  for (const url of urls) {
    try {
      const response = await fetch(url);
      if (!response.ok) {
        lastError = new Error(`Failed to load posts (${response.status})`);
        continue;
      }
      const buffer = await response.arrayBuffer();
      return await parsePostsPayload(buffer);
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));
    }
  }
  throw lastError;
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
  const rows = await loadGzipJson(dataUrls(candidateId));
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

function idRow(label, value, href) {
  const wrap = document.createElement("div");
  const lab = document.createElement("span");
  lab.className = "field";
  lab.textContent = label;
  wrap.append(lab, " ");
  if (href) {
    const link = document.createElement("a");
    link.href = href;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = value;
    wrap.append(link);
  } else {
    wrap.append(value);
  }
  return wrap;
}

function postCard(row) {
  const item = document.createElement("li");
  item.className = "post";
  item.dataset.candidate = row.matched_candidate;

  const when = document.createElement("div");
  when.className = "when";
  when.textContent = formatWhen(row.created_at);

  const match = document.createElement("div");
  const badge = document.createElement("span");
  badge.className = "badge";
  badge.textContent = row.matched_name_string;
  match.append(badge);

  const text = document.createElement("p");
  text.className = "text";
  text.textContent = row.text;

  const ids = document.createElement("div");
  ids.className = "ids";
  ids.append(idRow("uri", row.uri, row.bsky_url));
  ids.append(idRow("did", row.did));
  ids.append(idRow("candidate", row.matched_candidate));

  item.append(when, match, text, ids);
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
  const generation = ++loadGeneration;
  statusEl.textContent = "Loading posts…";
  feedEl.replaceChildren();
  visibleCount = 0;
  try {
    const rows = await rowsForCandidate(activeCandidateId);
    if (generation !== loadGeneration) {
      return;
    }
    filteredRows = applyFilters(rows);
    appendPage();
  } catch (error) {
    if (generation !== loadGeneration) {
      return;
    }
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
