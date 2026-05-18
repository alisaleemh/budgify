import type { CategorySummary } from "@/lib/types";
import { formatCurrency } from "@/lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export function TopCategories({ categories }: { categories: CategorySummary[] }) {
  const normalized = categories.map((item) => ({
    category: item.category || "uncategorized",
    total: Number(item.total) || 0,
  }));
  const topCategories = normalized.slice(0, 5);
  const totalSpend = normalized.reduce((sum, item) => sum + item.total, 0);
  const maxTopCategory = Math.max(...topCategories.map((item) => item.total), 1);

  return (
    <Card className="xl:col-span-2">
      <CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
        <div>
          <CardTitle>Top categories</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">Share of filtered spend</p>
        </div>
        <Badge variant="outline">Top 5</Badge>
      </CardHeader>
      <CardContent>
        {topCategories.length === 0 ? (
          <p className="text-sm text-muted-foreground">No category data</p>
        ) : (
          <div className="grid gap-3">
            {topCategories.map((item, index) => {
              const relativeWidth = Math.max((item.total / maxTopCategory) * 100, 2);
              const share = totalSpend > 0 ? (item.total / totalSpend) * 100 : 0;
              return (
                <div key={`${item.category}-${index}`} className="rounded-lg border bg-zinc-50 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-2">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-primary text-xs font-semibold text-primary-foreground">{index + 1}</span>
                      <span className="truncate text-sm font-medium">{item.category}</span>
                    </div>
                    <div className="flex shrink-0 items-center gap-2 text-sm numeric">
                      <span className="font-semibold">{formatCurrency(item.total)}</span>
                      <span className="w-12 text-right text-muted-foreground">{share.toFixed(1)}%</span>
                    </div>
                  </div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-zinc-200">
                    <div className="h-full rounded-full bg-accent" style={{ width: `${relativeWidth}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
