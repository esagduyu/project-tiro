/* Tiro — Inbox + Digest frontend */

let digestData = null; // cached digest response
let digestLoaded = false;

document.addEventListener("DOMContentLoaded", () => {
    loadInbox();
    setupViewTabs();
    setupDigestTabs();
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

/* ---- Inbox (articles list) ---- */

async function loadInbox() {
    const listEl = document.getElementById("article-list");
    const emptyEl = document.getElementById("empty-state");

    try {
        const res = await fetch("/api/articles");
        const json = await res.json();

        if (!json.success || !json.data.length) {
            emptyEl.style.display = "block";
            return;
        }

        emptyEl.style.display = "none";
        listEl.innerHTML = json.data.map(renderArticle).join("");
        attachListeners();
    } catch (err) {
        console.error("Failed to load articles:", err);
        emptyEl.style.display = "block";
    }
}

function renderArticle(a) {
    const classes = ["article-card"];
    if (a.is_read) classes.push("is-read");
    if (a.is_vip) classes.push("is-vip");

    const date = formatDate(a.ingested_at);
    const summary = a.summary || "";
    const tags = (a.tags || [])
        .map((t) => `<span class="tag">${esc(t)}</span>`)
        .join("");

    const ratingMap = { "-1": "dislike", 1: "like", 2: "love" };
    const activeRating = ratingMap[String(a.rating)] || "";

    return `
    <article class="${classes.join(" ")}" data-id="${a.id}">
        <div class="article-main">
            <div class="article-meta">
                <span class="source-name">${esc(a.source_name || a.domain || "unknown")}</span>
                <span class="vip-star ${a.is_vip ? "active" : ""}"
                      data-source-id="${a.source_id}"
                      title="Toggle VIP">&#9733;</span>
                <span class="meta-sep">&middot;</span>
                <span>${date}</span>
                <span class="meta-sep">&middot;</span>
                <span>${a.reading_time_min || "?"} min</span>
            </div>
            <h2 class="article-title">
                <a href="/articles/${a.id}" data-id="${a.id}">${esc(a.title)}</a>
            </h2>
            ${summary ? `<p class="article-summary">${esc(summary)}</p>` : ""}
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
