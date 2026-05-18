import type { Filters } from "@/lib/types";

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

export function formatCurrency(value: number | null | undefined) {
  return currency.format(value || 0);
}

export function formatDateInput(value: Date) {
  return value.toISOString().slice(0, 10);
}

export function subtractMonths(date: Date, months: number) {
  const result = new Date(date);
  const day = result.getDate();
  result.setDate(1);
  result.setMonth(result.getMonth() - months);
  const lastDay = new Date(result.getFullYear(), result.getMonth() + 1, 0).getDate();
  result.setDate(Math.min(day, lastDay));
  return result;
}

export function formatCategorySelectionLabel(categories: Filters["categories"]) {
  if (categories.length === 0) return "All categories";
  if (categories.length <= 2) return categories.join(", ");
  return `${categories.length} categories selected`;
}
