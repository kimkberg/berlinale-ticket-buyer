// === State ===
let ws = null;
let currentTab = "today-on-sale";
let programmeCache = {};  // day -> {data, timestamp}
const CACHE_TTL = 60000;  // 60 seconds
let tasks = [];
let ticketStatus = {};  // ext_id_screening -> {state, url, text}
let searchQuery = "";
let debounceTimer = null;
let config = { ticket_count: 2 };  // Default fallback, loaded from backend

// === Init ===
document.addEventListener("DOMContentLoaded", async () => {
    await loadConfig();
    connectWebSocket();
    loadTasks();
    loadTodayOnSale();
    buildDateTabs();
    // Check browser status on page load (read-only, does not trigger login)
    // Login is only triggered by explicit user action (clicking "Login Eventim" button)
    checkBrowserStatus();
    setupSearch();
    // Auto-refresh ticket status every 10 seconds
    setInterval(refreshTicketStatus, 10000);
});

// === WebSocket ===
function connectWebSocket() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/ws/status`);

    ws.onopen = () => {
        console.log("WebSocket connected");
        // Ping to keep alive
        setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: "ping" }));
            }
        }, 30000);
    };

    ws.onmessage = (evt) => {
        try {
            const msg = JSON.parse(evt.data);
            handleWSMessage(msg);
        } catch (e) {
            console.error("WS parse error:", e);
        }
    };

    ws.onclose = () => {
        console.log("WebSocket closed, reconnecting in 3s...");
        setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = (err) => {
        console.error("WebSocket error:", err);
    };
}

function handleWSMessage(msg) {
    if (msg.type === "task_update") {
        const data = msg.data;
        // Update local task list
        if (data.task) {
            const idx = tasks.findIndex(t => t.id === data.task_id);
            if (idx >= 0) {
                tasks[idx] = data.task;
            }
        } else {
            const idx = tasks.findIndex(t => t.id === data.task_id);
            if (idx >= 0) {
                tasks[idx].status = data.status;
                tasks[idx].result_message = data.message;
            }
        }
        renderTasks();

        // Show toast for important status changes
        if (data.status === "success") {
            showToast(`Ticket grabbed: ${data.message}`, "success");
        } else if (data.status === "failed") {
            showToast(`Grab failed: ${data.message}`, "error");
        }
    } else if (msg.type === "monitor_alert") {
        showToast(`Ticket available! ${msg.data.film_title} - auto-grabbing...`, "success");
    } else if (msg.type === "ticket_status") {
        ticketStatus = msg.data || {};
        updateTicketBadges();
    }
}

// === API Calls ===
async function loadConfig() {
    try {
        const resp = await fetch("/api/config");
        if (!resp.ok) {
            throw new Error(`Config fetch failed with status ${resp.status}`);
        }
        const data = await resp.json();
        config = data;
        console.log("Loaded config:", config);
    } catch (e) {
        console.error(`Failed to load config, using default ticket_count: ${config.ticket_count}`, e);
    }
}

async function loadTodayOnSale() {
    showLoading(true);
    try {
        const resp = await fetch("/api/today-on-sale");
        const data = await resp.json();
        renderFilms(data.films || [], "Today On Sale");
    } catch (e) {
        console.error("Failed to load today on sale:", e);
        document.getElementById("programme-list").innerHTML =
            '<div class="empty-state">Failed to load data. Is the Berlinale API available?</div>';
    }
    showLoading(false);
}

async function loadProgrammeDay(day) {
    const cached = programmeCache[day];
    if (cached && (Date.now() - cached.timestamp) < CACHE_TTL) {
        renderDayProgramme(cached.data);
        return;
    }
    showLoading(true);
    try {
        const resp = await fetch(`/api/programme/${day}`);
        const data = await resp.json();
        programmeCache[day] = { data, timestamp: Date.now() };
        renderDayProgramme(data);
    } catch (e) {
        console.error("Failed to load programme:", e);
        document.getElementById("programme-list").innerHTML =
            '<div class="empty-state">Failed to load programme for this day.</div>';
    }
    showLoading(false);
}

async function loadTasks() {
    try {
        const resp = await fetch("/api/tasks");
        const data = await resp.json();
        tasks = data.tasks || [];
        renderTasks();
    } catch (e) {
        console.error("Failed to load tasks:", e);
    }
}

async function createTask(filmData, eventData) {
    try {
        const body = {
            film_id: filmData.id || 0,
            film_title: filmData.title || "",
            ext_id_screening: eventData.ext_id_screening || "",
            venue: eventData.venue_hall || "",
            screening_time: eventData.date_display || eventData.time_text || "",
            sale_time: eventData.sale_time_str || "",
            eventim_url: eventData.ticket_url || "",
            mode: "browser",
            ticket_count: config.ticket_count,
        };
        const resp = await fetch("/api/tasks", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (data.task) {
            tasks.push(data.task);
            renderTasks();
            showToast("Grab task created!", "info");
        }
    } catch (e) {
        console.error("Failed to create task:", e);
        showToast("Failed to create task", "error");
    }
}

async function deleteTask(taskId) {
    try {
        await fetch(`/api/tasks/${taskId}`, { method: "DELETE" });
        tasks = tasks.filter(t => t.id !== taskId);
        renderTasks();
        showToast("Task cancelled", "info");
    } catch (e) {
        console.error("Failed to delete task:", e);
    }
}

async function runTaskNow(taskId) {
    try {
        await fetch(`/api/tasks/${taskId}/run`, { method: "POST" });
        showToast("Task triggered!", "info");
    } catch (e) {
        console.error("Failed to run task:", e);
    }
}

// Login is triggered ONLY by explicit user action (button click).
// The backend will bring existing browser to front if already open,
// rather than reloading the page (preserves session state).
async function loginEventim() {
    try {
        const resp = await fetch("/api/browser/login", { method: "POST" });
        const data = await resp.json();
        if (data.success) {
            showToast("Browser opened - please log in to Eventim", "info");
        } else {
            showToast("Failed to open browser", "error");
        }
        setTimeout(checkBrowserStatus, 5000);
    } catch (e) {
        showToast("Failed to connect to server", "error");
    }
}

async function checkBrowserStatus() {
    try {
        const resp = await fetch("/api/browser/status");
        const data = await resp.json();
        const badge = document.getElementById("session-status");
        if (data.logged_in) {
            badge.textContent = "Logged in";
            badge.className = "session-badge online";
        } else if (data.initialized) {
            badge.textContent = "Browser ready";
            badge.className = "session-badge offline";
        } else {
            badge.textContent = "Not connected";
            badge.className = "session-badge offline";
        }
    } catch (e) {
        // Server not reachable
    }
}

async function refreshTicketStatus() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "refresh_tickets" }));
    }
}

// === Date Tabs ===
function buildDateTabs() {
    const tabs = document.getElementById("date-tabs");
    // Festival: Feb 12-22
    const start = new Date(2026, 1, 12);
    const end = new Date(2026, 1, 22);

    let html = '<button class="date-tab active" data-tab="today-on-sale" onclick="switchTab(this, \'today-on-sale\')">Today On Sale</button>';
    html += '<button class="date-tab" data-tab="all-films" onclick="switchTab(this, \'all-films\')">All Films</button>';

    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
        const iso = d.toISOString().slice(0, 10);
        const label = d.toLocaleDateString("en-US", { month: "short", day: "numeric", weekday: "short" });
        html += `<button class="date-tab" data-tab="${iso}" onclick="switchTab(this, '${iso}')">${label}</button>`;
    }

    tabs.innerHTML = html;
}

function switchTab(el, tab) {
    document.querySelectorAll(".date-tab").forEach(t => t.classList.remove("active"));
    el.classList.add("active");
    currentTab = tab;

    // Clear search when switching tabs
    const searchInput = document.getElementById("search-input");
    if (searchInput) {
        searchInput.value = "";
        searchQuery = "";
    }

    if (tab === "today-on-sale") {
        loadTodayOnSale();
    } else if (tab === "all-films") {
        loadAllFilms();
    } else {
        loadProgrammeDay(tab);
    }
}

// === All Films ===
async function loadAllFilms() {
    const cached = programmeCache["__all__"];
    if (cached && (Date.now() - cached.timestamp) < CACHE_TTL) {
        renderAllFilms(cached.data);
        return;
    }
    showLoading(true);
    try {
        const resp = await fetch("/api/programme");
        const data = await resp.json();
        programmeCache["__all__"] = { data, timestamp: Date.now() };
        renderAllFilms(data);
    } catch (e) {
        console.error("Failed to load all films:", e);
        document.getElementById("programme-list").innerHTML =
            '<div class="empty-state">Failed to load full programme.</div>';
    }
    showLoading(false);
}

function renderAllFilms(data) {
    const container = document.getElementById("programme-list");
    const days = data.days || [];

    if (!days.length) {
        container.innerHTML = '<div class="empty-state">No programme data available.</div>';
        return;
    }

    let html = "";
    for (const day of days) {
        const dateLabel = day.weekday
            ? `${day.weekday}, ${day.date}`
            : day.date;
        html += `<div class="day-header">${escHtml(dateLabel)}</div>`;

        const sections = day.sections || [];
        for (const section of sections) {
            const color = section.section_color || "#666";
            html += `<div class="section-group">
                <div class="section-header">
                    <span class="section-dot" style="background:${escHtml(color)}"></span>
                    <span class="section-name">${escHtml(section.section_name || "Other")}</span>
                </div>`;
            const films = section.films || [];
            for (const film of films) {
                html += renderFilmCard(film);
            }
            html += `</div>`;
        }
    }
    container.innerHTML = html || '<div class="empty-state">No films found.</div>';
    startCountdowns();
    applySearchFilter();
}

// === Search ===
function setupSearch() {
    const input = document.getElementById("search-input");
    if (!input) return;
    input.addEventListener("input", () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            searchQuery = input.value.trim().toLowerCase();
            applySearchFilter();
        }, 300);
    });
}

function applySearchFilter() {
    const cards = document.querySelectorAll("#programme-list .film-card");
    if (!searchQuery) {
        cards.forEach(c => c.style.display = "");
        // Show all section groups and day headers
        document.querySelectorAll("#programme-list .section-group").forEach(g => g.style.display = "");
        document.querySelectorAll("#programme-list .day-header").forEach(h => h.style.display = "");
        return;
    }
    cards.forEach(card => {
        const titleEl = card.querySelector(".film-title");
        const title = (titleEl ? titleEl.textContent : "").toLowerCase();
        card.style.display = title.includes(searchQuery) ? "" : "none";
    });
    // Hide section groups where all cards are hidden
    document.querySelectorAll("#programme-list .section-group").forEach(group => {
        const visibleCards = group.querySelectorAll(".film-card:not([style*='display: none'])");
        group.style.display = visibleCards.length ? "" : "none";
    });
    // Hide day headers where the next section groups are all hidden
    document.querySelectorAll("#programme-list .day-header").forEach(header => {
        let next = header.nextElementSibling;
        let anyVisible = false;
        while (next && !next.classList.contains("day-header")) {
            if (next.classList.contains("section-group") && next.style.display !== "none") {
                anyVisible = true;
                break;
            }
            next = next.nextElementSibling;
        }
        header.style.display = anyVisible ? "" : "none";
    });
}

// === Rendering ===
function showLoading(show) {
    document.getElementById("programme-loading").style.display = show ? "block" : "none";
}

function renderFilms(films, title) {
    const container = document.getElementById("programme-list");
    if (!films.length) {
        container.innerHTML = '<div class="empty-state">No films found for this selection.</div>';
        return;
    }

    // Group films by section
    const sections = {};
    for (const film of films) {
        const sec = film.section_name || "Other";
        if (!sections[sec]) sections[sec] = { color: film.section_color || "#666", films: [] };
        sections[sec].films.push(film);
    }

    let html = "";
    for (const [name, data] of Object.entries(sections)) {
        html += `<div class="section-group">
            <div class="section-header">
                <span class="section-dot" style="background:${escHtml(data.color)}"></span>
                <span class="section-name">${escHtml(name)}</span>
            </div>`;
        for (const film of data.films) {
            html += renderFilmCard(film);
        }
        html += `</div>`;
    }
    container.innerHTML = html || '<div class="empty-state">No films found.</div>';
    startCountdowns();
    applySearchFilter();
}

function renderDayProgramme(dayData) {
    const container = document.getElementById("programme-list");
    const sections = dayData.sections || [];

    if (!sections.length) {
        container.innerHTML = '<div class="empty-state">No screenings for this day.</div>';
        return;
    }

    let html = "";
    for (const section of sections) {
        const color = section.section_color || "#666";
        html += `<div class="section-group">
            <div class="section-header">
                <span class="section-dot" style="background:${escHtml(color)}"></span>
                <span class="section-name">${escHtml(section.section_name || "Other")}</span>
            </div>`;

        const films = section.films || [];
        for (const film of films) {
            html += renderFilmCard(film);
        }
        html += `</div>`;
    }
    container.innerHTML = html;
    startCountdowns();
    applySearchFilter();
}

function renderFilmCard(film) {
    const otherTitles = (film.other_titles || []).filter(t => t && t !== film.title);
    const meta = (film.meta || []).join(" &middot; ");
    const directors = (film.crew || []).filter(Boolean);
    const infoTags = (film.information || []).filter(Boolean);

    // Title: link to berlinale page if available
    let titleHtml;
    if (film.link_url) {
        titleHtml = `<a href="${escAttr(film.link_url)}" target="_blank" rel="noopener">${escHtml(film.title || "Untitled")}</a>`;
    } else {
        titleHtml = escHtml(film.title || "Untitled");
    }

    let html = `<div class="film-card">
        <div class="film-header">
            <div style="flex:1;min-width:0">
                <div class="film-title">${titleHtml}</div>
                ${otherTitles.length ? `<div class="film-other-title">${escHtml(otherTitles.join(" / "))}</div>` : ""}
                ${directors.length ? `<div class="film-director">Dir: ${escHtml(directors.join(", "))}</div>` : ""}
                ${meta ? `<div class="film-meta">${meta}</div>` : ""}
            </div>
            ${film.image_url ? `<img class="film-thumb" src="${escAttr(film.image_url)}" alt="" loading="lazy">` : ""}
        </div>
        ${film.short_synopsis ? `<div class="film-synopsis">${escHtml(film.short_synopsis)}</div>` : ""}
        ${infoTags.length ? `<div class="film-info-badges">${infoTags.map(t => `<span class="film-info-badge">${escHtml(t)}</span>`).join("")}</div>` : ""}`;

    const events = film.events || [];
    for (const ev of events) {
        const state = ev.ticket_state || "unknown";
        const stateClass = state.replace("_", "-");
        const stateLabel = { available: "Available", pending: "Pending", sold_out: "Sold Out" }[state] || state;

        // Sale time display
        let saleInfo = "";
        if (ev.sale_time_str) {
            try {
                const sd = new Date(ev.sale_time_str);
                saleInfo = `Sale: ${sd.toLocaleDateString("en-US", { month: "short", day: "numeric" })} ${sd.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false })}`;
            } catch (e) {
                saleInfo = `Sale: ${ev.sale_time_str}`;
            }
        }

        const filmDataStr = escAttr(JSON.stringify({ id: film.id, title: film.title }));
        const eventDataStr = escAttr(JSON.stringify(ev));

        let actionButtons = "";
        if (state === "sold_out") {
            actionButtons = `<button class="btn btn-watch btn-sm" onclick='watchScreening(${filmDataStr}, ${eventDataStr})'>Watch</button>`;
        } else if (state === "available" && ev.ticket_url) {
            actionButtons = `<a href="${escAttr(ev.ticket_url)}" target="_blank" class="btn btn-success btn-sm">Buy Now</a>` +
                `<button class="btn btn-primary btn-sm" onclick='scheduleGrab(${filmDataStr}, ${eventDataStr})'>Schedule Grab</button>`;
        } else {
            actionButtons = `<button class="btn btn-primary btn-sm" onclick='scheduleGrab(${filmDataStr}, ${eventDataStr})'>Schedule Grab</button>`;
        }

        // Sale countdown: attach data attribute for live updates
        let saleTimeAttr = "";
        if (ev.sale_time_str) {
            saleTimeAttr = ` data-sale-time="${escAttr(ev.sale_time_str)}"`;
        }

        html += `<div class="event-row" data-screening="${escAttr(ev.ext_id_screening)}">
            <div class="event-info">
                ${ev.date_display ? `<span class="event-date">${escHtml(ev.date_display)}</span>` : ""}
                <span class="event-time">${escHtml(ev.time_text || "")}</span>
                <span class="event-venue">${escHtml(ev.venue_hall || "")}</span>
                ${saleInfo ? `<span class="event-sale"${saleTimeAttr}>${escHtml(saleInfo)}</span>` : ""}
            </div>
            <div class="event-actions">
                <span class="ticket-badge ${stateClass}">${stateLabel}</span>
                ${actionButtons}
            </div>
        </div>`;
    }

    html += `</div>`;
    return html;
}

function renderTasks() {
    const container = document.getElementById("tasks-list");
    const countEl = document.getElementById("task-count");
    const emptyEl = document.getElementById("tasks-empty");

    countEl.textContent = tasks.length;

    if (!tasks.length) {
        container.innerHTML = '<div class="empty-state" id="tasks-empty">No tasks yet. Click "Schedule Grab" on a screening to add one.</div>';
        return;
    }

    let html = "";
    for (const task of tasks) {
        const statusLabels = {
            pending: "Waiting",
            grabbing: "Grabbing...",
            watching: "Watching...",
            success: "Success!",
            failed: "Failed",
            cancelled: "Cancelled",
        };
        const statusLabel = statusLabels[task.status] || task.status;

        html += `<div class="task-card">
            <div class="task-info">
                <div class="task-title">${escHtml(task.film_title || task.ext_id_screening)}</div>
                <div class="task-detail">
                    ${escHtml(task.venue || "")} &middot; ${escHtml(task.screening_time || "")}
                    ${task.sale_time ? ` &middot; Sale: ${escHtml(formatDateTime(task.sale_time))}` : ""}
                </div>
                ${task.result_message ? `<div class="task-detail" style="color:${task.status === 'success' ? 'var(--green)' : task.status === 'failed' ? 'var(--red)' : 'var(--text-secondary)'}">${escHtml(truncateError(task.result_message))}</div>` : ""}
            </div>
            <div class="task-status">
                <span class="status-dot ${task.status}"></span>
                ${statusLabel}
            </div>
            <div class="task-actions">
                ${task.status === "pending" ? `<button class="btn btn-outline btn-xs" onclick="runTaskNow('${task.id}')">Run Now</button>` : ""}
                ${["pending", "failed", "watching"].includes(task.status) ? `<button class="btn btn-danger btn-xs" onclick="deleteTask('${task.id}')">Cancel</button>` : ""}
                ${["success", "cancelled"].includes(task.status) ? `<button class="btn btn-outline btn-xs" onclick="deleteTask('${task.id}')">Dismiss</button>` : ""}
            </div>
        </div>`;
    }
    container.innerHTML = html;
}

// === Actions ===
function scheduleGrab(filmData, eventData) {
    if (typeof filmData === "string") filmData = JSON.parse(filmData);
    if (typeof eventData === "string") eventData = JSON.parse(eventData);

    // Auto-detect: if sold_out with no URL, watch instead
    if (!eventData.ticket_url && eventData.ticket_state === "sold_out") {
        watchScreening(filmData, eventData);
        return;
    }
    createTask(filmData, eventData);
}

function watchScreening(filmData, eventData) {
    if (typeof filmData === "string") filmData = JSON.parse(filmData);
    if (typeof eventData === "string") eventData = JSON.parse(eventData);
    createTask(filmData, eventData);  // backend will detect empty URL and set watching status
}

// === Ticket Badge Updates ===
function updateTicketBadges() {
    for (const [extId, info] of Object.entries(ticketStatus)) {
        const rows = document.querySelectorAll(`[data-screening="${CSS.escape(extId)}"]`);
        for (const row of rows) {
            const badge = row.querySelector(".ticket-badge");
            if (badge) {
                const state = info.state || "unknown";
                const stateClass = state.replace("_", "-");
                const label = { available: "Available", pending: "Pending", sold_out: "Sold Out" }[state] || state;
                badge.className = `ticket-badge ${stateClass}`;
                badge.textContent = label;
            }
            // Show buy button if available
            if (info.state === "available" && info.url) {
                const actions = row.querySelector(".event-actions");
                if (actions && !actions.querySelector(".btn-success")) {
                    const link = document.createElement("a");
                    link.href = info.url;
                    link.target = "_blank";
                    link.className = "btn btn-success btn-sm";
                    link.textContent = "Buy Now";
                    actions.insertBefore(link, actions.querySelector(".btn-primary"));
                }
            }
        }
    }
}

// === Countdown Timer ===
let countdownInterval = null;

function startCountdowns() {
    if (countdownInterval) clearInterval(countdownInterval);
    countdownInterval = setInterval(updateCountdowns, 1000);
    updateCountdowns(); // immediate first tick
}

function updateCountdowns() {
    const els = document.querySelectorAll("[data-sale-time]");
    if (!els.length) return;

    const now = new Date();
    els.forEach(el => {
        const saleTime = new Date(el.dataset.saleTime);
        const diff = saleTime - now;
        if (diff <= 0) {
            el.innerHTML = `<span class="on-sale-now">ON SALE NOW!</span>`;
        } else {
            const h = Math.floor(diff / 3600000);
            const m = Math.floor((diff % 3600000) / 60000);
            const s = Math.floor((diff % 60000) / 1000);
            let parts = [];
            if (h > 0) parts.push(`${h}h`);
            parts.push(`${m}m`);
            parts.push(`${s}s`);
            el.innerHTML = `Sale in <span class="countdown">${parts.join(" ")}</span>`;
        }
    });
}

// === Helpers ===
function escHtml(str) {
    if (!str) return "";
    const el = document.createElement("span");
    el.textContent = str;
    return el.innerHTML;
}

function escAttr(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/'/g, "&#39;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function truncateError(msg) {
    if (!msg) return "";
    // Cut at "Call log:" which starts the verbose Playwright trace
    const callLogIdx = msg.indexOf("Call log:");
    if (callLogIdx > 0) msg = msg.slice(0, callLogIdx).trim();
    // Cut at first newline
    const nlIdx = msg.indexOf("\n");
    if (nlIdx > 0) msg = msg.slice(0, nlIdx).trim();
    // Hard limit
    if (msg.length > 150) msg = msg.slice(0, 150) + "...";
    return msg;
}

function formatDateTime(isoStr) {
    if (!isoStr) return "";
    try {
        const d = new Date(isoStr);
        return d.toLocaleDateString("en-US", { month: "short", day: "numeric" }) + " " +
            d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
    } catch (e) {
        return isoStr;
    }
}

function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transition = "opacity .3s";
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}
