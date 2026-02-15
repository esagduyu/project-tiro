/* Tiro — Inbox + Digest frontend */

let digestData = null; // cached digest response
let digestLoaded = false;
let currentSort = "newest"; // "newest" | "oldest" | "importance"
let cachedArticles = []; // store articles for re-sorting without re-fetching
let selectedIndex = -1; // keyboard-selected article index
let showArchived = false; // whether to include decayed articles

document.addEventListener("DOMContentLoaded", () => {
    loadInbox();
    setupViewTabs();
    setupDigestTabs();
    setupSearch();
    setupSort();
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

async function loadInbox() {
    const listEl = document.getElementById("article-list");
    if (!listEl) return; // Not on inbox page (e.g. reader)
    const emptyEl = document.getElementById("empty-state");
    const toolbar = document.getElementById("inbox-toolbar");

    try {
        const url = showArchived ? "/api/articles?include_decayed=true" : "/api/articles?include_decayed=false";
        const res = await fetch(url);
        const json = await res.json();

        if (!json.success || !json.data.length) {
            emptyEl.style.display = "block";
            if (toolbar) toolbar.style.display = "none";
            return;
        }

        cachedArticles = json.data;
        emptyEl.style.display = "none";
        renderSortedInbox();
        updateToolbar(cachedArticles);
    } catch (err) {
        console.error("Failed to load articles:", err);
        emptyEl.style.display = "block";
    }
}

function renderSortedInbox() {
    const listEl = document.getElementById("article-list");
    const sorted = sortArticles(cachedArticles, currentSort);
    listEl.innerHTML = sorted.map(renderArticle).join("");
    attachListeners();
    selectedIndex = -1; // reset keyboard selection on re-render

    // Sync the select element
    const sortSelect = document.getElementById("sort-select");
    if (sortSelect) sortSelect.value = currentSort;
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
        if (cachedArticles.length) {
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
        // Clean up URL without reloading
        window.history.replaceState({}, "", "/");
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

    // Switch to articles view if on digest
    const articlesTab = document.querySelector('.view-tab[data-view="articles"]');
    if (articlesTab && !articlesTab.classList.contains("active")) {
        articlesTab.click();
    }

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
        await loadInbox();
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
            switchToDigest();
            break;
        case "a":
            e.preventDefault();
            switchToArticles();
            break;
        case "r":
            e.preventDefault();
            // Generate or regenerate digest if in digest view
            if (isDigestView()) {
                loadDigest(digestLoaded);
            }
            break;
        case "c":
            e.preventDefault();
            // Trigger classify/reclassify if in articles view
            if (!isDigestView()) {
                const btn = document.getElementById("classify-btn");
                if (btn && !btn.disabled) btn.click();
            }
            break;
        case "g":
            e.preventDefault();
            window.location.href = "/stats";
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

function switchToDigest() {
    const digestTab = document.querySelector('.view-tab[data-view="digest"]');
    if (digestTab) digestTab.click();
}

function switchToArticles() {
    const articlesTab = document.querySelector('.view-tab[data-view="articles"]');
    if (articlesTab) articlesTab.click();
}

function isDigestView() {
    const digestSection = document.getElementById("view-digest");
    return digestSection && digestSection.style.display !== "none";
}

/* ---- Shortcuts overlay ---- */

const INBOX_SHORTCUTS = [
    { section: "Navigation" },
    { keys: ["j"], desc: "Move down" },
    { keys: ["k"], desc: "Move up" },
    { keys: ["Enter"], desc: "Open selected article" },
    { keys: ["/"], desc: "Focus search bar" },
    { keys: ["d"], desc: "Switch to digest view" },
    { keys: ["a"], desc: "Switch to articles view" },
    { keys: ["g"], desc: "Go to reading stats" },
    { section: "Actions" },
    { keys: ["s"], desc: "Toggle VIP on selected source" },
    { keys: ["1"], desc: "Rate dislike" },
    { keys: ["2"], desc: "Rate like" },
    { keys: ["3"], desc: "Rate love" },
    { keys: ["c"], desc: "Classify / reclassify inbox" },
    { keys: ["r"], desc: "Regenerate digest (in digest view)" },
    { section: "General" },
    { keys: ["?"], desc: "Show this help" },
    { keys: ["Esc"], desc: "Blur search / close overlay" },
];

const READER_SHORTCUTS = [
    { section: "Navigation" },
    { keys: ["b", "Esc"], desc: "Back to inbox" },
    { keys: ["g"], desc: "Go to reading stats" },
    { section: "Actions" },
    { keys: ["s"], desc: "Toggle VIP on source" },
    { keys: ["1"], desc: "Rate dislike" },
    { keys: ["2"], desc: "Rate like" },
    { keys: ["3"], desc: "Rate love" },
    { keys: ["i"], desc: "Toggle analysis panel" },
    { keys: ["r"], desc: "Run / re-run analysis (panel open)" },
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
