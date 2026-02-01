const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

const state = {
  page: 1,
  pageSize: 50,
  lastQueryKey: "",
  activeRange: "",
  activeCategory: "",
  charts: {
    period: [],
    categoryAllTime: [],
    categories: [],
    merchants: [],
  },
};

const els = {
  startDate: document.getElementById("start-date"),
  endDate: document.getElementById("end-date"),
  dateRange: document.getElementById("date-range"),
  category: document.getElementById("category-select"),
  merchant: document.getElementById("merchant-input"),
  provider: document.getElementById("provider-select"),
  minAmount: document.getElementById("min-amount"),
  maxAmount: document.getElementById("max-amount"),
  merchantRegex: document.getElementById("merchant-regex"),
  includeHouse: document.getElementById("include-house"),
  period: document.getElementById("period-select"),
  sortBy: document.getElementById("sort-by"),
  sortDir: document.getElementById("sort-dir"),
  reset: document.getElementById("reset-filters"),
  refresh: document.getElementById("refresh-all"),
  pageSize: document.getElementById("page-size"),
  pagePrev: document.getElementById("page-prev"),
  pageNext: document.getElementById("page-next"),
  pageStatus: document.getElementById("page-status"),
  tableHead: document.querySelector("table thead"),
  toggleAdvanced: document.getElementById("toggle-advanced"),
  advancedFilters: document.getElementById("advanced-filters"),
  expandAll: document.getElementById("expand-all"),
  collapseAll: document.getElementById("collapse-all"),
  totalSpend: document.getElementById("total-spend"),
  spendPeriod: document.getElementById("spend-period"),
  txCount: document.getElementById("tx-count"),
  txAverage: document.getElementById("tx-average"),
  topCategory: document.getElementById("top-category"),
  topCategoryTotal: document.getElementById("top-category-total"),
  topMerchant: document.getElementById("top-merchant"),
  topMerchantTotal: document.getElementById("top-merchant-total"),
  periodLabel: document.getElementById("period-label"),
  periodChart: document.getElementById("period-chart"),
  categoryAllTimeChart: document.getElementById("category-alltime-chart"),
  categoryChart: document.getElementById("category-chart"),
  txTotal: document.getElementById("tx-total"),
  table: document.getElementById("tx-table"),
  tooltip: document.getElementById("tooltip"),
  lastSync: document.getElementById("last-sync"),
};

function formatCurrency(value) {
  return currency.format(value || 0);
}

function fetchJSON(url) {
  return fetch(url).then((res) => {
    if (!res.ok) {
      throw new Error(`Request failed: ${res.status}`);
    }
    return res.json();
  });
}

function buildParams({ includeCategory = true, includeMerchant = true, includeAmounts = true } = {}) {
  const params = new URLSearchParams();
  if (els.startDate.value) params.set("start_date", els.startDate.value);
  if (els.endDate.value) params.set("end_date", els.endDate.value);
  if (includeCategory && state.activeCategory) params.set("category", state.activeCategory);
  const selectedCategory = (state.activeCategory || "").trim().toLowerCase();
  if (!els.includeHouse.checked && selectedCategory !== "house") {
    params.set("exclude_category", "house");
  }
  if (els.provider && els.provider.value) {
    params.set("provider", els.provider.value);
  }
  if (includeMerchant && els.merchant.value) {
    if (els.merchantRegex.checked) {
      params.set("merchant_regex", els.merchant.value);
    } else {
      params.set("merchant", els.merchant.value);
    }
  }
  if (includeAmounts && els.minAmount.value) params.set("min_amount", els.minAmount.value);
  if (includeAmounts && els.maxAmount.value) params.set("max_amount", els.maxAmount.value);
  return params;
}

function queryKey() {
  return [
    els.startDate.value,
    els.endDate.value,
    state.activeCategory,
    els.merchant.value,
    els.provider?.value,
    els.merchantRegex.checked,
    els.includeHouse.checked,
    els.minAmount.value,
    els.maxAmount.value,
    els.period.value,
    els.sortBy.value,
    els.sortDir.value,
  ].join("|");
}

