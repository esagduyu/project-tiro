/* Tiro — frontend */

let digestData = null; // cached digest response
let digestLoaded = false;
let currentSort = "newest"; // "newest" | "oldest" | "importance"
let cachedArticles = []; // store articles for re-sorting without re-fetching
let selectedIndex = -1; // keyboard-selected article index
let showArchived = false; // whether to include decayed articles
let showVIPOnly = false; // whether to filter to VIP articles only
let currentPage = 1;
let perPage = 50; // default page size
let activeFilters = {}; // e.g. { is_read: "false", ai_tier: "must-read", tag: "AI" }
let filterPanelOpen = false;
let filterData = null; // cached /api/filters response

/* ---- Theme management ---- */

function applyTheme(mode) {
    document.documentElement.setAttribute('data-theme', mode);
    const themeLink = document.getElementById('theme-css');
    const themeName = mode === 'dark' ? 'roman-night' : 'papyrus';
    if (themeLink) themeLink.href = `/static/themes/${themeName}.css?v=38`;
    document.querySelectorAll('#theme-toggle, #mobile-theme-toggle').forEach(btn => {
        const icon = btn.querySelector('.sidebar-icon');
        if (icon) {
            icon.textContent = mode === 'dark' ? '\u263D' : '\u2600';
        } else {
            btn.textContent = mode === 'dark' ? '\u263D' : '\u2600';
        }
    });
    const label = document.getElementById('theme-label');
    if (label) label.textContent = mode === 'dark' ? 'Dark' : 'Light';
    localStorage.setItem('tiro-mode', mode);
}

function toggleTheme() {
    const current = localStorage.getItem('tiro-mode') || 'light';
    applyTheme(current === 'dark' ? 'light' : 'dark');
}

/* ---- Mobile sidebar ---- */

function openSidebar() {
    document.getElementById('sidebar')?.classList.add('open');
    document.getElementById('sidebar-overlay')?.classList.add('open');
}

function closeSidebar() {
    document.getElementById('sidebar')?.classList.remove('open');
    document.getElementById('sidebar-overlay')?.classList.remove('open');
}

/* ---- Unread badge ---- */

async function updateUnreadBadge() {
    try {
        const res = await fetch('/api/articles?is_read=false&include_decayed=false&count_only=true');
        const json = await res.json();
        const badge = document.getElementById('unread-badge');
        if (!badge) return;
        const count = json.data?.count ?? 0;
        if (count > 0) {
            badge.textContent = count > 99 ? '99+' : count;
            badge.style.display = '';
        } else {
            badge.style.display = 'none';
        }
    } catch (e) {}
}

/* ---- Init ---- */

document.addEventListener("DOMContentLoaded", () => {
    // Theme toggles
    document.getElementById('theme-toggle')?.addEventListener('click', toggleTheme);
    document.getElementById('mobile-theme-toggle')?.addEventListener('click', toggleTheme);

    // Mobile sidebar
    document.getElementById('mobile-menu-btn')?.addEventListener('click', openSidebar);
    document.getElementById('sidebar-overlay')?.addEventListener('click', closeSidebar);

    // Apply stored theme (reinforces the inline script in base.html)
    const mode = localStorage.getItem('tiro-mode') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    applyTheme(mode);

    // Unread badge
    updateUnreadBadge();

    // Page-specific init
    if (document.getElementById("article-list")) {
        restoreFiltersFromURL();
        loadInbox();
        loadFilters();
        setupSearch();
        setupSort();
        setupFilterPanel();
    }
    if (document.querySelector(".view-tab")) {
        setupViewTabs();
    }
    if (document.querySelector(".digest-tab")) {
        setupDigestTabs();
        // Auto-load digest if on the dedicated digest page (no view tabs = standalone)
        if (!document.querySelector(".view-tab") && !digestLoaded) {
            loadDigest(false);
        }
    }
    setupKeyboard();
});

/* ---- View tabs (All Articles / Daily Digest) ---- */

function setupViewTabs() {
    document.querySelectorAll(".view-tab").forEach((tab) => {
        tab.addEventListener("click", () => {
            document.querySelectorAll(".view-tab").forEach((t) => t.classList.remove("active"));
            tab.classList.add("active");

            const view = tab.dataset.view;
            document.getElementById("view-articles").style.display =
                view === "articles" ? "block" : "none";
            document.getElementById("view-digest").style.display =
                view === "digest" ? "block" : "none";

            if (view === "digest" && !digestLoaded) {
                loadDigest(false);
            }
        });
    });
}

/* ---- Digest sub-tabs (Ranked / By Topic / By Entity) ---- */

function setupDigestTabs() {
    document.querySelectorAll(".digest-tab").forEach((tab) => {
        tab.addEventListener("click", () => {
            document.querySelectorAll(".digest-tab").forEach((t) => t.classList.remove("active"));
            tab.classList.add("active");

            const type = tab.dataset.type;
            document.querySelectorAll(".digest-section").forEach((s) => (s.style.display = "none"));
            const section = document.getElementById(`digest-${type.replace("_", "-")}`);
            if (section) section.style.display = "block";
        });
    });

    // Refresh button
    const refreshBtn = document.getElementById("digest-refresh");
    if (refreshBtn) {
        refreshBtn.addEventListener("click", () => loadDigest(true));
    }
}

/* ---- Load digest ---- */

