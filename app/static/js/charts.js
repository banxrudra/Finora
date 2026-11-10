/* Finora — Chart.js theming + chart builders.
   Colours are read from CSS custom properties so charts follow light/dark mode. */
(function () {
  "use strict";
  if (!window.Chart) return;

  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const registry = [];

  const currency = () => document.body.dataset.currency || "INR";
  const symbol = () => document.body.dataset.symbol || "₹";
  const indian = () => currency() === "INR";

  function fmt(v, decimals = 0) {
    const n = Number(v || 0);
    const s = Math.abs(n).toLocaleString(indian() ? "en-IN" : "en-US", {
      minimumFractionDigits: decimals, maximumFractionDigits: decimals,
    });
    return (n < 0 ? "−" : "") + symbol() + s;
  }
  function compact(v) {
    const n = Number(v || 0), a = Math.abs(n), sign = n < 0 ? "−" : "";
    const steps = indian() ? [[1e7, "Cr"], [1e5, "L"], [1e3, "K"]] : [[1e9, "B"], [1e6, "M"], [1e3, "K"]];
    for (const [size, suf] of steps) {
      if (a >= size) return sign + symbol() + (a / size).toFixed(1).replace(/\.0$/, "") + suf;
    }
    return sign + symbol() + a.toFixed(0);
  }
  window.FinoraFmt = { money: fmt, compact };

  function alpha(hex, a) {
    const h = hex.replace("#", "");
    const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  }

  function theme() {
    return {
      text: css("--text"), text2: css("--text-2"), text3: css("--text-3"),
      grid: css("--grid"), surface: css("--surface"), border: css("--border"),
      income: css("--series-income"), expense: css("--series-expense"),
      savings: css("--series-savings"), muted: css("--series-muted"),
      neg: css("--neg"), pos: css("--pos"),
    };
  }

  function applyDefaults() {
    const t = theme();
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.font.size = 12;
    Chart.defaults.color = t.text3;
    Chart.defaults.borderColor = t.grid;
    Chart.defaults.animation.duration = 500;
    Chart.defaults.plugins.legend.display = false;
    Object.assign(Chart.defaults.plugins.tooltip, {
      backgroundColor: t.surface === "#ffffff" ? "#0e1a2e" : "#1c2840",
      titleColor: "#fff", bodyColor: "#d6deea", borderColor: "rgba(255,255,255,.08)", borderWidth: 1,
      padding: 11, cornerRadius: 10, boxPadding: 5, usePointStyle: true,
      titleFont: { weight: "600", size: 12 }, bodyFont: { size: 12 },
    });
  }

  const moneyTicks = { callback: (v) => compact(v), maxTicksLimit: 6, padding: 8 };
  function axes(t, opts = {}) {
    return {
      x: { grid: { display: false }, border: { display: false }, ticks: { padding: 6, maxRotation: 0, autoSkipPadding: 12 }, stacked: !!opts.stacked },
      y: {
        beginAtZero: true, stacked: !!opts.stacked, border: { display: false },
        grid: { color: t.grid, drawTicks: false }, ticks: moneyTicks,
      },
    };
  }
  const moneyTooltip = (decimals = 0) => ({
    callbacks: { label: (c) => ` ${c.dataset.label}: ${fmt(c.parsed.y ?? c.parsed, decimals)}` },
  });

  // Vertical hover line for line charts
  const crosshair = {
    id: "crosshair",
    afterDatasetsDraw(chart) {
      const a = chart.tooltip?.getActiveElements?.();
      if (!a || !a.length || chart.config.type !== "line") return;
      const { ctx, chartArea } = chart;
      const x = a[0].element.x;
      ctx.save();
      ctx.beginPath();
      ctx.setLineDash([4, 4]);
      ctx.moveTo(x, chartArea.top);
      ctx.lineTo(x, chartArea.bottom);
      ctx.lineWidth = 1;
      ctx.strokeStyle = css("--text-3");
      ctx.stroke();
      ctx.restore();
    },
  };
  Chart.register(crosshair);

  function gradient(ctx, area, color, top = 0.22) {
    if (!area) return alpha(color, top / 2);
    const g = ctx.createLinearGradient(0, area.top, 0, area.bottom);
    g.addColorStop(0, alpha(color, top));
    g.addColorStop(1, alpha(color, 0));
    return g;
  }

  /* ------------------------------------------------------- builders */
  const builders = {
    sparkline(el, d) {
      const t = theme();
      const color = t[d.tone] || t.income;
      return new Chart(el, {
        type: "line",
        data: { labels: d.values.map((_, i) => i), datasets: [{ data: d.values, borderColor: color, borderWidth: 2, tension: 0.35, pointRadius: 0, fill: true, backgroundColor: (c) => gradient(c.chart.ctx, c.chart.chartArea, color, 0.18) }] },
        options: {
          responsive: true, maintainAspectRatio: false, animation: false,
          plugins: { tooltip: { enabled: false } }, events: [],
          scales: { x: { display: false }, y: { display: false, grace: "8%" } },
          layout: { padding: { top: 4, bottom: 0 } },
        },
      });
    },

    incomeExpense(el, d) {
      const t = theme();
      return new Chart(el, {
        type: "bar",
        data: {
          labels: d.labels,
          datasets: [
            { label: "Income", data: d.income, backgroundColor: t.income, hoverBackgroundColor: t.income, borderRadius: 4, borderSkipped: "bottom", maxBarThickness: 22, categoryPercentage: 0.62, barPercentage: 0.86 },
            { label: "Expenses", data: d.expense, backgroundColor: t.expense, hoverBackgroundColor: t.expense, borderRadius: 4, borderSkipped: "bottom", maxBarThickness: 22, categoryPercentage: 0.62, barPercentage: 0.86 },
          ],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          scales: axes(t),
          plugins: { tooltip: moneyTooltip(0) },
        },
      });
    },

    donut(el, d) {
      const t = theme();
      return new Chart(el, {
        type: "doughnut",
        data: { labels: d.labels, datasets: [{ data: d.values, backgroundColor: d.colors, borderColor: t.surface, borderWidth: 2, hoverOffset: 6, borderRadius: 4, spacing: 1 }] },
        options: {
          responsive: true, maintainAspectRatio: false, cutout: "74%",
          layout: { padding: 6 },
          plugins: {
            tooltip: {
              callbacks: {
                label: (c) => {
                  const total = c.dataset.data.reduce((a, b) => a + b, 0) || 1;
                  return ` ${c.label}: ${fmt(c.parsed)} (${((c.parsed / total) * 100).toFixed(1)}%)`;
                },
              },
            },
          },
        },
      });
    },

    trend(el, d) {
      const t = theme();
      return new Chart(el, {
        type: "line",
        data: {
          labels: d.labels,
          datasets: [
            { label: d.currentLabel || "This period", data: d.current, borderColor: t.expense, borderWidth: 2, tension: 0.3, pointRadius: 0, pointHoverRadius: 5, pointHoverBorderWidth: 2, pointHoverBorderColor: t.surface, pointHoverBackgroundColor: t.expense, fill: true, backgroundColor: (c) => gradient(c.chart.ctx, c.chart.chartArea, t.expense, 0.16), spanGaps: false },
            { label: d.previousLabel || "Previous period", data: d.previous, borderColor: t.text3, borderWidth: 2, borderDash: [5, 5], tension: 0.3, pointRadius: 0, pointHoverRadius: 4, pointHoverBackgroundColor: t.text3, fill: false },
          ],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          scales: { ...axes(t), x: { ...axes(t).x, ticks: { ...axes(t).x.ticks, maxTicksLimit: 8 } } },
          plugins: { tooltip: moneyTooltip(0) },
        },
      });
    },

    expenseAvg(el, d) {
      const t = theme();
      return new Chart(el, {
        type: "line",
        data: {
          labels: d.labels,
          datasets: [
            { label: "Monthly spend", data: d.expense, borderColor: t.expense, borderWidth: 2, tension: 0.3, pointRadius: 4, pointBackgroundColor: t.expense, pointBorderColor: t.surface, pointBorderWidth: 2, pointHoverRadius: 6, fill: true, backgroundColor: (c) => gradient(c.chart.ctx, c.chart.chartArea, t.expense, 0.14) },
            { label: "3-month average", data: d.avg, borderColor: t.text3, borderWidth: 2, borderDash: [5, 5], tension: 0.3, pointRadius: 0, pointHoverRadius: 4, fill: false },
          ],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          scales: axes(t),
          plugins: { tooltip: moneyTooltip(0) },
        },
      });
    },

    savings(el, d) {
      const t = theme();
      const colors = d.savings.map((v) => (v >= 0 ? t.savings : t.neg));
      return new Chart(el, {
        type: "bar",
        data: { labels: d.labels, datasets: [{ label: "Net savings", data: d.savings, backgroundColor: colors, hoverBackgroundColor: colors, borderRadius: 4, borderSkipped: "start", maxBarThickness: 28 }] },
        options: {
          responsive: true, maintainAspectRatio: false,
          scales: { ...axes(t), y: { ...axes(t).y, beginAtZero: true } },
          plugins: {
            tooltip: {
              callbacks: {
                label: (c) => ` Net savings: ${fmt(c.parsed.y)}`,
                afterLabel: (c) => (d.rates[c.dataIndex] == null ? "" : ` Savings rate: ${d.rates[c.dataIndex]}%`),
              },
            },
          },
        },
      });
    },

    budgetVsActual(el, d) {
      const t = theme();
      const actualColors = d.actual.map((v, i) => (v > d.budget[i] ? t.neg : t.income));
      return new Chart(el, {
        type: "bar",
        data: {
          labels: d.labels,
          datasets: [
            { label: "Budget", data: d.budget, backgroundColor: t.muted, hoverBackgroundColor: t.muted, borderRadius: 4, borderSkipped: "start", barPercentage: 0.9, categoryPercentage: 0.7, maxBarThickness: 16 },
            { label: "Spent", data: d.actual, backgroundColor: actualColors, hoverBackgroundColor: actualColors, borderRadius: 4, borderSkipped: "start", barPercentage: 0.9, categoryPercentage: 0.7, maxBarThickness: 16 },
          ],
        },
        options: {
          indexAxis: "y", responsive: true, maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          scales: {
            x: { beginAtZero: true, border: { display: false }, grid: { color: t.grid, drawTicks: false }, ticks: moneyTicks },
            y: { grid: { display: false }, border: { display: false }, ticks: { color: t.text2, padding: 6 } },
          },
          plugins: {
            tooltip: {
              callbacks: {
                label: (c) => ` ${c.dataset.label}: ${fmt(c.parsed.x)}`,
                afterBody: (items) => {
                  const i = items[0].dataIndex;
                  const pct = d.budget[i] ? Math.round((d.actual[i] / d.budget[i]) * 100) : 0;
                  return `${pct}% of budget used`;
                },
              },
            },
          },
        },
      });
    },
  };

  function mount(el) {
    const kind = el.dataset.chart;
    const src = document.getElementById(el.dataset.source);
    const data = src ? JSON.parse(src.textContent) : JSON.parse(el.dataset.values || "{}");
    if (el.dataset.tone) data.tone = el.dataset.tone;
    if (!builders[kind]) return;
    const chart = builders[kind](el, data);
    registry.push({ el, chart, kind, data });
  }

  function mountAll() {
    applyDefaults();
    document.querySelectorAll("canvas[data-chart]").forEach(mount);
  }

  // Rebuild on theme change so colours follow tokens.
  document.addEventListener("themechange", () => {
    applyDefaults();
    registry.splice(0).forEach(({ el, chart }) => { chart.destroy(); mount(el); });
  });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mountAll);
  else mountAll();
})();
