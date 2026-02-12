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
