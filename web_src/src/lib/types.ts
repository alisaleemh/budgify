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

export interface AssistantResponse {
  answer: string;
  dataUsed: unknown[];
}
