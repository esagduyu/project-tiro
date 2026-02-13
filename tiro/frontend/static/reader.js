/* Tiro — Reader view */

document.addEventListener("DOMContentLoaded", () => {
    const reader = document.getElementById("reader");
    const articleId = reader.dataset.articleId;
    loadArticle(articleId);
});

async function loadArticle(id) {
    const loadingEl = document.getElementById("reader-loading");
    const errorEl = document.getElementById("reader-error");
    const contentEl = document.getElementById("reader-content");

    try {
        // Mark as read
        fetch(`/api/articles/${id}/read`, { method: "PATCH" }).catch(() => {});

        const res = await fetch(`/api/articles/${id}`);
        const json = await res.json();

        if (!json.success) {
            throw new Error("Failed to load article");
        }

        const a = json.data;

        // Title
        document.getElementById("reader-title").textContent = a.title;
        document.title = `${a.title} — Tiro`;

        // Source
        document.getElementById("reader-source").textContent =
            a.source_name || a.domain || "Unknown source";

        // VIP indicator
        if (a.is_vip) {
            const vip = document.getElementById("reader-vip");
            vip.style.display = "inline";
            vip.classList.add("active");
        }

        // Author
        const authorEl = document.getElementById("reader-author");
        const authorSep = document.getElementById("author-sep");
        if (a.author) {
            authorEl.textContent = a.author;
        } else {
            authorEl.style.display = "none";
            authorSep.style.display = "none";
        }

        // Date
        document.getElementById("reader-date").textContent = formatDate(
            a.published_at || a.ingested_at
        );

        // Reading time
        document.getElementById("reader-time").textContent =
            `${a.reading_time_min || "?"} min read`;

        // Original URL
        const linkEl = document.getElementById("reader-original-link");
        if (a.url) {
            linkEl.href = a.url;
            linkEl.textContent = new URL(a.url).hostname;
        } else {
            linkEl.parentElement.style.display = "none";
        }

        // Tags
        const tagsEl = document.getElementById("reader-tags");
        if (a.tags && a.tags.length) {
            tagsEl.innerHTML = a.tags
                .map((t) => `<span class="tag">${esc(t)}</span>`)
                .join("");
        }

        // Summary
        const summaryEl = document.getElementById("reader-summary");
        if (a.summary) {
            summaryEl.textContent = a.summary;
        } else {
            summaryEl.style.display = "none";
        }

        // Markdown body
        const bodyEl = document.getElementById("reader-body");
        if (a.content) {
            bodyEl.innerHTML = marked.parse(a.content);
            // Open external links in new tab
            bodyEl.querySelectorAll("a").forEach((link) => {
                if (link.hostname && link.hostname !== location.hostname) {
                    link.target = "_blank";
                    link.rel = "noopener noreferrer";
                }
            });
        }

        // Rating buttons
        setupRating(a.id, a.rating);

        // Related articles
        loadRelatedArticles(a.id);

        // Analysis panel
        setupAnalysis(a.id);

        loadingEl.style.display = "none";
        contentEl.style.display = "block";
    } catch (err) {
        console.error("Failed to load article:", err);
        loadingEl.style.display = "none";
        errorEl.style.display = "block";
    }
}

