export type Period = "month" | "quarter" | "year";
export type SortBy = "date" | "amount" | "merchant" | "category" | "provider" | "description";
export type SortDir = "asc" | "desc";

export interface Filters {
  startDate: string;
  endDate: string;
  activeRange: string;
  categories: string[];
  merchant: string;
  provider: string;
  merchantRegex: boolean;
  includeHouse: boolean;
  minAmount: string;
  maxAmount: string;
  period: Period;
  sortBy: SortBy;
  sortDir: SortDir;
  page: number;
  pageSize: number;
}

export interface Metadata {
  categories: string[];
  providers: string[];
  merchants: { merchant: string; categories: string[] }[];
}

export interface Overview {
  transactions: number;
  total: number;
  average: number;
  first_date?: string | null;
  last_date?: string | null;
}

export interface CategorySummary {
  category: string;
  total: number;
  transactions: number;
}

export interface MerchantSummary {
  merchant: string;
  total: number;
  transactions: number;
}

export interface PeriodSummary {
  period: string;
  total: number;
  transactions: number;
}

export interface Transaction {
  date: string;
  description?: string;
  merchant?: string;
  amount: number;
  category?: string | null;
  provider?: string | null;
}

export interface DashboardData {
  overview: Overview;
  categories: CategorySummary[];
  periods: PeriodSummary[];
  merchants: MerchantSummary[];
  allTimeCategories: CategorySummary[];
  transactions: Transaction[];
}

export interface AssistantStatus {
  provider: string;
  baseUrl: string;
  model: string;
  apiKeyPresent: boolean;
}

export interface AssistantMetricCard {
  kind: "metric";
  label: string;
  value: string;
  detail: string;
  tone?: "default" | "warning";
}

export interface AssistantComparisonCard {
  kind: "comparison";
  title: string;
  detail?: string;
  leftLabel: string;
  leftValue: string;
  leftDetail?: string;
  rightLabel: string;
  rightValue: string;
  rightDetail?: string;
  deltaLabel?: string;
  deltaValue?: string;
  trend: "up" | "down" | "flat";
}

export interface AssistantListItem {
  label: string;
  value?: string;
  detail?: string;
}

export interface AssistantListCard {
  kind: "list";
  title: string;
  detail?: string;
  items: AssistantListItem[];
}

export interface AssistantChipCard {
  kind: "chips";
  title: string;
  detail?: string;
  chips: string[];
}

export type AssistantCard = AssistantMetricCard | AssistantComparisonCard | AssistantListCard | AssistantChipCard;

export interface AssistantDataUse {
  tool: string;
  arguments: Record<string, unknown>;
  result: Record<string, unknown>;
}

export interface AssistantTable {
  title: string;
  note?: string;
  columns: string[];
  rows: Record<string, string | number | boolean | null | undefined>[];
}

export interface AssistantResponse {
  answer: string;
  summary?: string;
  bullets?: string[];
  followup?: string;
  cards: AssistantCard[];
  tables: AssistantTable[];
  dataUsed: AssistantDataUse[];
}
