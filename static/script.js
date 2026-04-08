/**
 * script.js — NIFTY Market Analysis Dashboard
 * Handles API calls, DOM rendering, animations, tab switching,
 * and intraday prediction rendering.
 * News items are sorted by published date/time (most recent first).
 */

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// State
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

let analysisData = null;
let currentFilter = "ALL";
let activeTab = "btst";

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// DOM Refs
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

const btnAnalyze = document.getElementById("btn-analyze");
const btnAnalyzeText = document.getElementById("btn-analyze-text");
const loadingOverlay = document.getElementById("loading-overlay");
const loadingText = document.getElementById("loading-text");
const loadingSubtext = document.getElementById("loading-subtext");
const dashboard = document.getElementById("dashboard");
const errorContainer = document.getElementById("error-container");

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Tab Navigation
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function initTabs() {
    document.querySelectorAll(".tab-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            const tab = btn.dataset.tab;
            switchTab(tab);
        });
    });
}

function switchTab(tab) {
    activeTab = tab;

    // Update buttons
    document.querySelectorAll(".tab-btn").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.tab === tab);
    });

    // Update content
    document.querySelectorAll(".tab-content").forEach((content) => {
        content.classList.toggle("active", content.id === `content-${tab}`);
    });
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Loading Messages (cycle through while scraping)
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

const LOADING_MESSAGES = [
    { text: "Connecting to news sources...", sub: "Fetching RSS feeds from Google News, Livemint, Economic Times" },
    { text: "Scraping Indian market news...", sub: "Collecting NIFTY, Sensex, RBI, and market updates" },
    { text: "Fetching global macro data...", sub: "US Fed, inflation, crude oil, and geopolitical news" },
    { text: "Scanning corporate earnings...", sub: "Banking, IT, Pharma, and other sector results" },
    { text: "Classifying news by sector...", sub: "Banking, IT, Pharma, Auto, Energy, FMCG, Metals..." },
    { text: "Running sentiment analysis...", sub: "Evaluating bullish vs bearish signals with weighted scoring" },
    { text: "Generating intraday prediction...", sub: "Analyzing patterns, volatility, and market phase for today" },
    { text: "Computing BTST prediction...", sub: "Generating GAP UP / GAP DOWN / FLAT forecast" },
    { text: "Finalising analysis...", sub: "Preparing your market intelligence report" },
];

let loadingInterval = null;

function startLoadingMessages() {
    let idx = 0;
    updateLoadingMessage(idx);
    loadingInterval = setInterval(() => {
        idx = (idx + 1) % LOADING_MESSAGES.length;
        updateLoadingMessage(idx);
    }, 3000);
}

function updateLoadingMessage(idx) {
    if (loadingText) loadingText.textContent = LOADING_MESSAGES[idx].text;
    if (loadingSubtext) loadingSubtext.textContent = LOADING_MESSAGES[idx].sub;
}