async function loadDigest(refresh) {
    const loadingEl = document.getElementById("digest-loading");
    const errorEl = document.getElementById("digest-error");
    const contentEl = document.getElementById("digest-content");
    const emptyEl = document.getElementById("digest-empty");
    const refreshBtn = document.getElementById("digest-refresh");

    loadingEl.style.display = "block";
    errorEl.style.display = "none";
    contentEl.style.display = "none";
    emptyEl.style.display = "none";
    if (refreshBtn) refreshBtn.disabled = true;

    try {
        const url = refresh ? "/api/digest/today?refresh=true" : "/api/digest/today";
        const res = await fetch(url);

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${res.status}`);
        }

        const json = await res.json();

        if (!json.success || !json.data) {
            throw new Error("Invalid response");
        }

        digestData = json.data;
        digestLoaded = true;

        // Render each section
        renderDigestSection("ranked", digestData.ranked);
        renderDigestSection("by_topic", digestData.by_topic);
        renderDigestSection("by_entity", digestData.by_entity);

        // Show time-ago banner
        updateDigestBanner(digestData);

        loadingEl.style.display = "none";
        contentEl.style.display = "block";

        // Show the active tab's section
        const activeTab = document.querySelector(".digest-tab.active");
        if (activeTab) {
            const type = activeTab.dataset.type;
            document.querySelectorAll(".digest-section").forEach((s) => (s.style.display = "none"));
            const section = document.getElementById(`digest-${type.replace("_", "-")}`);
            if (section) section.style.display = "block";
        }
    } catch (err) {
        console.error("Digest load failed:", err);
        loadingEl.style.display = "none";
        document.getElementById("digest-error-msg").textContent =
            `Failed to generate digest: ${err.message}`;
        errorEl.style.display = "block";
    } finally {
        if (refreshBtn) refreshBtn.disabled = false;
    }
}

function renderDigestSection(type, data) {
    const elId = `digest-${type.replace("_", "-")}`;
    const el = document.getElementById(elId);
    if (!el || !data) return;

    const content = data.content || "";
    el.innerHTML = marked.parse(content);

    // Make article links work (they're /articles/ID)
    el.querySelectorAll("a").forEach((link) => {
        const href = link.getAttribute("href");
        // Internal article links — keep as-is, they already point to /articles/{id}
        if (href && href.startsWith("/articles/")) {
            link.addEventListener("click", (e) => {
                e.preventDefault();
                // Mark as read
                const id = href.split("/articles/")[1];
                fetch(`/api/articles/${id}/read`, { method: "PATCH" }).catch(() => {});
                window.location.href = href;
            });
        } else if (href && (href.startsWith("http://") || href.startsWith("https://"))) {
            link.target = "_blank";
            link.rel = "noopener noreferrer";
        }
    });
}

function updateDigestBanner(data) {
    const banner = document.getElementById("digest-banner");
    if (!banner) return;

    // Get created_at from any section (they're all generated together)
    const section = data.ranked || data.by_topic || data.by_entity;
    if (!section || !section.created_at) {
        banner.style.display = "none";
        return;
    }

    const then = new Date(section.created_at.replace(" ", "T"));
    const diffHr = (new Date() - then) / 3600000;
    const stale = diffHr >= 24;
    const ago = timeAgo(then);

    banner.className = stale ? "digest-banner digest-banner-stale" : "digest-banner";
    banner.innerHTML = stale
        ? `Digest is ${ago} old — new articles may not be included. <button class="digest-refresh-inline" onclick="loadDigest(true)">Regenerate now</button>`
        : `Generated ${ago} <button class="digest-refresh-inline" onclick="loadDigest(true)">Regenerate</button>`;
    banner.style.display = "flex";
}

function timeAgo(then) {
    const diffMs = new Date() - then;
    const diffMin = Math.floor(diffMs / 60000);
    const diffHr = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHr / 24);

    if (diffMin < 1) return "just now";
    if (diffMin < 60) return `${diffMin}m ago`;
    if (diffHr < 24) return `${diffHr}h ago`;
    if (diffDay === 1) return "yesterday";
    return `${diffDay} days ago`;
}

/* ---- Inbox (articles list) ---- */

function buildQueryString() {
    const params = new URLSearchParams();

    // Pagination
    if (perPage > 0) {
        params.set("per_page", perPage);
        params.set("page", currentPage);
    }

    // Sort
    params.set("sort", currentSort);

    // Archived / decayed
    if (!showArchived) {
        params.set("include_decayed", "false");
    }

    // Active filters
    for (const [key, val] of Object.entries(activeFilters)) {
        if (val !== null && val !== undefined && val !== "") {
            params.set(key, val);
        }
    }

    return params.toString();
}

function syncURLWithFilters() {
    const params = new URLSearchParams();
    for (const [key, val] of Object.entries(activeFilters)) {
        if (val !== null && val !== undefined && val !== "") {
            params.set(key, val);
        }
    }
    if (currentSort !== "newest") params.set("sort", currentSort);
    if (currentPage > 1) params.set("page", currentPage);
    const qs = params.toString();
    const url = "/inbox" + (qs ? "?" + qs : "");
    window.history.replaceState({}, "", url);
}

function restoreFiltersFromURL() {
    const params = new URLSearchParams(window.location.search);
    const filterKeys = [
        "is_read", "is_vip", "ai_tier", "author", "source_id", "tag",
        "rating", "ingestion_method", "min_reading_time", "max_reading_time",
        "has_audio", "date_from", "date_to",
    ];
    for (const key of filterKeys) {
        if (params.has(key)) {
            activeFilters[key] = params.get(key);
        }
    }
    if (params.has("sort")) currentSort = params.get("sort");
    if (params.has("page")) currentPage = parseInt(params.get("page"), 10) || 1;
    // Update tab indicator after restoring filters
    setTimeout(() => updateFilterTabIndicator(), 0);
}

async function loadInbox() {
    const listEl = document.getElementById("article-list");
    if (!listEl) return;
    const emptyEl = document.getElementById("empty-state");
    const toolbar = document.getElementById("inbox-toolbar");

    try {
        const qs = buildQueryString();
        const res = await fetch(`/api/articles?${qs}`);
        const json = await res.json();

        if (!json.success || !json.data.length) {
            emptyEl.style.display = Object.keys(activeFilters).length ? "none" : "block";
            if (toolbar) toolbar.style.display = Object.keys(activeFilters).length ? "flex" : "none";
            listEl.innerHTML = Object.keys(activeFilters).length
                ? '<div class="filter-loading">No articles match these filters.</div>'
                : "";
            renderPagination(null);
            return;
        }

        cachedArticles = json.data;
        emptyEl.style.display = "none";
        renderArticleList(cachedArticles);
        updateToolbar(cachedArticles);
        renderPagination(json.pagination || null);
        renderActiveFilters();
        syncURLWithFilters();
    } catch (err) {
        console.error("Failed to load articles:", err);
        emptyEl.style.display = "block";
    }
}

function renderArticleList(articles) {
    const listEl = document.getElementById("article-list");
    // When using server-side pagination + sort, render as-is (already sorted by server)
    // Only client-sort when per_page=0 (all articles loaded)
    const toRender = perPage > 0 ? articles : sortArticles(articles, currentSort);
    listEl.innerHTML = toRender.map(renderArticle).join("");
    attachListeners();
    selectedIndex = -1;

    const sortSelect = document.getElementById("sort-select");
    if (sortSelect) sortSelect.value = currentSort;
}

function renderSortedInbox() {
    // Re-render with client-side sort (used when per_page=0)
    renderArticleList(cachedArticles);
}

function sortArticles(articles, mode) {
    const copy = [...articles];
    if (mode === "newest") {
        copy.sort((a, b) => {
            // VIP pinned first, then newest
            if (a.is_vip !== b.is_vip) return b.is_vip ? 1 : -1;
            return new Date(b.published_at || b.ingested_at) - new Date(a.published_at || a.ingested_at);
        });
    } else if (mode === "oldest") {
        copy.sort((a, b) => {
            if (a.is_vip !== b.is_vip) return b.is_vip ? 1 : -1;
            return new Date(a.published_at || a.ingested_at) - new Date(b.published_at || b.ingested_at);
        });
    } else if (mode === "importance") {
        const tierOrder = { "must-read": 0, "summary-enough": 1, "discard": 2 };
        copy.sort((a, b) => {
            const ta = tierOrder[a.ai_tier] ?? 1.5;
            const tb = tierOrder[b.ai_tier] ?? 1.5;
            if (ta !== tb) return ta - tb;
            // Within same tier: VIP first, then newest
            if (a.is_vip !== b.is_vip) return b.is_vip ? 1 : -1;
            return new Date(b.published_at || b.ingested_at) - new Date(a.published_at || a.ingested_at);
        });
    }
    return copy;
}

function renderArticle(a, showScore) {
    const classes = ["article-card"];
    if (a.is_read) classes.push("is-read");
    if (a.is_vip) classes.push("is-vip");
    if (a.ai_tier) classes.push(`tier-${a.ai_tier}`);

    const date = formatDate(a.published_at || a.ingested_at);
    const summary = a.summary || "";
    const tags = (a.tags || [])
        .map((t) => `<span class="tag clickable-tag" data-tag="${esc(t)}">${esc(t)}</span>`)
        .join("");

    const ratingMap = { "-1": "dislike", 1: "like", 2: "love" };
    const activeRating = ratingMap[String(a.rating)] || "";

    const sourceType = a.source_type || "web";
    const sourceTypeLabel = sourceType === "email" ? "email" : sourceType === "rss" ? "rss" : "saved";
    const sourceTypePill = `<span class="source-type-pill source-type-${sourceType} clickable-tag" data-tag="${esc(sourceTypeLabel)}">${sourceTypeLabel}</span>`;

    const tierBadge = a.ai_tier === "must-read"
        ? '<span class="tier-badge tier-badge-must-read">Must Read</span>'
        : a.ai_tier === "summary-enough"
        ? '<span class="tier-badge tier-badge-summary-enough">Summary</span>'
        : "";

    return `
    <article class="${classes.join(" ")}" data-id="${a.id}">
        <div class="article-main">
            <div class="article-meta">
                ${tierBadge}
                ${sourceTypePill}
                <span class="source-name">${esc(a.source_name || a.domain || "unknown")}</span>
                <span class="vip-star ${a.is_vip ? "active" : ""}"
                      data-source-id="${a.source_id}"
                      title="Toggle VIP">&#9733;</span>
                <span class="meta-sep">&middot;</span>
                <span>${date}</span>
                <span class="meta-sep">&middot;</span>
                <span>${a.reading_time_min || "?"} min</span>
                ${showScore && a.similarity_score ? `<span class="meta-sep">&middot;</span><span class="similarity-badge">${Math.round(a.similarity_score * 100)}% match</span>` : ""}
            </div>
            <h2 class="article-title">
                <a href="/articles/${a.id}" data-id="${a.id}">${esc(a.title)}</a>
            </h2>
            ${summary ? `<p class="article-summary"><strong>TL;DR</strong> &ndash; <em>${esc(summary)}</em></p>` : ""}
            ${tags ? `<div class="article-tags">${tags}</div>` : ""}
        </div>
        <div class="article-actions">
            <button class="rate-btn love ${activeRating === "love" ? "active" : ""}"
                    data-article-id="${a.id}" data-rating="2"
                    title="Love">&hearts;</button>
            <button class="rate-btn like ${activeRating === "like" ? "active" : ""}"
                    data-article-id="${a.id}" data-rating="1"
                    title="Like">&plus;</button>
            <button class="rate-btn dislike ${activeRating === "dislike" ? "active" : ""}"
                    data-article-id="${a.id}" data-rating="-1"
                    title="Dislike">&minus;</button>
        </div>
    </article>`;
}

function attachListeners() {
    // Rating buttons
    document.querySelectorAll(".rate-btn").forEach((btn) => {
        btn.addEventListener("click", async (e) => {
            e.stopPropagation();
            const articleId = btn.dataset.articleId;
            const rating = parseInt(btn.dataset.rating, 10);

            try {
                const res = await fetch(`/api/articles/${articleId}/rate`, {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ rating }),
                });
                const json = await res.json();
                if (json.success) {
                    // Update active state within this card
                    const card = btn.closest(".article-card");
                    card.querySelectorAll(".rate-btn").forEach((b) =>
                        b.classList.remove("active")
                    );
                    btn.classList.add("active");
                }
            } catch (err) {
                console.error("Rating failed:", err);
            }
        });
    });

    // VIP star toggle
    document.querySelectorAll(".vip-star").forEach((star) => {
        star.addEventListener("click", async (e) => {
            e.stopPropagation();
            const sourceId = star.dataset.sourceId;

            try {
                const res = await fetch(`/api/sources/${sourceId}/vip`, {
                    method: "PATCH",
                });
                const json = await res.json();
                if (json.success) {
                    // Reload to reflect VIP reordering
                    loadInbox();
                }
            } catch (err) {
                console.error("VIP toggle failed:", err);
            }
        });
    });

    // Tag click — search by tag
    document.querySelectorAll(".clickable-tag").forEach((tag) => {
        tag.addEventListener("click", (e) => {
            e.stopPropagation();
            const q = tag.dataset.tag;
            const input = document.getElementById("search-input");
            if (input) {
                input.value = q;
                document.getElementById("search-clear").style.display = "block";
                runSearch(q);
            }
        });
    });

    // Article title click — mark as read
    document.querySelectorAll(".article-title a").forEach((link) => {
        link.addEventListener("click", async (e) => {
            e.preventDefault();
            const articleId = link.dataset.id;

            try {
                await fetch(`/api/articles/${articleId}/read`, {
                    method: "PATCH",
                });
            } catch (err) {
                console.error("Mark-read failed:", err);
            }

            window.location.href = link.href;
        });
    });
}

function formatDate(isoStr) {
    if (!isoStr) return "";
    const d = new Date(isoStr);
    const now = new Date();
    const months = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ];

    if (d.getFullYear() === now.getFullYear()) {
        return `${months[d.getMonth()]} ${d.getDate()}`;
    }
    return `${months[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}

function esc(str) {
    const el = document.createElement("span");
    el.textContent = str;
    return el.innerHTML;
}

/* ---- Sort ---- */

function setupSort() {
    const sortSelect = document.getElementById("sort-select");
    if (!sortSelect) return;

    sortSelect.addEventListener("change", () => {
        currentSort = sortSelect.value;
        currentPage = 1;
        if (perPage > 0) {
            // Server-side sort with pagination — must re-fetch
            loadInbox();
        } else if (cachedArticles.length) {
            renderSortedInbox();
        }
    });
}

/* ---- Search ---- */

function setupSearch() {
    const input = document.getElementById("search-input");
    const clearBtn = document.getElementById("search-clear");
    if (!input) return;

    // Check for ?q= URL param (e.g. from reader tag click)
    const urlParams = new URLSearchParams(window.location.search);
    const initialQuery = urlParams.get("q");
    if (initialQuery) {
        input.value = initialQuery;
        clearBtn.style.display = "block";
        runSearch(initialQuery);
    }

    let debounceTimer = null;

    input.addEventListener("input", () => {
        const q = input.value.trim();
        clearBtn.style.display = q ? "block" : "none";

        clearTimeout(debounceTimer);
        if (!q) {
            exitSearch();
            return;
        }
        debounceTimer = setTimeout(() => runSearch(q), 300);
    });

    clearBtn.addEventListener("click", () => {
        input.value = "";
        clearBtn.style.display = "none";
        exitSearch();
        input.focus();
    });
}

async function runSearch(query) {
    const listEl = document.getElementById("article-list");
    const emptyEl = document.getElementById("empty-state");

    try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
        const json = await res.json();

        if (!json.success || !json.data.length) {
            listEl.innerHTML = `<div class="search-results-header">
                <h3>No results for "${esc(query)}"</h3>
            </div>`;
            emptyEl.style.display = "none";
            return;
        }

        emptyEl.style.display = "none";
        const header = `<div class="search-results-header">
            <h3>Results for "${esc(query)}"</h3>
            <span class="search-results-count">${json.data.length} found</span>
        </div>`;
        listEl.innerHTML = header + json.data.map((a) => renderArticle(a, true)).join("");
        attachListeners();
    } catch (err) {
        console.error("Search failed:", err);
    }
}

function exitSearch() {
    currentPage = 1;
    window.history.replaceState({}, "", "/inbox");
    loadInbox();
}

/* ---- Tier toolbar (classify button + discard toggle) ---- */

function updateToolbar(articles) {
    const toolbar = document.getElementById("inbox-toolbar");
    const classifyBtn = document.getElementById("classify-btn");
    const discardToggle = document.getElementById("discard-toggle");
    const classifyInfo = document.getElementById("classify-info");
    if (!toolbar) return;

    const discardCount = articles.filter((a) => a.ai_tier === "discard").length;
    const unclassified = articles.filter((a) => !a.ai_tier).length;
    const ratedCount = articles.filter((a) => a.rating !== null).length;

    toolbar.style.display = "flex";

    // Classify button — always visible
    classifyBtn.style.display = "inline-flex";
    if (unclassified > 0) {
        classifyBtn.textContent = `Classify inbox (${unclassified})`;
        classifyBtn.classList.remove("classify-btn-secondary");
    } else {
        classifyBtn.textContent = "Reclassify";
        classifyBtn.classList.add("classify-btn-secondary");
    }

    // Info text — guide user if not enough ratings
    if (ratedCount < 5) {
        classifyInfo.textContent = `Rate ${5 - ratedCount} more article${5 - ratedCount === 1 ? "" : "s"} to enable classification`;
        classifyInfo.style.display = "inline";
        classifyBtn.disabled = true;
    } else {
        classifyInfo.style.display = "none";
        classifyBtn.disabled = false;
    }

    // Discard toggle
    if (discardCount > 0) {
        discardToggle.style.display = "inline-flex";
        discardToggle.textContent = `Show discarded (${discardCount})`;
    } else {
        discardToggle.style.display = "none";
    }

    // Archived toggle — only show when not already showing archived
    const archivedToggle = document.getElementById("archived-toggle");
    if (archivedToggle) {
        if (showArchived) {
            archivedToggle.style.display = "inline-flex";
            archivedToggle.textContent = "Hide archived";
            archivedToggle.classList.add("active");
        } else {
            // Always show the button so user can toggle
            archivedToggle.style.display = "inline-flex";
            archivedToggle.textContent = "Show archived";
            archivedToggle.classList.remove("active");
        }
    }

    // VIP toggle
    const vipToggle = document.getElementById("vip-toggle");
    if (vipToggle) {
        vipToggle.classList.toggle("active", showVIPOnly);
        vipToggle.onclick = toggleVIPOnly;
    }

    // Attach handlers (safe to call multiple times — we replace onclick)
    classifyBtn.onclick = classifyArticles;
    discardToggle.onclick = toggleDiscarded;
    if (archivedToggle) archivedToggle.onclick = toggleArchived;
}

async function classifyArticles() {
    const classifyBtn = document.getElementById("classify-btn");
    const classifyInfo = document.getElementById("classify-info");
    const isReclassify = classifyBtn.classList.contains("classify-btn-secondary");

    classifyBtn.disabled = true;
    classifyBtn.textContent = "Classifying...";
    classifyInfo.textContent = "Opus 4.6 is learning your preferences — this may take 30–60s";
    classifyInfo.style.display = "inline";

    try {
        const body = isReclassify ? JSON.stringify({ refresh: true }) : undefined;
        const headers = isReclassify ? { "Content-Type": "application/json" } : {};
        const res = await fetch("/api/classify", { method: "POST", headers, body });
        const json = await res.json();

        if (!json.success) {
            classifyInfo.textContent = json.error || "Classification failed";
            classifyBtn.disabled = false;
            classifyBtn.textContent = isReclassify ? "Reclassify" : "Classify inbox";
            return;
        }

        classifyInfo.textContent = `Classified ${json.data.classified_count} articles`;

        // Switch to importance sort and reload
        currentSort = "importance";
        currentPage = 1;
        await loadInbox();
        loadFilters(); // refresh filter counts
    } catch (err) {
        console.error("Classification failed:", err);
        classifyInfo.textContent = "Classification failed — check console";
        classifyBtn.disabled = false;
        classifyBtn.textContent = isReclassify ? "Reclassify" : "Classify inbox";
    }
}

function toggleArchived() {
    showArchived = !showArchived;
    loadInbox().then(() => {
        if (!showArchived) return;
        // When showing archived, also force-show discarded so archived+discarded articles appear
        const listEl = document.getElementById("article-list");
        if (listEl) listEl.classList.add("show-discarded");
        const discardToggle = document.getElementById("discard-toggle");
        if (discardToggle) {
            const count = listEl.querySelectorAll(".tier-discard").length;
            discardToggle.textContent = `Hide discarded (${count})`;
            discardToggle.classList.add("active");
        }
    });
}

function toggleDiscarded() {
    const listEl = document.getElementById("article-list");
    const toggle = document.getElementById("discard-toggle");
    if (!listEl || !toggle) return;

    const showing = listEl.classList.toggle("show-discarded");
    toggle.classList.toggle("active", showing);

    // Update label
    const count = listEl.querySelectorAll(".tier-discard").length;
    toggle.textContent = showing
        ? `Hide discarded (${count})`
        : `Show discarded (${count})`;
}

function toggleVIPOnly() {
    showVIPOnly = !showVIPOnly;
    const toggle = document.getElementById("vip-toggle");
    if (toggle) toggle.classList.toggle("active", showVIPOnly);

    if (showVIPOnly) {
        // Client-side filter: show only VIP articles from cached list
        const vipArticles = cachedArticles.filter(a => a.is_vip);
        renderArticleList(vipArticles);
    } else {
        renderArticleList(cachedArticles);
    }
}

/* ---- Filter panel ---- */

function setupFilterPanel() {
    const filterTab = document.getElementById("filter-tab");
    const closeBtn = document.getElementById("filter-panel-close");
    const clearAllBtn = document.getElementById("filter-clear-all");

    function togglePanel() {
        filterPanelOpen = !filterPanelOpen;
        const panel = document.getElementById("filter-panel");
        if (panel) panel.classList.toggle("open", filterPanelOpen);
    }

    if (filterTab) {
        filterTab.addEventListener("click", togglePanel);
    }

    if (closeBtn) {
        closeBtn.addEventListener("click", () => {
            filterPanelOpen = false;
            const panel = document.getElementById("filter-panel");
            if (panel) panel.classList.remove("open");
        });
    }

    if (clearAllBtn) {
        clearAllBtn.addEventListener("click", () => {
            activeFilters = {};
            currentPage = 1;
            loadInbox();
            if (filterData) renderFilterPanelContent(filterData);
            updateFilterTabIndicator();
        });
    }
}

function updateFilterTabIndicator() {
    const tab = document.getElementById("filter-tab");
    if (!tab) return;
    const hasFilters = Object.keys(activeFilters).length > 0;
    tab.classList.toggle("has-filters", hasFilters);
}

async function loadFilters() {
    try {
        const res = await fetch("/api/filters");
        const json = await res.json();
        if (json.success) {
            filterData = json.data;
            renderFilterPanelContent(json.data);
        }
    } catch (err) {
        console.error("Failed to load filters:", err);
    }
}

function renderFilterPanelContent(data) {
    const body = document.getElementById("filter-panel-body");
    if (!body) return;

    let html = "";

    // Read status
    html += renderFilterSection("Status", [
        { label: "Unread", value: "false", key: "is_read", count: data.read_status?.unread || 0 },
        { label: "Read", value: "true", key: "is_read", count: data.read_status?.read || 0 },
    ]);

    // AI Tiers
    if (data.tiers?.length) {
        const tierLabels = { "must-read": "Must Read", "summary-enough": "Summary", "discard": "Discard", "unclassified": "Unclassified" };
        const tierItems = data.tiers.map(t => ({
            label: tierLabels[t.name] || t.name,
            value: t.name,
            key: "ai_tier",
            count: t.count,
        }));
        html += renderFilterSection("Tier", tierItems);
    }

    // Ratings
    if (data.ratings?.length) {
        const ratingLabels = { loved: "\u2665 Loved", liked: "+ Liked", disliked: "\u2212 Disliked", unrated: "Unrated" };
        const ratingItems = data.ratings.map(r => ({
            label: ratingLabels[r.name] || r.name,
            value: r.name,
            key: "rating",
            count: r.count,
        }));
        html += renderFilterSection("Rating", ratingItems);
    }

    // Sources
    if (data.sources?.length) {
        const sourceItems = data.sources.map(s => ({
            label: (s.is_vip ? "\u2605 " : "") + s.name,
            value: String(s.id),
            key: "source_id",
            count: s.count,
        }));
        html += renderFilterSection("Source", sourceItems, true);
    }

    // Tags
    if (data.tags?.length) {
        const tagItems = data.tags.map(t => ({
            label: t.name,
            value: t.name,
            key: "tag",
            count: t.count,
        }));
        html += renderFilterSection("Tag", tagItems, true);
    }

    // Ingestion method
    if (data.ingestion_methods?.length) {
        const methodLabels = { manual: "Manual", extension: "Extension", email: "Email", imap: "IMAP" };
        const methodItems = data.ingestion_methods.map(m => ({
            label: methodLabels[m.name] || m.name,
            value: m.name,
            key: "ingestion_method",
            count: m.count,
        }));
        html += renderFilterSection("Source Type", methodItems);
    }

    // Reading time
    if (data.reading_time) {
        html += renderFilterSection("Reading Time", [
            { label: "Quick (<5 min)", value: "quick", key: "_reading_time", count: data.reading_time.quick },
            { label: "Medium (5-15 min)", value: "medium", key: "_reading_time", count: data.reading_time.medium },
            { label: "Long (>15 min)", value: "long", key: "_reading_time", count: data.reading_time.long },
        ]);
    }

    // Has audio
    if (data.has_audio > 0) {
        html += renderFilterSection("Audio", [
            { label: "Has audio", value: "true", key: "has_audio", count: data.has_audio },
        ]);
    }

    body.innerHTML = html;

    // Wire up filter option clicks
    body.querySelectorAll(".filter-option").forEach(opt => {
        opt.addEventListener("click", () => {
            const key = opt.dataset.key;
            const value = opt.dataset.value;
            toggleFilter(key, value);
        });
    });

    // Show more toggles
    body.querySelectorAll(".filter-show-more").forEach(btn => {
        btn.addEventListener("click", () => {
            const section = btn.closest(".filter-section");
            const scroll = section?.querySelector(".filter-options-scroll");
            if (scroll) {
                scroll.style.maxHeight = scroll.style.maxHeight === "none" ? "200px" : "none";
                btn.textContent = scroll.style.maxHeight === "none" ? "Show less" : "Show more";
            }
        });
    });
}

function renderFilterSection(title, items, scrollable) {
    const isActive = (item) => {
        if (item.key === "_reading_time") {
            // Special handling for reading time compound filter
            if (item.value === "quick") return activeFilters.max_reading_time === "4";
            if (item.value === "medium") return activeFilters.min_reading_time === "5" && activeFilters.max_reading_time === "15";
            if (item.value === "long") return activeFilters.min_reading_time === "16";
            return false;
        }
        return activeFilters[item.key] === item.value;
    };

    const optionsHtml = items.map(item =>
        `<button class="filter-option${isActive(item) ? " active" : ""}"
                data-key="${item.key}" data-value="${esc(item.value)}">
            <span>${item.label}</span>
            <span class="filter-option-count">${item.count}</span>
        </button>`
    ).join("");

    const showMore = scrollable && items.length > 8
        ? '<button class="filter-show-more">Show more</button>'
        : "";

    const wrapClass = scrollable ? "filter-options filter-options-scroll" : "filter-options";

    return `<div class="filter-section">
        <div class="filter-section-title">${title}</div>
        <div class="${wrapClass}">${optionsHtml}</div>
        ${showMore}
    </div>`;
}

function toggleFilter(key, value) {
    if (key === "_reading_time") {
        // Special reading time handling
        const wasActive = (value === "quick" && activeFilters.max_reading_time === "4")
            || (value === "medium" && activeFilters.min_reading_time === "5" && activeFilters.max_reading_time === "15")
            || (value === "long" && activeFilters.min_reading_time === "16");

        delete activeFilters.min_reading_time;
        delete activeFilters.max_reading_time;

        if (!wasActive) {
            if (value === "quick") { activeFilters.max_reading_time = "4"; }
            else if (value === "medium") { activeFilters.min_reading_time = "5"; activeFilters.max_reading_time = "15"; }
            else if (value === "long") { activeFilters.min_reading_time = "16"; }
        }
    } else {
        // Toggle: if same value, remove; otherwise set
        if (activeFilters[key] === value) {
            delete activeFilters[key];
        } else {
            activeFilters[key] = value;
        }
    }

    currentPage = 1;
    loadInbox();
    if (filterData) renderFilterPanelContent(filterData);
    updateFilterTabIndicator();
}

function removeFilter(key) {
    if (key === "_reading_time") {
        delete activeFilters.min_reading_time;
        delete activeFilters.max_reading_time;
    } else {
        delete activeFilters[key];
    }
    currentPage = 1;
    loadInbox();
    if (filterData) renderFilterPanelContent(filterData);
    updateFilterTabIndicator();
}

/* ---- Active filter pills ---- */

function renderActiveFilters() {
    const container = document.getElementById("active-filters");
    if (!container) return;

    const pills = [];
    const labelMap = {
        is_read: v => v === "true" ? "Read" : "Unread",
        is_vip: v => v === "true" ? "VIP" : "Not VIP",
        ai_tier: v => ({ "must-read": "Must Read", "summary-enough": "Summary", "discard": "Discard", "unclassified": "Unclassified" })[v] || v,
        author: v => `Author: ${v}`,
        source_id: v => {
            if (filterData?.sources) {
                const s = filterData.sources.find(s => String(s.id) === v);
                return s ? `Source: ${s.name}` : `Source #${v}`;
            }
            return `Source #${v}`;
        },
        tag: v => `Tag: ${v}`,
        rating: v => ({ loved: "\u2665 Loved", liked: "Liked", disliked: "Disliked", unrated: "Unrated" })[v] || v,
        ingestion_method: v => ({ manual: "Manual", extension: "Extension", email: "Email", imap: "IMAP" })[v] || v,
        has_audio: () => "Has audio",
    };

    for (const [key, val] of Object.entries(activeFilters)) {
        if (val === null || val === undefined || val === "") continue;
        // Skip reading time sub-keys, handle as compound
        if (key === "min_reading_time" || key === "max_reading_time") continue;
        const label = labelMap[key] ? labelMap[key](val) : `${key}: ${val}`;
        pills.push(`<span class="filter-pill" data-key="${key}" title="Click to remove">
            ${esc(label)} <span class="filter-pill-x">&times;</span>
        </span>`);
    }

    // Compound reading time pill
    if (activeFilters.min_reading_time || activeFilters.max_reading_time) {
        let label = "Reading time";
        if (activeFilters.max_reading_time === "4") label = "Quick (<5 min)";
        else if (activeFilters.min_reading_time === "5" && activeFilters.max_reading_time === "15") label = "Medium (5-15 min)";
        else if (activeFilters.min_reading_time === "16") label = "Long (>15 min)";
        pills.push(`<span class="filter-pill" data-key="_reading_time" title="Click to remove">
            ${esc(label)} <span class="filter-pill-x">&times;</span>
        </span>`);
    }

    if (pills.length) {
        container.innerHTML = pills.join("");
        container.style.display = "flex";
        container.querySelectorAll(".filter-pill").forEach(pill => {
            pill.addEventListener("click", () => removeFilter(pill.dataset.key));
        });
    } else {
        container.style.display = "none";
        container.innerHTML = "";
    }
}

/* ---- Pagination ---- */

function toRoman(num) {
    const vals = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1];
    const syms = ["M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I"];
    let result = "";
    for (let i = 0; i < vals.length; i++) {
        while (num >= vals[i]) { result += syms[i]; num -= vals[i]; }
    }
    return result;
}

function renderPagination(pagination) {
    const container = document.getElementById("pagination");
    if (!container) return;

    if (!pagination || pagination.total_pages <= 1) {
        container.style.display = "none";
        return;
    }

    const { page, total_pages, total } = pagination;
    let html = "";

    // Previous
    html += `<button class="page-link${page <= 1 ? " disabled" : ""}" data-page="${page - 1}">&laquo;</button>`;

    // Page numbers (show max 7, with ellipsis)
    const pages = getPageRange(page, total_pages, 7);
    for (const p of pages) {
        if (p === "...") {
            html += `<span class="page-info">\u2026</span>`;
        } else {
            html += `<button class="page-link${p === page ? " active" : ""}" data-page="${p}">${toRoman(p)}</button>`;
        }
    }

    // Next
    html += `<button class="page-link${page >= total_pages ? " disabled" : ""}" data-page="${page + 1}">&raquo;</button>`;

    // Info
    html += `<span class="page-info">${total} articles</span>`;

    container.innerHTML = html;
    container.style.display = "flex";

    // Wire clicks
    container.querySelectorAll(".page-link:not(.disabled)").forEach(link => {
        link.addEventListener("click", () => {
            const p = parseInt(link.dataset.page, 10);
            if (p >= 1 && p <= total_pages) {
                currentPage = p;
                loadInbox();
                window.scrollTo({ top: 0, behavior: "smooth" });
            }
        });
    });
}

function getPageRange(current, total, maxVisible) {
    if (total <= maxVisible) {
        return Array.from({ length: total }, (_, i) => i + 1);
    }

    const pages = [];
    const half = Math.floor(maxVisible / 2);
    let start = Math.max(1, current - half);
    let end = Math.min(total, start + maxVisible - 1);

    if (end - start < maxVisible - 1) {
        start = Math.max(1, end - maxVisible + 1);
    }

    if (start > 1) {
        pages.push(1);
        if (start > 2) pages.push("...");
    }

    for (let i = start; i <= end; i++) {
        pages.push(i);
    }

    if (end < total) {
        if (end < total - 1) pages.push("...");
        pages.push(total);
    }

    return pages;
}

/* ---- Keyboard navigation ---- */

function setupKeyboard() {
    // Only activate on the inbox page (not reader)
    if (!document.getElementById("article-list")) return;

    document.addEventListener("keydown", handleInboxKeydown);

    // Shortcuts overlay close
    const closeBtn = document.getElementById("shortcuts-close");
    if (closeBtn) {
        closeBtn.addEventListener("click", hideShortcuts);
    }
    const overlay = document.getElementById("shortcuts-overlay");
    if (overlay) {
        overlay.addEventListener("click", (e) => {
            if (e.target === overlay) hideShortcuts();
        });
    }
}

function handleInboxKeydown(e) {
    // Don't capture when typing in inputs
    const tag = document.activeElement.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
        if (e.key === "Escape") {
            document.activeElement.blur();
            e.preventDefault();
        }
        return;
    }

    // Don't capture when shortcuts overlay is open (except ? and Escape to close)
    const overlay = document.getElementById("shortcuts-overlay");
    if (overlay && overlay.style.display !== "none") {
        if (e.key === "?" || e.key === "Escape") {
            hideShortcuts();
            e.preventDefault();
        }
        return;
    }

    const cards = getVisibleCards();

    switch (e.key) {
        case "j":
            e.preventDefault();
            moveSelection(cards, 1);
            break;
        case "k":
            e.preventDefault();
            moveSelection(cards, -1);
            break;
        case "Enter":
            e.preventDefault();
            openSelectedArticle(cards);
            break;
        case "s":
            e.preventDefault();
            toggleSelectedVip(cards);
            break;
        case "1":
            e.preventDefault();
            rateSelected(cards, -1); // dislike
            break;
        case "2":
            e.preventDefault();
            rateSelected(cards, 1); // like
            break;
        case "3":
            e.preventDefault();
            rateSelected(cards, 2); // love
            break;
        case "/":
            e.preventDefault();
            document.getElementById("search-input")?.focus();
            break;
        case "d":
            e.preventDefault();
            window.location.href = "/digest";
            break;
        case "r":
            e.preventDefault();
            // Generate or regenerate digest if on digest page
            if (document.querySelector(".digest-tab")) {
                loadDigest(digestLoaded);
            }
            break;
        case "c":
            e.preventDefault();
            {
                const btn = document.getElementById("classify-btn");
                if (btn && !btn.disabled) btn.click();
            }
            break;
        case "g":
            e.preventDefault();
            window.location.href = "/stats";
            break;
        case "v":
            e.preventDefault();
            window.location.href = "/graph";
            break;
        case "f":
            e.preventDefault();
            {
                const tab = document.getElementById("filter-tab");
                if (tab) tab.click();
            }
            break;
        case "?":
            e.preventDefault();
            showShortcuts("inbox");
            break;
    }
}

