import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, ChevronsDown, ChevronsUp } from "lucide-react";
import { AppLayout } from "@/components/AppLayout";
import { BetaHome } from "@/components/beta/BetaHome";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { AssistantPanel } from "@/components/dashboard/AssistantPanel";
import { ChartCard } from "@/components/dashboard/ChartCard";
import { FiltersPanel } from "@/components/dashboard/FiltersPanel";
import { LoadingState } from "@/components/dashboard/LoadingState";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { TopCategories } from "@/components/dashboard/TopCategories";
import { TransactionTable } from "@/components/dashboard/TransactionTable";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { fetchDashboard, fetchMetadata } from "@/lib/api";
import { useAnalytics } from "@/lib/analytics";
import { formatCategorySelectionLabel, formatCurrency, formatDateInput, subtractMonths } from "@/lib/format";
import type { DashboardData, Filters, Metadata, SortBy, SortDir, Transaction } from "@/lib/types";

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

const defaultFilters: Filters = {
  startDate: "",
  endDate: "",
  activeRange: "",
  categories: [],
  merchant: "",
  provider: "",
  merchantRegex: false,
  includeHouse: false,
  minAmount: "",
  maxAmount: "",
  period: "month",
  sortBy: "amount",
  sortDir: "desc",
  page: 1,
  pageSize: 50,
};

function rootText() {
  const root = document.getElementById("root");
  return {
    title: root?.dataset.appTitle || "Budgify",
    eyebrow: root?.dataset.appEyebrow || "Budgify Home",
    headline: root?.dataset.appHeadline || "Budgify spending dashboard",
    lede: root?.dataset.appLede || "Explore monthly trends, category mix, and top merchants for your home ledger.",
  };
}

function applyDateRange(value: string, filters: Filters): Partial<Filters> {
  if (!value) return {};
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  let start: Date | null = null;
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
      return { startDate: "", endDate: "", activeRange: value, page: 1 };
    default:
      if (value.startsWith("month_")) {
        const [, yearText, monthText] = value.split("_");
        const year = Number(yearText);
        const month = Number(monthText);
        if (!Number.isFinite(year) || !Number.isFinite(month)) return filters;
        start = new Date(year, month - 1, 1);
        end = new Date(year, month, 0);
        break;
      }
      return filters;
  }

  return { startDate: formatDateInput(start), endDate: formatDateInput(end), activeRange: value, page: 1 };
}

function transactionMeta(row: Transaction) {
  return {
    date: row.date,
    merchantLength: row.merchant?.length || 0,
    category: row.category || "uncategorized",
    provider: row.provider || "none",
    amountBucket:
      Math.abs(row.amount) < 25 ? "under_25" : Math.abs(row.amount) < 100 ? "under_100" : Math.abs(row.amount) < 250 ? "under_250" : "250_plus",
  };
}