function stopLoadingMessages() {
    if (loadingInterval) {
        clearInterval(loadingInterval);
        loadingInterval = null;
    }
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Date Parsing & News Sorting
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

/**
 * Parse a date string like "08 Apr 2026, 10:30 AM" into a Date object.
 * Falls back to current time if parsing fails.
 */
function parseNewsDate(dateStr) {
    if (!dateStr) return new Date(0);
    // Try native parse first (handles many formats)
    const d = new Date(dateStr);
    if (!isNaN(d.getTime())) return d;
    // Fallback: return epoch so unparseable dates sort to end
    return new Date(0);
}

/**
 * Sort news items by published_date descending (most recent first).
 */
function sortNewsByDate(newsArray) {
    if (!newsArray || newsArray.length === 0) return newsArray;
    return [...newsArray].sort((a, b) => {
        const dateA = parseNewsDate(a.published_date);
        const dateB = parseNewsDate(b.published_date);
        return dateB.getTime() - dateA.getTime(); // Descending: newest first
    });
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// API Call
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async function startAnalysis() {
    // UI: show loading
    btnAnalyze.disabled = true;
    btnAnalyzeText.textContent = "Analysing...";
    dashboard.classList.remove("active");
    errorContainer.innerHTML = "";
    loadingOverlay.classList.add("active");
    startLoadingMessages();

    try {
        const response = await fetch("/api/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
        });

        const json = await response.json();

        if (json.status === "error") {
            throw new Error(json.message || "Unknown server error");
        }

        analysisData = json.data;

        // Sort all news arrays by date (most recent first)
        if (analysisData.all_news) {
            analysisData.all_news = sortNewsByDate(analysisData.all_news);
        }
        if (analysisData.major_news) {
            analysisData.major_news = sortNewsByDate(analysisData.major_news);
        }

        renderDashboard(analysisData);
    } catch (err) {
        console.error("Analysis failed:", err);
        renderError(err.message);
    } finally {
        stopLoadingMessages();
        loadingOverlay.classList.remove("active");
        btnAnalyze.disabled = false;
        btnAnalyzeText.textContent = "Re-Analyse Market";
    }
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Render Dashboard
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function renderDashboard(data) {
    // BTST Tab
    renderPredictionHero(data);
    renderInfoStrip(data);
    renderScoreBar(data);
    renderSummary(data);
    renderEventRisk(data);
    renderKeyDrivers(data);
    renderFactors(data);
    renderSectorSummary(data);

    // Intraday Tab
    renderIntradayPrediction(data);

    // Common: News (sorted by date)
    renderNewsCards(data);

    dashboard.classList.add("active");

    // Scroll to dashboard
    setTimeout(() => {
        dashboard.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 200);
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Prediction Hero (BTST)
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function renderPredictionHero(data) {
    const pred = data.prediction;
    const conf = data.confidence;
    const btst = data.btst_bias;

    // Prediction card
    const predCard = document.getElementById("prediction-card");
    const predValue = document.getElementById("prediction-value");
    const predSentiment = document.getElementById("prediction-sentiment");

    predCard.className = "card prediction-card " + predClassKey(pred);
    predValue.className = "prediction-value " + predClassKey(pred);
    predValue.textContent = pred;

    const sentimentEmoji = { BULLISH: "🟢", BEARISH: "🔴", MIXED: "🟡" };
    predSentiment.textContent = `${sentimentEmoji[data.news_sentiment] || "⚪"} Sentiment: ${data.news_sentiment}`;

    // Confidence gauge
    animateGauge(conf, "gauge-fill", "gauge-number");

    // BTST badge
    const btstBadge = document.getElementById("btst-badge");
    const btstIcon = document.getElementById("btst-icon");
    btstBadge.className = "btst-badge " + btstClassKey(btst);
    btstBadge.querySelector("span:last-child").textContent = btst;

    if (btst === "BUY CE") {
        btstIcon.textContent = "📈";
    } else if (btst === "BUY PE") {
        btstIcon.textContent = "📉";
    } else {
        btstIcon.textContent = "⏸️";
    }
}

function predClassKey(pred) {
    if (pred === "GAP UP") return "gap-up";
    if (pred === "GAP DOWN") return "gap-down";
    return "flat";
}

function btstClassKey(btst) {
    if (btst === "BUY CE") return "buy-ce";
    if (btst === "BUY PE") return "buy-pe";
    return "no-trade";
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Confidence Gauge Animation
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function animateGauge(value, fillId, numberId) {
    const gaugeFill = document.getElementById(fillId);
    const gaugeNumber = document.getElementById(numberId);
    const circumference = 2 * Math.PI * 54; // radius = 54

    // Set initial state
    gaugeFill.style.strokeDasharray = circumference;
    gaugeFill.style.strokeDashoffset = circumference;

    // Determine color
    let color;
    if (value >= 65) color = "var(--bullish)";
    else if (value >= 40) color = "var(--neutral)";
    else color = "var(--bearish)";

    gaugeFill.style.stroke = color;

    // Animate after a small delay
    setTimeout(() => {
        const offset = circumference - (value / 100) * circumference;
        gaugeFill.style.strokeDashoffset = offset;
    }, 100);

    // Animate number
    animateNumber(gaugeNumber, 0, value, 1200);
}

function animateNumber(element, start, end, duration) {
    const startTime = performance.now();
    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3); // easeOutCubic
        const current = Math.round(start + (end - start) * eased);
        element.textContent = current;
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Info Strip
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function renderInfoStrip(data) {
    const container = document.getElementById("info-strip");
    const scores = data.scores;
    const netClass = scores.net_score >= 0 ? "positive" : "negative";
    const netPrefix = scores.net_score >= 0 ? "+" : "";

    container.innerHTML = `
        <div class="info-chip">
            🟢 Bullish Score: <span class="info-chip__value positive">${scores.total_bullish}</span>
        </div>
        <div class="info-chip">
            🔴 Bearish Score: <span class="info-chip__value negative">${scores.total_bearish}</span>
        </div>
        <div class="info-chip">
            📊 Net Score: <span class="info-chip__value ${netClass}">${netPrefix}${scores.net_score}</span>
        </div>
        <div class="info-chip">
            📰 News Analyzed: <span class="info-chip__value">${data.total_news_analyzed}</span>
        </div>
        <div class="info-chip">
            🕐 ${data.analysis_timestamp}
        </div>
    `;
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Score Bar
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function renderScoreBar(data) {
    const scores = data.scores;
    const total = scores.total_bullish + scores.total_bearish;
    const bullPct = total > 0 ? (scores.total_bullish / total) * 100 : 50;
    const bearPct = total > 0 ? (scores.total_bearish / total) * 100 : 50;

    const bullBar = document.getElementById("score-bar-bull");
    const bearBar = document.getElementById("score-bar-bear");
    const bullLabel = document.getElementById("score-label-bull");
    const bearLabel = document.getElementById("score-label-bear");

    // Animate after a small delay
    setTimeout(() => {
        bullBar.style.width = bullPct + "%";
        bearBar.style.width = bearPct + "%";
    }, 300);

    bullLabel.textContent = `Bullish ${Math.round(bullPct)}%`;
    bearLabel.textContent = `Bearish ${Math.round(bearPct)}%`;
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Summary
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function renderSummary(data) {
    document.getElementById("summary-text").textContent = data.final_summary;
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Event Risk
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function renderEventRisk(data) {
    const container = document.getElementById("event-risk");
    const risk = data.event_risk;
    const icons = { HIGH: "🚨", MEDIUM: "⚠️", LOW: "✅" };
    const messages = {
        HIGH: "HIGH EVENT RISK — Major economic event imminent. Consider avoiding BTST trades.",
        MEDIUM: "MODERATE EVENT RISK — Potential volatility ahead. Trade with caution.",
        LOW: "LOW EVENT RISK — No major events detected. Normal trading conditions expected.",
    };

    container.className = "event-risk-strip " + risk.toLowerCase();
    container.innerHTML = `
        <span>${icons[risk]}</span>
        <span>Event Risk: ${risk}</span>
        <span style="margin-left: auto; font-weight: 400; font-size: 0.82rem; opacity: 0.8;">${messages[risk]}</span>
    `;
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Key Drivers
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function renderKeyDrivers(data) {
    const container = document.getElementById("key-drivers");
    container.innerHTML = data.key_drivers
        .map(
            (driver) => `
        <div class="driver-item">
            <span class="driver-item__icon"></span>
            <span>${escapeHtml(driver)}</span>
        </div>
    `
        )
        .join("");
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Factors (Bullish vs Bearish)
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function renderFactors(data) {
    const bullContainer = document.getElementById("bullish-factors");
    const bearContainer = document.getElementById("bearish-factors");

    bullContainer.innerHTML = data.bullish_factors.length
        ? data.bullish_factors
              .map(
                  (f) => `
            <div class="factor-item">
                <span class="factor-bullet"></span>
                <span>${escapeHtml(f)}</span>
            </div>
        `
              )
              .join("")
        : '<div class="factor-item" style="color: var(--text-muted);">No strong bullish signals detected</div>';

    bearContainer.innerHTML = data.bearish_factors.length
        ? data.bearish_factors
              .map(
                  (f) => `
            <div class="factor-item">
                <span class="factor-bullet"></span>
                <span>${escapeHtml(f)}</span>
            </div>
        `
              )
              .join("")
        : '<div class="factor-item" style="color: var(--text-muted);">No strong bearish signals detected</div>';
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Sector Summary
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function renderSectorSummary(data) {
    const container = document.getElementById("sector-grid");

    if (!data.sector_summary || data.sector_summary.length === 0) {
        container.innerHTML = '<div style="color: var(--text-muted); padding: 16px;">No sector data available</div>';
        return;
    }

    container.innerHTML = data.sector_summary
        .map(
            (sec) => `
        <div class="sector-card">
            <div>
                <div class="sector-card__name">${escapeHtml(sec.sector)}</div>
                <div class="sector-card__count">${sec.news_count} article${sec.news_count !== 1 ? "s" : ""} · Bull: ${sec.bullish_score} / Bear: ${sec.bearish_score}</div>
            </div>
            <div class="sector-card__badge ${sec.sentiment.toLowerCase()}">${sec.sentiment}</div>
        </div>
    `
        )
        .join("");
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Intraday Prediction Rendering
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function renderIntradayPrediction(data) {
    if (!data.intraday) return;

    const intraday = data.intraday;
    const bias = intraday.intraday_bias;
    const pattern = intraday.intraday_pattern;
    const phase = intraday.market_phase;
    const vol = intraday.volatility;

    // ── Intraday Bias Card ──
    const biasValueEl = document.getElementById("intraday-bias-value");
    biasValueEl.textContent = bias.bias;
    biasValueEl.className = `intraday-bias-value ${getIntradayBiasClass(bias.bias)}`;

    document.getElementById("intraday-bias-icon").textContent = bias.icon;
    document.getElementById("intraday-confidence-text").textContent = `Confidence: ${bias.confidence}%`;

    const biasCard = document.getElementById("intraday-bias-card");
    biasCard.className = `card intraday-bias-card ${getIntradayBiasClass(bias.bias)}`;

    // ── Intraday Gauge ──
    animateGauge(bias.confidence, "intraday-gauge-fill", "intraday-gauge-number");

    // ── Volatility Card ──
    const volBadge = document.getElementById("volatility-badge");
    volBadge.textContent = vol.level;
    volBadge.className = `volatility-badge vol-${vol.level.toLowerCase()}`;

    document.getElementById("volatility-range").textContent = vol.expected_range;
    document.getElementById("volatility-pct").textContent = `~${vol.nifty_range_pct}`;

    // ── Market Phase ──
    const phaseStrip = document.getElementById("market-phase-strip");
    phaseStrip.innerHTML = `
        <span>${phase.icon}</span>
        <span class="market-phase-name">${phase.phase}</span>
        <span class="market-phase-desc">${phase.description}</span>
    `;

    // ── Intraday Pattern ──
    const patternName = document.getElementById("intraday-pattern-name");
    patternName.textContent = pattern.pattern;
    patternName.className = `intraday-pattern-name ${getPatternClass(pattern.pattern)}`;

    document.getElementById("intraday-pattern-desc").textContent = pattern.description;
    document.getElementById("intraday-strategy-text").textContent = pattern.strategy;
    document.getElementById("intraday-option-strategy-text").textContent = pattern.option_strategy;

    const riskLevel = document.getElementById("intraday-risk-level");
    riskLevel.textContent = `⚠️ Risk Level: ${pattern.risk_level}`;
    riskLevel.className = `intraday-risk-level risk-${pattern.risk_level.toLowerCase().replace(" ", "-")}`;

    // ── Strategies ──
    const strategiesContainer = document.getElementById("intraday-strategies");
    strategiesContainer.innerHTML = bias.strategies
        .map(
            (s) => `
        <div class="driver-item strategy-item">
            <span class="driver-item__icon"></span>
            <span>${escapeHtml(s)}</span>
        </div>
    `
        )
        .join("");

    // ── Intraday Drivers ──
    const driversContainer = document.getElementById("intraday-drivers");
    driversContainer.innerHTML = intraday.intraday_drivers
        .map(
            (d) => `
        <div class="driver-item">
            <span class="driver-item__icon"></span>
            <span>${escapeHtml(d)}</span>
        </div>
    `
        )
        .join("");

    // ── Intraday Summary ──
    document.getElementById("intraday-summary-text").textContent = intraday.intraday_summary;
}

function getIntradayBiasClass(bias) {
    if (bias.includes("BULLISH")) return "bias-bullish";
    if (bias.includes("BEARISH")) return "bias-bearish";
    if (bias.includes("AVOID")) return "bias-avoid";
    return "bias-neutral";
}

function getPatternClass(pattern) {
    if (pattern.includes("UP") || pattern.includes("BULLISH")) return "pattern-bullish";
    if (pattern.includes("DOWN") || pattern.includes("BEARISH")) return "pattern-bearish";
    if (pattern.includes("RANGE") || pattern.includes("DRIFT")) return "pattern-neutral";
    return "pattern-volatile";
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// News Cards (sorted by date — most recent first)
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function renderNewsCards(data) {
    const filterContainer = document.getElementById("news-filters");
    const newsGrid = document.getElementById("news-grid");

    // Build filter buttons from sectors
    const sectors = new Set(["ALL"]);
    const allNews = data.all_news || data.major_news || [];
    allNews.forEach((n) => sectors.add(n.sector || "General"));

    // Also add impact filters
    const impactFilters = ["BULLISH", "BEARISH", "NEUTRAL"];

    filterContainer.innerHTML = "";

    // Sector filters
    sectors.forEach((sec) => {
        const btn = document.createElement("button");
        btn.className = "filter-btn" + (sec === currentFilter ? " active" : "");
        btn.textContent = sec;
        btn.addEventListener("click", () => {
            currentFilter = sec;
            renderNewsCards(data);
        });
        filterContainer.appendChild(btn);
    });

    // Divider
    const divider = document.createElement("span");
    divider.style.cssText = "width:1px;height:24px;background:var(--border-subtle);margin:0 4px;";
    filterContainer.appendChild(divider);

    // Impact filters
    impactFilters.forEach((impact) => {
        const btn = document.createElement("button");
        btn.className = "filter-btn" + (impact === currentFilter ? " active" : "");
        btn.textContent = impact;
        btn.style.borderColor =
            impact === "BULLISH"
                ? "rgba(0,230,118,0.3)"
                : impact === "BEARISH"
                ? "rgba(255,23,68,0.3)"
                : "rgba(255,171,64,0.3)";
        btn.addEventListener("click", () => {
            currentFilter = impact;
            renderNewsCards(data);
        });
        filterContainer.appendChild(btn);
    });

    // Filter news
    let filtered = allNews;
    if (currentFilter !== "ALL") {
        filtered = allNews.filter(
            (n) => n.sector === currentFilter || n.impact === currentFilter
        );
    }

    // News are already sorted by date (most recent first) from startAnalysis()

    // Render
    if (filtered.length === 0) {
        newsGrid.innerHTML = `
            <div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">
                No news items match the selected filter.
            </div>
        `;
        return;
    }

    newsGrid.innerHTML = filtered
        .map(
            (n, i) => `
        <div class="news-card animate-in" style="animation-delay: ${Math.min(i * 0.05, 0.5)}s;">
            <div class="news-card__header">
                <div class="news-card__headline">
                    <a href="${escapeHtml(n.link)}" target="_blank" rel="noopener noreferrer">
                        ${escapeHtml(n.headline)}
                    </a>
                </div>
                <span class="news-card__impact ${n.impact.toLowerCase()}">
                    ${impactIcon(n.impact)} ${n.impact}
                </span>
            </div>
            <div class="news-card__meta">
                <span class="news-card__tag sector-tag">${escapeHtml(n.sector)}</span>
                <span class="news-card__tag importance-${n.importance.toLowerCase()}">${n.importance}</span>
                <span class="news-card__tag">${escapeHtml(n.category)}</span>
                <span class="news-card__divider">•</span>
                <span>${escapeHtml(n.source)}</span>
                <span class="news-card__divider">•</span>
                <span>🕐 ${escapeHtml(n.published_date)}</span>
            </div>
        </div>
    `
        )
        .join("");
}

function impactIcon(impact) {
    if (impact === "BULLISH") return "▲";
    if (impact === "BEARISH") return "▼";
    return "●";
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Error Rendering
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function renderError(message) {
    errorContainer.innerHTML = `
        <div class="card error-card animate-in">
            <div class="error-card__title">⚠️ Analysis Failed</div>
            <div class="error-card__message">${escapeHtml(message)}</div>
            <div style="margin-top: 16px; color: var(--text-muted); font-size: 0.82rem;">
                Please check your internet connection and try again.
            </div>
        </div>
    `;
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Utilities
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

function formatCrore(value) {
    if (value === undefined || value === null) return "0";
    const num = parseFloat(value);
    const prefix = num >= 0 ? "+" : "";
    return prefix + Math.abs(num).toLocaleString("en-IN", {
        maximumFractionDigits: 0,
    });
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Event Listeners
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

btnAnalyze.addEventListener("click", startAnalysis);

// Keyboard shortcut: Enter to start
document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !btnAnalyze.disabled && !dashboard.classList.contains("active")) {
        startAnalysis();
    }
});

// Initialize tabs
initTabs();