function getVisibleCards() {
    const listEl = document.getElementById("article-list");
    if (!listEl) return [];
    // Get only visible cards (not hidden discards)
    return Array.from(listEl.querySelectorAll(".article-card")).filter(
        (card) => card.offsetParent !== null
    );
}

function moveSelection(cards, direction) {
    if (!cards.length) return;

    // Clear previous selection
    const prev = document.querySelector(".article-card.kb-selected");
    if (prev) prev.classList.remove("kb-selected");

    // Calculate new index
    if (selectedIndex === -1) {
        selectedIndex = direction === 1 ? 0 : cards.length - 1;
    } else {
        selectedIndex += direction;
    }

    // Clamp
    selectedIndex = Math.max(0, Math.min(cards.length - 1, selectedIndex));

    // Apply selection
    const card = cards[selectedIndex];
    card.classList.add("kb-selected");
    card.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function openSelectedArticle(cards) {
    if (selectedIndex < 0 || selectedIndex >= cards.length) return;
    const card = cards[selectedIndex];
    const link = card.querySelector(".article-title a");
    if (link) link.click();
}

function toggleSelectedVip(cards) {
    if (selectedIndex < 0 || selectedIndex >= cards.length) return;
    const card = cards[selectedIndex];
    const star = card.querySelector(".vip-star");
    if (star) star.click();
}

function rateSelected(cards, rating) {
    if (selectedIndex < 0 || selectedIndex >= cards.length) return;
    const card = cards[selectedIndex];
    const btn = card.querySelector(`.rate-btn[data-rating="${rating}"]`);
    if (btn) btn.click();
}


/* ---- Shortcuts overlay ---- */

const INBOX_SHORTCUTS = [
    { section: "Navigation" },
    { keys: ["j"], desc: "Move down" },
    { keys: ["k"], desc: "Move up" },
    { keys: ["Enter"], desc: "Open selected article" },
    { keys: ["/"], desc: "Focus search bar" },
    { keys: ["d"], desc: "Go to digest" },
    { keys: ["g"], desc: "Go to reading stats" },
    { keys: ["v"], desc: "Go to knowledge graph" },
    { section: "Actions" },
    { keys: ["s"], desc: "Toggle VIP on selected source" },
    { keys: ["1"], desc: "Rate dislike" },
    { keys: ["2"], desc: "Rate like" },
    { keys: ["3"], desc: "Rate love" },
    { keys: ["c"], desc: "Classify / reclassify inbox" },
    { keys: ["f"], desc: "Toggle filter panel" },
    { keys: ["r"], desc: "Regenerate digest (in digest view)" },
    { section: "General" },
    { keys: ["?"], desc: "Show this help" },
    { keys: ["Esc"], desc: "Blur search / close overlay" },
];

const READER_SHORTCUTS = [
    { section: "Navigation" },
    { keys: ["b", "Esc"], desc: "Back to inbox" },
    { keys: ["d"], desc: "Go to digest" },
    { keys: ["g"], desc: "Go to reading stats" },
    { keys: ["v"], desc: "Go to knowledge graph" },
    { section: "Actions" },
    { keys: ["s"], desc: "Toggle VIP on source" },
    { keys: ["1"], desc: "Rate dislike" },
    { keys: ["2"], desc: "Rate like" },
    { keys: ["3"], desc: "Rate love" },
    { keys: ["i"], desc: "Toggle analysis panel" },
    { keys: ["r"], desc: "Run / re-run analysis (panel open)" },
    { keys: ["p"], desc: "Play / pause audio" },
    { section: "General" },
    { keys: ["?"], desc: "Show this help" },
];

function showShortcuts(view) {
    const overlay = document.getElementById("shortcuts-overlay");
    const body = document.getElementById("shortcuts-body");
    if (!overlay || !body) return;

    const shortcuts = view === "reader" ? READER_SHORTCUTS : INBOX_SHORTCUTS;

    body.innerHTML = shortcuts
        .map((item) => {
            if (item.section) {
                return `<div class="shortcut-section">${item.section}</div>`;
            }
            const keys = item.keys
                .map((k) => `<kbd>${esc(k)}</kbd>`)
                .join(" / ");
            return `<div class="shortcut-row">
                <span class="shortcut-keys">${keys}</span>
                <span class="shortcut-desc">${esc(item.desc)}</span>
            </div>`;
        })
        .join("");

    overlay.style.display = "flex";
}

function hideShortcuts() {
    const overlay = document.getElementById("shortcuts-overlay");
    if (overlay) overlay.style.display = "none";
}
