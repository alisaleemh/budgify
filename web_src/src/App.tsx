import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, ChevronsDown, ChevronsUp } from "lucide-react";
import { AppLayout } from "@/components/AppLayout";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { AssistantPanel } from "@/components/dashboard/AssistantPanel";
import { ChartCard } from "@/components/dashboard/ChartCard";
import { FiltersPanel } from "@/components/dashboard/FiltersPanel";
import { LoadingState } from "@/components/dashboard/LoadingState";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { TopCategories } from "@/components/dashboard/TopCategories";
import { TransactionTable } from "@/components/dashboard/TransactionTable";
import { fetchDashboard, fetchMetadata } from "@/lib/api";
import { formatCategorySelectionLabel, formatCurrency, formatDateInput, subtractMonths } from "@/lib/format";
import type { DashboardData, Filters, Metadata, SortBy, SortDir } from "@/lib/types";

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

export default function App() {
  const text = useMemo(rootText, []);
  const [metadata, setMetadata] = useState<Metadata>({ categories: [], providers: [], merchants: [] });
  const [filters, setFilters] = useState<Filters>(() => ({ ...defaultFilters, ...applyDateRange("last_1y", defaultFilters) }));
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastSync, setLastSync] = useState("Ready");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [expandedCharts, setExpandedCharts] = useState<string[]>([]);

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

  const updateFilters = (patch: Partial<Filters>) => {
    setFilters((current) => ({ ...current, ...patch }));
  };

  const toggleCategory = (category: string) => {
    setFilters((current) => {
      if (!category) return { ...current, categories: [], page: 1 };
      const categories = current.categories.includes(category)
        ? current.categories.filter((item) => item !== category)
        : [...current.categories, category];
      return { ...current, categories, page: 1 };
    });
  };

  const setChartExpanded = (chart: string, expanded: boolean) => {
    setExpandedCharts((current) => (expanded ? Array.from(new Set([...current, chart])) : current.filter((item) => item !== chart)));
  };

  const overview = data?.overview;
  const topMerchant = data?.merchants[0];
  const totalPages = Math.max(1, Math.ceil((overview?.transactions || 0) / filters.pageSize));
  const periodText = filters.period === "month" ? "Monthly" : filters.period === "quarter" ? "Quarterly" : "Yearly";
  const categoryText = formatCategorySelectionLabel(filters.categories);

  return (
    <AppLayout title={text.title} eyebrow={text.eyebrow} headline={text.headline} lede={text.lede} lastSync={lastSync} loading={loading} onRefresh={() => void refresh(filters)}>
      <section id="overview" className="grid gap-4">
        <FiltersPanel
          filters={filters}
          categories={metadata.categories}
          providers={metadata.providers}
          ranges={quickRanges}
          monthRanges={monthRanges}
          advancedOpen={advancedOpen}
          onAdvancedOpenChange={setAdvancedOpen}
          onChange={updateFilters}
          onCategoryToggle={toggleCategory}
          onRangeSelect={(range) => setFilters((current) => ({ ...current, ...applyDateRange(range, current) }))}
          onReset={() => setFilters({ ...defaultFilters })}
        />

        {error ? (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Unable to load dashboard</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

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
                  <Button type="button" variant="outline" size="sm" onClick={() => setExpandedCharts(["alltime", "period", "category"])}>
                    <ChevronsDown className="h-4 w-4" />
                    Expand all
                  </Button>
                  <Button type="button" variant="outline" size="sm" onClick={() => setExpandedCharts([])}>
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

            <AssistantPanel />

            <section id="transactions">
              <TransactionTable
                rows={data?.transactions || []}
                total={overview?.transactions || 0}
                page={Math.min(filters.page, totalPages)}
                pageSize={filters.pageSize}
                sortBy={filters.sortBy}
                sortDir={filters.sortDir}
                loading={loading}
                onPageChange={(page) => updateFilters({ page })}
                onPageSizeChange={(pageSize) => updateFilters({ pageSize, page: 1 })}
                onSortChange={(sortBy: SortBy, sortDir: SortDir) => updateFilters({ sortBy, sortDir, page: 1 })}
              />
            </section>
          </>
        )}
      </section>
    </AppLayout>
  );
}