function setupRating(articleId, currentRating) {
    const ratingMap = { "-1": "dislike", "1": "like", "2": "love" };
    const active = ratingMap[String(currentRating)] || "";

    document.querySelectorAll(".reader-actions .rate-btn").forEach((btn) => {
        const ratingClass = btn.classList.contains("love")
            ? "love"
            : btn.classList.contains("like")
            ? "like"
            : "dislike";
        if (ratingClass === active) btn.classList.add("active");

        btn.addEventListener("click", async () => {
            const rating = parseInt(btn.dataset.rating, 10);
            try {
                const res = await fetch(`/api/articles/${articleId}/rate`, {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ rating }),
                });
                const json = await res.json();
                if (json.success) {
                    document
                        .querySelectorAll(".reader-actions .rate-btn")
                        .forEach((b) => b.classList.remove("active"));
                    btn.classList.add("active");
                }
            } catch (err) {
                console.error("Rating failed:", err);
            }
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

/* --- Ingenuity Analysis Panel --- */

function setupAnalysis(articleId) {
    const btn = document.getElementById("analysis-btn");
    const panel = document.getElementById("analysis-panel");
    const overlay = document.getElementById("analysis-overlay");
    const closeBtn = document.getElementById("analysis-close");
    const retryBtn = document.getElementById("analysis-retry");

    function openPanel() {
        panel.classList.add("open");
        overlay.classList.add("open");
    }
    function closePanel() {
        panel.classList.remove("open");
        overlay.classList.remove("open");
    }

    closeBtn.addEventListener("click", closePanel);
    overlay.addEventListener("click", closePanel);

    btn.addEventListener("click", () => {
        openPanel();
        fetchAnalysis(articleId, false);
    });

    retryBtn.addEventListener("click", () => {
        fetchAnalysis(articleId, true);
    });
}

async function fetchAnalysis(articleId, refresh) {
    const loadingEl = document.getElementById("analysis-loading");
    const errorEl = document.getElementById("analysis-error");
    const bodyEl = document.getElementById("analysis-body");

    loadingEl.style.display = "block";
    errorEl.style.display = "none";
    bodyEl.style.display = "none";

    try {
        const url = `/api/articles/${articleId}/analysis${refresh ? "?refresh=true" : ""}`;
        const res = await fetch(url);
        const json = await res.json();

        if (!res.ok || !json.success) {
            throw new Error(json.detail || "Analysis failed");
        }

        renderAnalysis(json.data);
        loadingEl.style.display = "none";
        bodyEl.style.display = "block";
    } catch (err) {
        console.error("Analysis failed:", err);
        loadingEl.style.display = "none";
        errorEl.style.display = "block";
    }
}

function scoreColor(score) {
    if (score >= 7) return "score-good";
    if (score >= 4) return "score-caution";
    return "score-concern";
}

function renderAnalysis(data) {
    const bodyEl = document.getElementById("analysis-body");

    const biasScore = data.bias?.score ?? "?";
    const factScore = data.factual_confidence?.score ?? "?";
    const novelScore = data.novelty?.score ?? "?";

    bodyEl.innerHTML = `
        <div class="analysis-summary">${esc(data.overall_summary || "")}</div>

        <div class="analysis-dimension">
            <div class="dimension-header">
                <span class="dimension-title">Bias</span>
                <span class="dimension-score ${scoreColor(biasScore)}">${biasScore}/10</span>
            </div>
            <div class="dimension-detail">
                <span class="dimension-lean">${esc(data.bias?.lean || "")}</span>
            </div>
            ${renderList("Indicators", data.bias?.indicators)}
            ${renderList("Missing perspectives", data.bias?.missing_perspectives)}
        </div>

        <div class="analysis-dimension">
            <div class="dimension-header">
                <span class="dimension-title">Factual Confidence</span>
                <span class="dimension-score ${scoreColor(factScore)}">${factScore}/10</span>
            </div>
            ${renderList("Well-sourced claims", data.factual_confidence?.well_sourced_claims)}
            ${renderList("Unsourced assertions", data.factual_confidence?.unsourced_assertions)}
            ${renderList("Flags", data.factual_confidence?.flags)}
        </div>

        <div class="analysis-dimension">
            <div class="dimension-header">
                <span class="dimension-title">Novelty</span>
                <span class="dimension-score ${scoreColor(novelScore)}">${novelScore}/10</span>
            </div>
            <div class="dimension-detail">${esc(data.novelty?.assessment || "")}</div>
            ${renderList("Novel claims", data.novelty?.novel_claims)}
        </div>

        <div class="analysis-actions">
            <button onclick="fetchAnalysis(${document.getElementById('reader').dataset.articleId}, true)" class="analysis-refresh-btn">Re-analyze</button>
        </div>
    `;
}

/* --- Related articles --- */

async function loadRelatedArticles(articleId) {
    const section = document.getElementById("related-articles");
    const listEl = document.getElementById("related-list");

    try {
        const res = await fetch(`/api/articles/${articleId}/related`);
        const json = await res.json();

        if (!json.success || !json.data || !json.data.length) {
            return;
        }

        listEl.innerHTML = json.data.map((r) => {
            const date = formatDate(r.ingested_at);
            const note = r.connection_note
                ? `<div class="related-card-note">${esc(r.connection_note)}</div>`
                : "";
            const score = Math.round(r.similarity_score * 100);
            return `
            <div class="related-card">
                <a href="/articles/${r.related_article_id}">
                    <div class="related-card-title">${esc(r.title)}</div>
                </a>
                <div class="related-card-meta">
                    <span>${esc(r.source_name || "")}</span>
                    <span class="meta-sep">&middot;</span>
                    <span>${date}</span>
                    <span class="meta-sep">&middot;</span>
                    <span class="similarity-badge">${score}% similar</span>
                </div>
                ${note}
            </div>`;
        }).join("");

        section.style.display = "block";
    } catch (err) {
        console.error("Failed to load related articles:", err);
    }
}

function renderList(label, items) {
    if (!items || !items.length) return "";
    const lis = items.map((item) => `<li>${esc(item)}</li>`).join("");
    return `<div class="dimension-list">
        <span class="dimension-list-label">${esc(label)}</span>
        <ul>${lis}</ul>
    </div>`;
}
