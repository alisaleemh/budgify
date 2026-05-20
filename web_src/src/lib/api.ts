import type { AssistantResponse, AssistantStatus, DashboardData, Filters, Metadata } from "@/lib/types";

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function buildParams(filters: Filters, options: { includeMerchant?: boolean; includeAmounts?: boolean } = {}) {
  const params = new URLSearchParams();
  const includeMerchant = options.includeMerchant ?? true;
  const includeAmounts = options.includeAmounts ?? true;
  if (filters.startDate) params.set("start_date", filters.startDate);
  if (filters.endDate) params.set("end_date", filters.endDate);
  if (filters.categories.length > 0) params.set("categories", filters.categories.join(","));
  const houseSelected = filters.categories.some((category) => category.trim().toLowerCase() === "house");
  if (!filters.includeHouse && !houseSelected) params.set("exclude_category", "house");
  if (filters.provider) params.set("provider", filters.provider);
  if (includeMerchant && filters.merchant) {
    params.set(filters.merchantRegex ? "merchant_regex" : "merchant", filters.merchant);
  }
  if (includeAmounts && filters.minAmount) params.set("min_amount", filters.minAmount);
  if (includeAmounts && filters.maxAmount) params.set("max_amount", filters.maxAmount);
  return params;
}

export function fetchMetadata() {
  return fetchJSON<Metadata>("/api/metadata");
}

export async function fetchDashboard(filters: Filters): Promise<DashboardData> {
  const baseParams = buildParams(filters);
  const periodParams = buildParams(filters);
  periodParams.set("period", filters.period);
  const txParams = buildParams(filters);
  txParams.set("sort_by", filters.sortBy);
  txParams.set("sort_dir", filters.sortDir);
  txParams.set("limit", String(filters.pageSize));
  txParams.set("offset", String((filters.page - 1) * filters.pageSize));
  const allTimeParams = new URLSearchParams();
  if (!filters.includeHouse) allTimeParams.set("exclude_category", "house");

  const [overview, categories, periods, merchants, allTimeCategories, transactions] = await Promise.all([
    fetchJSON<DashboardData["overview"]>(`/api/overview?${baseParams}`),
    fetchJSON<DashboardData["categories"]>(`/api/summary/category?${baseParams}`),
    fetchJSON<DashboardData["periods"]>(`/api/summary/period?${periodParams}`),
    fetchJSON<DashboardData["merchants"]>(`/api/summary/merchant?${baseParams}`),
    fetchJSON<DashboardData["allTimeCategories"]>(`/api/summary/category?${allTimeParams}`),
    fetchJSON<DashboardData["transactions"]>(`/api/transactions?${txParams}`),
  ]);

  return { overview, categories, periods, merchants, allTimeCategories, transactions };
}

export function fetchAssistantStatus() {
  return fetchJSON<AssistantStatus>("/api/assistant/status");
}

export function askAssistant(question: string) {
  return fetchJSON<AssistantResponse>("/api/assistant/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
}