function setLastSync() {
  const now = new Date();
  els.lastSync.textContent = now.toLocaleString();
}

function formatDateInput(value) {
  return value.toISOString().slice(0, 10);
}

function subtractMonths(date, months) {
  const result = new Date(date);
  const day = result.getDate();
  result.setDate(1);
  result.setMonth(result.getMonth() - months);
  const lastDay = new Date(result.getFullYear(), result.getMonth() + 1, 0).getDate();
  result.setDate(Math.min(day, lastDay));
  return result;
}

function applyDateRange(value) {
  if (!value) {
    return;
  }
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  let start = null;
  let end = new Date(today);

  switch (value) {
    case "last_week":
      start = new Date(today);
      start.setDate(start.getDate() - 7);
      break;
    case "current_month":
      start = new Date(today.getFullYear(), today.getMonth(), 1);
      break;
    case "last_1m":
      start = subtractMonths(today, 1);
      break;
    case "last_3m":
      start = subtractMonths(today, 3);
      break;
    case "last_6m":
      start = subtractMonths(today, 6);
      break;
    case "last_1y":
      start = subtractMonths(today, 12);
      break;
    case "ytd":
      start = new Date(today.getFullYear(), 0, 1);
      break;
    case "all_time":
      els.startDate.value = "";
      els.endDate.value = "";
      return;
    default:
      if (value.startsWith("month_")) {
        const parts = value.split("_");
        if (parts.length !== 3) {
          return;
        }
        const year = parseInt(parts[1], 10);
        const month = parseInt(parts[2], 10);
        if (Number.isNaN(year) || Number.isNaN(month)) {
          return;
        }
        start = new Date(year, month - 1, 1);
        end = new Date(year, month, 0);
        break;
      }
      return;
  }

  els.startDate.value = formatDateInput(start);
  els.endDate.value = formatDateInput(end);
}

function debounce(fn, delay) {
  let timeoutId = null;
  return (...args) => {
    if (timeoutId) {
      window.clearTimeout(timeoutId);
    }
    timeoutId = window.setTimeout(() => {
      timeoutId = null;
      fn(...args);
    }, delay);
  };
}

function resetFilters() {
  els.startDate.value = "";
  els.endDate.value = "";
  setActiveRange("");
  setActiveCategory("");
  els.merchant.value = "";
  if (els.provider) {
    els.provider.value = "";
  }
  els.merchantRegex.checked = false;
  els.includeHouse.checked = false;
  els.minAmount.value = "";
  els.maxAmount.value = "";
  els.period.value = "month";
  els.sortBy.value = "amount";
  els.sortDir.value = "desc";
  state.page = 1;
  state.pageSize = parseInt(els.pageSize?.value || "50", 10);
}

function setActiveRange(value) {
  state.activeRange = value;
  if (!els.dateRange) {
    return;
  }
  els.dateRange.querySelectorAll(".range-button").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.range === value);
  });
}

function setActiveCategory(value) {
  state.activeCategory = value;
  if (!els.category) {
    return;
  }
  els.category.querySelectorAll(".range-button").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.range === value);
  });
}

function populateCategories(categories) {
  if (!els.category) {
    return;
  }
  const target = els.category.querySelector(".range-group__buttons");
  if (!target) {
    return;
  }
  const allButton = document.createElement("button");
  allButton.type = "button";
  allButton.className = "range-button";
  allButton.dataset.range = "";
  allButton.textContent = "All categories";
  target.appendChild(allButton);

  categories.forEach((cat) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "range-button";
    button.dataset.range = cat;
    button.textContent = cat;
    target.appendChild(button);
  });
  setActiveCategory("");
}