function DashboardApp() {
  const text = useMemo(rootText, []);
  const analytics = useAnalytics("/");
  const [metadata, setMetadata] = useState<Metadata>({ categories: [], providers: [], merchants: [] });
  const [filters, setFilters] = useState<Filters>(() => ({ ...defaultFilters, ...applyDateRange("last_1y", defaultFilters) }));
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastSync, setLastSync] = useState("Ready");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [expandedCharts, setExpandedCharts] = useState<string[]>([]);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [selectedTransaction, setSelectedTransaction] = useState<Transaction | null>(null);
  const lastZeroResultTrackedRef = useRef("");

  const monthRanges = useMemo(() => {
    const monthLabels = new Intl.DateTimeFormat("en-US", { month: "short", year: "numeric" });
    const anchor = new Date();
    anchor.setDate(1);
    return Array.from({ length: 12 }, (_, offset) => {
      const monthDate = new Date(anchor.getFullYear(), anchor.getMonth() - offset, 1);
      const year = monthDate.getFullYear();
      const month = String(monthDate.getMonth() + 1).padStart(2, "0");
      return { value: `month_${year}_${month}`, label: monthLabels.format(monthDate) };
    });
  }, []);

  const refresh = useCallback(
    async (nextFilters = filters) => {
      setLoading(true);
      setError(null);
      try {
        const payload = await fetchDashboard(nextFilters);
        setData(payload);
        setLastSync(new Date().toLocaleString());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load dashboard data");
      } finally {
        setLoading(false);
      }
    },
    [filters],
  );

  useEffect(() => {
    fetchMetadata()
      .then((payload) => setMetadata(payload))
      .catch((err) => setError(err instanceof Error ? err.message : "Unable to load metadata"));
  }, []);

  useEffect(() => {
    const id = window.setTimeout(() => {
      void refresh(filters);
    }, 200);
    return () => window.clearTimeout(id);
  }, [filters, refresh]);

  useEffect(() => {
    const query = filters.merchant.trim();
    if (!query) return;
    const id = window.setTimeout(() => {
      analytics.trackSearchSubmitted(query, {
        regex: filters.merchantRegex,
        categoryCount: filters.categories.length,
        providerSelected: Boolean(filters.provider),
      });
    }, 450);
    return () => window.clearTimeout(id);
  }, [analytics, filters.categories.length, filters.merchant, filters.merchantRegex, filters.provider]);

  useEffect(() => {
    const query = filters.merchant.trim();
    if (!query) {
      lastZeroResultTrackedRef.current = "";
      return;
    }
    if ((data?.overview.transactions || 0) === 0 && query !== lastZeroResultTrackedRef.current) {
      lastZeroResultTrackedRef.current = query;
      analytics.trackSearchZeroResults(query, { regex: filters.merchantRegex, pageSize: filters.pageSize });
    }
  }, [analytics, data?.overview.transactions, filters.merchant, filters.merchantRegex, filters.pageSize]);

  const updateFilters = useCallback(
    (patch: Partial<Filters>) => {
      setFilters((current) => {
        const next = { ...current, ...patch };

        if (patch.merchant !== undefined && current.merchant && !String(next.merchant || "").trim()) {
          analytics.trackSearchAbandoned(current.merchant, { reason: "cleared" });
        }
        if (patch.sortBy !== undefined || patch.sortDir !== undefined) {
          analytics.trackSortChange(String(next.sortBy), String(next.sortDir), { pageSize: next.pageSize });
        }

        if (patch.activeRange !== undefined) {
          analytics.trackFilterChange("date_range", next.activeRange || "custom", {
            startDate: next.startDate || null,
            endDate: next.endDate || null,
          });
        }
        if (patch.startDate !== undefined) analytics.trackFilterChange("start_date", next.startDate || "");
        if (patch.endDate !== undefined) analytics.trackFilterChange("end_date", next.endDate || "");
        if (patch.provider !== undefined) analytics.trackFilterChange("provider", next.provider || "all");
        if (patch.minAmount !== undefined) analytics.trackFilterChange("min_amount", next.minAmount || "");
        if (patch.maxAmount !== undefined) analytics.trackFilterChange("max_amount", next.maxAmount || "");
        if (patch.pageSize !== undefined) analytics.trackSettingsChange("page_size", next.pageSize);
        if (patch.period !== undefined) analytics.trackSettingsChange("period", next.period);
        if (patch.merchantRegex !== undefined) analytics.trackSettingsChange("merchant_regex", next.merchantRegex);
        if (patch.includeHouse !== undefined) analytics.trackSettingsChange("include_house", next.includeHouse);

        return next;
      });
    },
    [analytics],
  );

  const toggleCategory = useCallback(
    (category: string) => {
      setFilters((current) => {
        if (!category) {
          analytics.trackCategorySelection("all", current.categories.length !== 0);
          return { ...current, categories: [], page: 1 };
        }
        const selected = current.categories.includes(category);
        analytics.trackCategorySelection(category, !selected);
        const categories = selected ? current.categories.filter((item) => item !== category) : [...current.categories, category];
        return { ...current, categories, page: 1 };
      });
    },
    [analytics],
  );

  const setChartExpanded = useCallback(
    (chart: string, expanded: boolean) => {
      setExpandedCharts((current) => (expanded ? Array.from(new Set([...current, chart])) : current.filter((item) => item !== chart)));
      analytics.trackButtonClick("ChartCard", expanded ? "expand_chart" : "collapse_chart", { chart });
    },
    [analytics],
  );

  const handleRefresh = useCallback(() => {
    analytics.trackButtonClick("AppLayout", "refresh_dashboard");
    void refresh(filters);
  }, [analytics, filters, refresh]);

  const handleNav = useCallback(
    (href: string, label: string) => {
      analytics.trackNavigation("SidebarNav", href, { label });
      if (mobileNavOpen) {
        analytics.trackModalChange("MobileNavigation", false, { sheet: true, via: "nav_link" });
        setMobileNavOpen(false);
      }
    },
    [analytics, mobileNavOpen],
  );

  const handleMobileNavOpenChange = useCallback(
    (open: boolean) => {
      setMobileNavOpen(open);
      analytics.trackModalChange("MobileNavigation", open, { sheet: true });
    },
    [analytics],
  );

  const handleAdvancedOpenChange = useCallback(
    (open: boolean) => {
      setAdvancedOpen(open);
      analytics.trackButtonClick("FiltersPanel", open ? "open_advanced" : "close_advanced");
    },
    [analytics],
  );

  const handleReset = useCallback(() => {
    analytics.trackButtonClick("FiltersPanel", "reset_filters");
    setFilters({ ...defaultFilters });
  }, [analytics]);

  const handleRangeSelect = useCallback(
    (range: string) => {
      analytics.trackFilterChange("date_range", range);
      setFilters((current) => ({ ...current, ...applyDateRange(range, current) }));
    },
    [analytics],
  );

  const handlePageChange = useCallback(
    (page: number) => {
      analytics.trackNavigation("TransactionTable", page > filters.page ? "next_page" : "previous_page", {
        fromPage: filters.page,
        toPage: page,
      });
      updateFilters({ page });
    },
    [analytics, filters.page, updateFilters],
  );

  const handlePageSizeChange = useCallback(
    (pageSize: number) => {
      updateFilters({ pageSize, page: 1 });
    },
    [updateFilters],
  );

  const handleSortChange = useCallback(
    (sortBy: SortBy, sortDir: SortDir) => {
      updateFilters({ sortBy, sortDir, page: 1 });
    },
    [updateFilters],
  );

  const handleTransactionClick = useCallback(
    (row: Transaction) => {
      analytics.trackTransactionDrilldown(transactionMeta(row));
      analytics.trackModalChange("TransactionDrilldown", true, transactionMeta(row));
      setSelectedTransaction(row);
    },
    [analytics],
  );

  const closeTransactionDialog = useCallback(() => {
    if (selectedTransaction) {
      analytics.trackModalChange("TransactionDrilldown", false, transactionMeta(selectedTransaction));
    }
    setSelectedTransaction(null);
  }, [analytics, selectedTransaction]);

  const overview = data?.overview;
  const topMerchant = data?.merchants[0];
  const totalPages = Math.max(1, Math.ceil((overview?.transactions || 0) / filters.pageSize));
  const periodText = filters.period === "month" ? "Monthly" : filters.period === "quarter" ? "Quarterly" : "Yearly";
  const categoryText = formatCategorySelectionLabel(filters.categories);

  return (
    <AppLayout
      title={text.title}
      eyebrow={text.eyebrow}
      headline={text.headline}
      lede={text.lede}
      lastSync={lastSync}
      loading={loading}
      mobileNavOpen={mobileNavOpen}
      onMobileNavOpenChange={handleMobileNavOpenChange}
      onNavigate={handleNav}
      onRefresh={handleRefresh}
    >
      <section id="overview" className="grid gap-4">
        <FiltersPanel
          filters={filters}
          categories={metadata.categories}
          providers={metadata.providers}
          ranges={quickRanges}
          monthRanges={monthRanges}
          advancedOpen={advancedOpen}
          onAdvancedOpenChange={handleAdvancedOpenChange}
          onChange={updateFilters}
          onCategoryToggle={toggleCategory}
          onRangeSelect={handleRangeSelect}
          onReset={handleReset}
        />

        {error ? (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Unable to load dashboard</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        <section id="assistant" className="grid gap-4">
          <AssistantPanel />
        </section>

        {!data && loading ? (
          <LoadingState />
        ) : (
          <>
            <div className="grid gap-4 xl:grid-cols-4">
              <TopCategories categories={data?.categories || []} />
              <MetricCard label="Total spend" value={formatCurrency(overview?.total)} detail={overview?.first_date && overview.last_date ? `${overview.first_date} to ${overview.last_date}` : "No range selected"} />
              <MetricCard label="Transactions" value={String(overview?.transactions || 0)} detail={`Avg ${formatCurrency(overview?.average)}`} />
              <MetricCard label="Top merchant" value={topMerchant?.merchant || "-"} detail={formatCurrency(topMerchant?.total)} />
            </div>

            <section id="charts" className="grid gap-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold tracking-normal">Charts</h2>
                  <p className="text-sm text-muted-foreground">
                    {periodText} view · {categoryText}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      analytics.trackButtonClick("ChartsToolbar", "expand_all_charts");
                      setExpandedCharts(["alltime", "period", "category"]);
                    }}
                  >
                    <ChevronsDown className="h-4 w-4" />
                    Expand all
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      analytics.trackButtonClick("ChartsToolbar", "collapse_all_charts");
                      setExpandedCharts([]);
                    }}
                  >
                    <ChevronsUp className="h-4 w-4" />
                    Collapse all
                  </Button>
                </div>
              </div>
              <div className="grid gap-4 xl:grid-cols-3">
                <ChartCard
                  title="All-time category spend"
                  subtitle="Static totals"
                  type="bar"
                  data={(data?.allTimeCategories || []).slice(0, 10).map((item) => ({ label: item.category || "uncategorized", value: item.total }))}
                  expanded={expandedCharts.includes("alltime")}
                  onExpandedChange={(expanded) => setChartExpanded("alltime", expanded)}
                />
                <ChartCard
                  title="Spend over time"
                  subtitle={`${periodText} view`}
                  type="line"
                  data={(data?.periods || []).map((item) => ({ label: item.period, value: item.total }))}
                  expanded={expandedCharts.includes("period")}
                  onExpandedChange={(expanded) => setChartExpanded("period", expanded)}
                />
                <ChartCard
                  title="Category mix"
                  subtitle="Top categories by total"
                  type="bar"
                  data={(data?.categories || []).slice(0, 8).map((item) => ({ label: item.category || "uncategorized", value: item.total }))}
                  expanded={expandedCharts.includes("category")}
                  onExpandedChange={(expanded) => setChartExpanded("category", expanded)}
                />
              </div>
            </section>

            <section id="transactions">
              <TransactionTable
                rows={data?.transactions || []}
                total={overview?.transactions || 0}
                page={Math.min(filters.page, totalPages)}
                pageSize={filters.pageSize}
                sortBy={filters.sortBy}
                sortDir={filters.sortDir}
                loading={loading}
                onPageChange={handlePageChange}
                onPageSizeChange={handlePageSizeChange}
                onSortChange={handleSortChange}
                onRowClick={handleTransactionClick}
              />
            </section>

          </>
        )}
      </section>

      <Dialog open={Boolean(selectedTransaction)} onOpenChange={(open) => {
        if (!open) closeTransactionDialog();
      }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Transaction detail</DialogTitle>
            <DialogDescription>{selectedTransaction?.merchant || "Transaction"}</DialogDescription>
          </DialogHeader>
          {selectedTransaction ? (
            <div className="grid gap-3 text-sm">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Date</p>
                  <p className="mt-1 font-medium">{selectedTransaction.date}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Amount</p>
                  <p className="mt-1 font-medium numeric">{formatCurrency(selectedTransaction.amount)}</p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Category</p>
                  <p className="mt-1 font-medium">{selectedTransaction.category || "uncategorized"}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Provider</p>
                  <p className="mt-1 font-medium">{selectedTransaction.provider || "-"}</p>
                </div>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Description</p>
                <p className="mt-1 text-muted-foreground">{selectedTransaction.description || "No description"}</p>
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </AppLayout>
  );
}

export default function App() {
  return window.location.pathname === "/beta" ? <BetaHome /> : <DashboardApp />;
}
