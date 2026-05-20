import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { formatCurrency } from "@/lib/format";
import type { SortBy, SortDir, Transaction } from "@/lib/types";
import { cn } from "@/lib/utils";

const columns: { key: SortBy; label: string; className?: string }[] = [
  { key: "date", label: "Date" },
  { key: "merchant", label: "Merchant" },
  { key: "description", label: "Description" },
  { key: "category", label: "Category" },
  { key: "provider", label: "Provider" },
  { key: "amount", label: "Amount", className: "text-right" },
];

interface TransactionTableProps {
  rows: Transaction[];
  total: number;
  page: number;
  pageSize: number;
  sortBy: SortBy;
  sortDir: SortDir;
  loading: boolean;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onSortChange: (sortBy: SortBy, sortDir: SortDir) => void;
}

export function TransactionTable({
  rows,
  total,
  page,
  pageSize,
  sortBy,
  sortDir,
  loading,
  onPageChange,
  onPageSizeChange,
  onSortChange,
}: TransactionTableProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-3 space-y-0">
        <div>
          <CardTitle>Transactions</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground numeric">Transactions: {total}</p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Select value={String(pageSize)} onValueChange={(value) => onPageSizeChange(Number(value))}>
            <SelectTrigger className="w-24">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[25, 50, 100, 200].map((size) => (
                <SelectItem key={size} value={String(size)}>
                  {size}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" size="icon" onClick={() => onPageChange(Math.max(1, page - 1))} disabled={page <= 1}>
              <ChevronLeft className="h-4 w-4" />
              <span className="sr-only">Previous page</span>
            </Button>
            <span className="min-w-24 text-center text-sm text-muted-foreground numeric">
              Page {page} of {totalPages}
            </span>
            <Button type="button" variant="outline" size="icon" onClick={() => onPageChange(Math.min(totalPages, page + 1))} disabled={page >= totalPages}>
              <ChevronRight className="h-4 w-4" />
              <span className="sr-only">Next page</span>
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {loading && rows.length === 0 ? (
          <div className="grid gap-2">
            {Array.from({ length: 8 }).map((_, index) => (
              <Skeleton key={index} className="h-11 w-full" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <EmptyState title="No transactions match these filters" detail="Adjust the date range, category, merchant, provider, or amount filters." />
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <Table>
              <TableHeader className="sticky top-0 z-10 bg-zinc-100">
                <TableRow>
                  <TableHead className="w-14 text-right">#</TableHead>
                  {columns.map((column) => {
                    const active = sortBy === column.key;
                    const nextDir: SortDir = active && sortDir === "asc" ? "desc" : "asc";
                    return (
                      <TableHead key={column.key} className={cn("whitespace-nowrap", column.className)}>
                        <button
                          type="button"
                          className={cn("inline-flex items-center gap-1 font-medium", column.className === "text-right" && "justify-end")}
                          onClick={() => onSortChange(column.key, nextDir)}
                        >
                          {column.label}
                          {active ? sortDir === "asc" ? <ArrowUp className="h-3.5 w-3.5" /> : <ArrowDown className="h-3.5 w-3.5" /> : <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />}
                        </button>
                      </TableHead>
                    );
                  })}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row, index) => (
                  <TableRow key={`${row.date}-${row.merchant}-${row.amount}-${index}`}>
                    <TableCell className="text-right text-muted-foreground numeric">{(page - 1) * pageSize + index + 1}</TableCell>
                    <TableCell className="whitespace-nowrap numeric">{row.date}</TableCell>
                    <TableCell className="min-w-48 font-medium">{row.merchant || ""}</TableCell>
                    <TableCell className="min-w-64 text-muted-foreground">{row.description || ""}</TableCell>
                    <TableCell>
                      <Badge variant="secondary">{row.category || "uncategorized"}</Badge>
                    </TableCell>
                    <TableCell>
                      {row.provider ? <Badge variant="outline">{row.provider}</Badge> : null}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-right font-semibold numeric">{formatCurrency(row.amount)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