function populateProviders(providers) {
  if (!els.provider) {
    return;
  }
  els.provider.innerHTML = "<option value=\"\">All providers</option>";
  providers.forEach((provider) => {
    const option = document.createElement("option");
    option.value = provider;
    option.textContent = provider;
    els.provider.appendChild(option);
  });
  els.provider.value = "";
}

function updateSummary(overview, categories, merchants) {
  els.totalSpend.textContent = formatCurrency(overview.total);
  els.txCount.textContent = overview.transactions;
  els.txAverage.textContent = `Avg ${formatCurrency(overview.average)}`;

  if (overview.first_date && overview.last_date) {
    els.spendPeriod.textContent = `${overview.first_date} to ${overview.last_date}`;
  } else {
    els.spendPeriod.textContent = "No range selected";
  }

  if (state.activeCategory) {
    els.topCategory.textContent = state.activeCategory;
    els.topCategoryTotal.textContent = formatCurrency(overview.total);
  } else {
    const topCategory = categories[0];
    if (topCategory) {
      els.topCategory.textContent = topCategory.category;
      els.topCategoryTotal.textContent = formatCurrency(topCategory.total);
    } else {
      els.topCategory.textContent = "-";
      els.topCategoryTotal.textContent = formatCurrency(0);
    }
  }

  const topMerchant = merchants[0];
  if (topMerchant) {
    els.topMerchant.textContent = topMerchant.merchant;
    els.topMerchantTotal.textContent = formatCurrency(topMerchant.total);
  } else {
    els.topMerchant.textContent = "-";
    els.topMerchantTotal.textContent = formatCurrency(0);
  }
}

function renderTable(rows, append = false) {
  if (!append) {
    els.table.innerHTML = "";
  }
  const startIndex = append ? els.table.children.length : (state.page - 1) * state.pageSize;
  rows.forEach((row, idx) => {
    const tr = document.createElement("tr");
    const rowNumber = startIndex + idx + 1;
    tr.innerHTML = `
      <td class="right">${rowNumber}</td>
      <td>${row.date}</td>
      <td>${row.merchant || ""}</td>
      <td>${row.description || ""}</td>
      <td>${row.category || "uncategorized"}</td>
      <td>${row.provider || ""}</td>
      <td class="right">${formatCurrency(row.amount)}</td>
    `;
    els.table.appendChild(tr);
  });
}

function fitCanvas(canvas) {
  const scale = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * scale;
  canvas.height = rect.height * scale;
  return scale;
}

function drawBarChart(canvas, data, options = {}) {
  const ctx = canvas.getContext("2d");
  const scale = fitCanvas(canvas);
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
  ctx.clearRect(0, 0, canvas.width / scale, canvas.height / scale);

  const paddingX = 36;
  const paddingTop = 28;
  const paddingBottom = 68;
  const labelOffset = 32;
  const width = canvas.width / scale - paddingX * 2;
  const height = canvas.height / scale - paddingTop - paddingBottom;
  const maxValue = Math.max(...data.map((d) => d.value), 1);
  const barWidth = width / Math.max(data.length, 1);
  const bars = [];

  ctx.fillStyle = options.barColor || "#2c7a7b";
  ctx.strokeStyle = "#1d1a1a";
  ctx.lineWidth = 1;

  data.forEach((item, index) => {
    const barHeight = (item.value / maxValue) * height;
    const x = paddingX + index * barWidth + barWidth * 0.15;
    const y = paddingTop + height - barHeight;
    const w = barWidth * 0.7;
    ctx.fillStyle = options.barColor || "#2c7a7b";
    ctx.fillRect(x, y, w, barHeight);
    bars.push({ x, y, w, h: barHeight, label: item.label, value: item.value });
  });

  ctx.fillStyle = "#595257";
  ctx.font = "12px Avenir Next, Trebuchet MS, Gill Sans, sans-serif";
  data.forEach((item, index) => {
    const x = paddingX + index * barWidth + barWidth * 0.5;
    ctx.save();
    ctx.translate(x, paddingTop + height + labelOffset);
    ctx.rotate(-0.4);
    ctx.textAlign = "right";
    ctx.fillText(item.label, 0, 0);
    ctx.restore();
  });

  canvas._bars = bars;
}

function drawLineChart(canvas, data, options = {}) {
  const ctx = canvas.getContext("2d");
  const scale = fitCanvas(canvas);
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
  ctx.clearRect(0, 0, canvas.width / scale, canvas.height / scale);

  const paddingLeft = 52;
  const paddingRight = 24;
  const paddingTop = 28;
  const paddingBottom = 58;
  const labelOffset = 26;
  const width = canvas.width / scale - paddingLeft - paddingRight;
  const height = canvas.height / scale - paddingTop - paddingBottom;
  const values = data.map((d) => d.value);
  const minValue = Math.min(...values, 0);
  const maxValue = Math.max(...values, 0);
  const range = maxValue - minValue || 1;
  const yTicks = 4;
  const roughStep = range / yTicks;
  const niceStep = (() => {
    const magnitude = Math.pow(10, Math.floor(Math.log10(roughStep || 1)));
    const normalized = roughStep / magnitude;
    if (normalized <= 1) return 1 * magnitude;
    if (normalized <= 2) return 2 * magnitude;
    if (normalized <= 5) return 5 * magnitude;
    return 10 * magnitude;
  })();
  const niceMin = Math.floor(minValue / niceStep) * niceStep;
  const niceMax = Math.ceil(maxValue / niceStep) * niceStep;
  const niceRange = niceMax - niceMin || 1;
  const tickCount = Math.max(1, Math.round(niceRange / niceStep));

  ctx.strokeStyle = "rgba(29, 26, 26, 0.12)";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#595257";
  ctx.font = "11px Avenir Next, Trebuchet MS, Gill Sans, sans-serif";
  for (let i = 0; i <= tickCount; i += 1) {
    const value = niceMin + niceStep * i;
    const y = paddingTop + height - ((value - niceMin) / niceRange) * height;
    ctx.beginPath();
    ctx.moveTo(paddingLeft, y);
    ctx.lineTo(paddingLeft + width, y);
    ctx.stroke();
    ctx.textAlign = "right";
    ctx.fillText(formatCurrency(Math.round(value)), paddingLeft - 8, y + 4);
  }

  ctx.strokeStyle = "#1d1a1a";
  ctx.beginPath();
  ctx.moveTo(paddingLeft, paddingTop);
  ctx.lineTo(paddingLeft, paddingTop + height);
  ctx.lineTo(paddingLeft + width, paddingTop + height);
  ctx.stroke();

  if (niceMin < 0 && niceMax > 0) {
    const zeroY = paddingTop + height - ((0 - niceMin) / niceRange) * height;
    ctx.strokeStyle = "rgba(29, 26, 26, 0.35)";
    ctx.beginPath();
    ctx.moveTo(paddingLeft, zeroY);
    ctx.lineTo(paddingLeft + width, zeroY);
    ctx.stroke();
  }

  ctx.strokeStyle = options.lineColor || "#d96d47";
  ctx.lineWidth = 2;
  ctx.beginPath();
  data.forEach((item, index) => {
    const x = paddingLeft + (index / Math.max(data.length - 1, 1)) * width;
    const y = paddingTop + height - ((item.value - niceMin) / niceRange) * height;
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  const points = [];
  ctx.fillStyle = options.lineColor || "#d96d47";
  data.forEach((item, index) => {
    const x = paddingLeft + (index / Math.max(data.length - 1, 1)) * width;
    const y = paddingTop + height - ((item.value - niceMin) / niceRange) * height;
    ctx.beginPath();
    ctx.arc(x, y, 3.5, 0, Math.PI * 2);
    ctx.fill();
    points.push({ x, y, r: 6, label: item.label, value: item.value });
  });

  data.forEach((item, index) => {
    const x = paddingLeft + (index / Math.max(data.length - 1, 1)) * width;
    if (data.length > 10 && index % 2 !== 0) {
      return;
    }
    ctx.save();
    ctx.translate(x, paddingTop + height + labelOffset);
    ctx.rotate(-0.4);
    ctx.textAlign = "right";
    ctx.fillText(item.label, 0, 0);
    ctx.restore();
  });

  canvas._points = points;
}

function attachTooltip(canvas) {
  canvas.addEventListener("mousemove", (event) => {
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const bars = canvas._bars || [];
    const points = canvas._points || [];
    const hit = bars.find((bar) => x >= bar.x && x <= bar.x + bar.w && y >= bar.y && y <= bar.y + bar.h);
    const point = points.find((pt) => {
      const dx = x - pt.x;
      const dy = y - pt.y;
      return Math.sqrt(dx * dx + dy * dy) <= pt.r;
    });
    const target = hit || point;
    if (target) {
      els.tooltip.textContent = `${target.label}: ${formatCurrency(target.value)}`;
      els.tooltip.style.left = `${event.clientX}px`;
      els.tooltip.style.top = `${event.clientY}px`;
      els.tooltip.classList.add("is-visible");
    } else {
      els.tooltip.classList.remove("is-visible");
    }
  });
  canvas.addEventListener("mouseleave", () => {
    els.tooltip.classList.remove("is-visible");
  });
}

function updateCharts() {
  const periodData = state.charts.period.map((item) => ({
    label: item.period,
    value: item.total,
  }));
  const categoryAllTimeData = state.charts.categoryAllTime.slice(0, 10).map((item) => ({
    label: item.category,
    value: item.total,
  }));
  const categoryData = state.charts.categories.slice(0, 8).map((item) => ({
    label: item.category,
    value: item.total,
  }));
  drawLineChart(els.periodChart, periodData, { lineColor: "#d96d47" });
  if (els.categoryAllTimeChart) {
    drawBarChart(els.categoryAllTimeChart, categoryAllTimeData, { barColor: "#2f5f61" });
  }
  drawBarChart(els.categoryChart, categoryData, { barColor: "#2c7a7b" });
}

function updateReveal() {
  document.querySelectorAll(".reveal").forEach((el, idx) => {
    setTimeout(() => {
      el.classList.add("is-visible");
    }, 120 + idx * 80);
  });
}

function updateSortIndicators() {
  if (!els.tableHead) {
    return;
  }
  const headers = els.tableHead.querySelectorAll("th[data-sort]");
  headers.forEach((th) => {
    const isActive = th.dataset.sort === els.sortBy.value;
    if (isActive) {
      th.dataset.sortActive = "true";
      th.dataset.sortDir = els.sortDir.value;
    } else {
      th.dataset.sortActive = "false";
      th.removeAttribute("data-sort-dir");
    }
  });
}

function refreshTransactions(append = false) {
  const params = buildParams();
  params.set("sort_by", els.sortBy.value);
  params.set("sort_dir", els.sortDir.value);
  params.set("limit", state.pageSize);
  params.set("offset", (state.page - 1) * state.pageSize);
  return fetchJSON(`/api/transactions?${params}`).then((rows) => {
    renderTable(rows, append);
    return rows.length;
  });
}

function refreshAll(resetOffset = true) {
  if (resetOffset) {
    state.page = 1;
  }

  const baseParams = buildParams();
  const periodParams = buildParams({ includeCategory: true, includeMerchant: true, includeAmounts: true });
  periodParams.set("period", els.period.value);

  const categoryParams = buildParams({ includeCategory: true, includeMerchant: true, includeAmounts: true });

  const key = queryKey();
  const changed = key !== state.lastQueryKey;
  state.lastQueryKey = key;
  if (changed) {
    state.page = 1;
  }

  const periodText = els.period.options[els.period.selectedIndex].text;
  const categoryText = state.activeCategory ? state.activeCategory : "All categories";
  els.periodLabel.textContent = `${periodText} view · ${categoryText}`;
  updateSortIndicators();

  const overviewPromise = fetchJSON(`/api/overview?${baseParams}`);
  const categoryPromise = fetchJSON(`/api/summary/category?${categoryParams}`);
  const periodPromise = fetchJSON(`/api/summary/period?${periodParams}`);
  const merchantPromise = fetchJSON(`/api/summary/merchant?${categoryParams}`);
  const allTimeCategoryParams = new URLSearchParams();
  if (!els.includeHouse.checked) {
    allTimeCategoryParams.set("exclude_category", "house");
  }
  const allTimeCategoryPromise = fetchJSON(`/api/summary/category?${allTimeCategoryParams}`);
  return Promise.all([overviewPromise, categoryPromise, periodPromise, merchantPromise, allTimeCategoryPromise])
    .then(([overview, categories, period, merchants, allTimeCategories]) => {
      state.charts.categories = categories;
      state.charts.period = period;
      state.charts.categoryAllTime = allTimeCategories;
      updateSummary(overview, categories, merchants);
      if (els.txTotal) {
        els.txTotal.textContent = `Transactions: ${overview.transactions}`;
      }
      if (els.pageStatus) {
        const totalPages = Math.max(1, Math.ceil(overview.transactions / state.pageSize));
        els.pageStatus.textContent = `Page ${state.page} of ${totalPages}`;
        if (els.pagePrev) {
          els.pagePrev.disabled = state.page <= 1;
        }
        if (els.pageNext) {
          els.pageNext.disabled = state.page >= totalPages;
        }
      }
      updateCharts();
      return refreshTransactions(false);
    })
    .then(() => {
      setLastSync();
    })
    .catch((err) => {
      console.error(err);
    });
}

function loadMetadata() {
  return fetchJSON("/api/metadata").then((data) => {
    populateCategories(data.categories || []);
    populateProviders(data.providers || []);
  });
}

function populateDateRanges() {
  const container = els.dateRange;
  if (!container) {
    return;
  }
  const quickTarget = container.querySelector("[data-range-section=\"quick\"] .range-group__buttons");
  const monthsTarget = container.querySelector("[data-range-section=\"months\"] .range-group__buttons");
  if (!quickTarget || !monthsTarget) {
    return;
  }

  const quickRanges = [
    { value: "last_week", label: "Last week" },
    { value: "current_month", label: "Current month" },
    { value: "last_1m", label: "1 mo" },
    { value: "last_3m", label: "3 mo" },
    { value: "last_6m", label: "6 mo" },
    { value: "last_1y", label: "1 yr" },
    { value: "ytd", label: "YTD" },
    { value: "all_time", label: "All time" },
  ];
  quickRanges.forEach((range) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "range-button";
    button.dataset.range = range.value;
    button.textContent = range.label;
    quickTarget.appendChild(button);
  });

  const monthLabels = new Intl.DateTimeFormat("en-US", { month: "short", year: "numeric" });
  const anchor = new Date();
  anchor.setDate(1);

  for (let offset = 0; offset < 12; offset += 1) {
    const monthDate = new Date(anchor.getFullYear(), anchor.getMonth() - offset, 1);
    const year = monthDate.getFullYear();
    const month = String(monthDate.getMonth() + 1).padStart(2, "0");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "range-button range-button--month";
    button.dataset.range = `month_${year}_${month}`;
    button.textContent = monthLabels.format(monthDate);
    monthsTarget.appendChild(button);
  }
}

function init() {
  attachTooltip(els.periodChart);
  attachTooltip(els.categoryAllTimeChart);
  attachTooltip(els.categoryChart);

  els.reset.addEventListener("click", () => {
    resetFilters();
    refreshAll(true);
  });
  els.refresh.addEventListener("click", () => refreshAll(false));
  if (els.pageSize) {
    els.pageSize.addEventListener("change", () => {
      state.pageSize = parseInt(els.pageSize.value, 10);
      state.page = 1;
      refreshAll(true);
    });
  }
  if (els.pagePrev) {
    els.pagePrev.addEventListener("click", () => {
      state.page = Math.max(1, state.page - 1);
      refreshAll(false);
    });
  }
  if (els.pageNext) {
    els.pageNext.addEventListener("click", () => {
      state.page += 1;
      refreshAll(false);
    });
  }

  if (els.toggleAdvanced && els.advancedFilters) {
    els.toggleAdvanced.addEventListener("click", () => {
      const isOpen = els.advancedFilters.classList.toggle("is-open");
      els.toggleAdvanced.setAttribute("aria-expanded", String(isOpen));
      els.toggleAdvanced.textContent = isOpen ? "Hide advanced" : "Advanced filters";
    });
  }

  if (els.tableHead) {
    els.tableHead.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      const sortKey = target.dataset.sort;
      if (!sortKey) {
        return;
      }
      if (els.sortBy.value === sortKey) {
        els.sortDir.value = els.sortDir.value === "asc" ? "desc" : "asc";
      } else {
        els.sortBy.value = sortKey;
        els.sortDir.value = "desc";
      }
      updateSortIndicators();
      refreshAll(true);
    });
  }

  if (els.category) {
    els.category.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      if (!target.classList.contains("range-button")) {
        return;
      }
      const value = target.dataset.range || "";
      setActiveCategory(value);
      refreshAll(true);
    });
  }

  const chartButtons = () => document.querySelectorAll(".chart-expand");
  const chartCards = () => document.querySelectorAll(".chart-card");

  const setAllChartsExpanded = (expanded) => {
    chartCards().forEach((card) => {
      card.classList.toggle("is-expanded", expanded);
      const control = card.querySelector(".chart-expand");
      if (control) {
        control.textContent = expanded ? "Collapse" : "Expand";
      }
    });
    window.setTimeout(() => updateCharts(), 50);
  };

  chartButtons().forEach((button) => {
    button.addEventListener("click", () => {
      const card = button.closest(".chart-card");
      if (!card) {
        return;
      }
      const isExpanded = card.classList.contains("is-expanded");
      if (!isExpanded) {
        card.classList.add("is-expanded");
        button.textContent = "Collapse";
      } else {
        card.classList.remove("is-expanded");
        button.textContent = "Expand";
      }
      window.setTimeout(() => updateCharts(), 50);
    });
  });

  if (els.expandAll) {
    els.expandAll.addEventListener("click", () => {
      setAllChartsExpanded(true);
    });
  }
  if (els.collapseAll) {
    els.collapseAll.addEventListener("click", () => {
      setAllChartsExpanded(false);
    });
  }

  const scheduleRefresh = debounce(() => refreshAll(true), 250);
  const immediateInputs = [
    els.startDate,
    els.endDate,
    els.merchantRegex,
    els.includeHouse,
    els.provider,
    els.period,
    els.sortBy,
    els.sortDir,
  ];
  immediateInputs.forEach((el) => {
    el.addEventListener("change", () => refreshAll(true));
  });

  const textInputs = [els.merchant, els.minAmount, els.maxAmount];
  textInputs.forEach((el) => {
    el.addEventListener("input", () => scheduleRefresh());
  });

  if (els.dateRange) {
    els.dateRange.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      if (!target.classList.contains("range-button")) {
        return;
      }
      const rangeValue = target.dataset.range || "";
      setActiveRange(rangeValue);
      applyDateRange(rangeValue);
      refreshAll(true);
    });
  }
  [els.startDate, els.endDate].forEach((el) => {
    el.addEventListener("change", () => {
      if (state.activeRange) {
        setActiveRange("");
      }
    });
  });

  window.addEventListener("resize", () => updateCharts());

  loadMetadata().then(() => {
    resetFilters();
    populateDateRanges();
    setActiveRange("last_1y");
    applyDateRange("last_1y");
    setActiveCategory("");
    updateReveal();
    updateSortIndicators();
    refreshAll(true);
  });
}

init();
