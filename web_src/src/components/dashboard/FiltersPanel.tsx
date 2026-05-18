import { ChevronDown, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import type { Filters, Period, SortBy, SortDir } from "@/lib/types";

interface DateRange {
  value: string;
  label: string;
}

interface FiltersPanelProps {
  filters: Filters;
  categories: string[];
  providers: string[];
  ranges: DateRange[];
  monthRanges: DateRange[];
  advancedOpen: boolean;
  onAdvancedOpenChange: (open: boolean) => void;
  onChange: (patch: Partial<Filters>) => void;
  onCategoryToggle: (category: string) => void;
  onRangeSelect: (range: string) => void;
  onReset: () => void;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-2">
      <Label>{label}</Label>
      {children}
    </div>
  );
}

function SelectField<T extends string>({
  label,
  value,
  onValueChange,
  items,
}: {
  label: string;
  value: T;
  onValueChange: (value: T) => void;
  items: { value: T; label: string }[];
}) {
  return (
    <Field label={label}>
      <Select value={value} onValueChange={onValueChange}>
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {items.map((item) => (
            <SelectItem key={item.value} value={item.value}>
              {item.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  );
}

function PillButton({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <Button
      type="button"
      size="sm"
      variant={active ? "default" : "outline"}
      className={cn("h-8 rounded-full px-3 text-xs", active && "shadow-none")}
      onClick={onClick}
    >
      {children}
    </Button>
  );
}

export function FiltersPanel({
  filters,
  categories,
  providers,
  ranges,
  monthRanges,
  advancedOpen,
  onAdvancedOpenChange,
  onChange,
  onCategoryToggle,
  onRangeSelect,
  onReset,
}: FiltersPanelProps) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-3 space-y-0">
        <div>
          <CardTitle>Query filters</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">Auto-updating</p>
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => onAdvancedOpenChange(!advancedOpen)}>
            <ChevronDown className={cn("h-4 w-4 transition-transform", advancedOpen && "rotate-180")} />
            Advanced
          </Button>
          <Button type="button" variant="ghost" size="icon" onClick={onReset} aria-label="Reset filters">
            <RotateCcw className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="grid gap-5">
        <div className="grid gap-3">
          <Label>Quick range</Label>
          <div className="flex flex-wrap gap-2">
            {ranges.map((range) => (
              <PillButton key={range.value} active={filters.activeRange === range.value} onClick={() => onRangeSelect(range.value)}>
                {range.label}
              </PillButton>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            {monthRanges.map((range) => (
              <PillButton key={range.value} active={filters.activeRange === range.value} onClick={() => onRangeSelect(range.value)}>
                {range.label}
              </PillButton>
            ))}
          </div>
        </div>

        <div className="grid gap-3">
          <Label>Category</Label>
          <div className="flex flex-wrap gap-2">
            <PillButton active={filters.categories.length === 0} onClick={() => onCategoryToggle("")}>
              All categories
            </PillButton>
            {categories.map((category) => (
              <PillButton key={category} active={filters.categories.includes(category)} onClick={() => onCategoryToggle(category)}>
                {category}
              </PillButton>
            ))}
          </div>
        </div>

        {advancedOpen ? (
          <div className="filter-grid border-t pt-5">
            <Field label="Start date">
              <Input type="date" value={filters.startDate} onChange={(event) => onChange({ startDate: event.target.value, activeRange: "" })} />
            </Field>
            <Field label="End date">
              <Input type="date" value={filters.endDate} onChange={(event) => onChange({ endDate: event.target.value, activeRange: "" })} />
            </Field>
            <Field label="Merchant">
              <Input type="text" value={filters.merchant} placeholder="Search merchant name" onChange={(event) => onChange({ merchant: event.target.value, page: 1 })} />
            </Field>
            <Field label="Provider">
              <Select value={filters.provider || "all"} onValueChange={(value) => onChange({ provider: value === "all" ? "" : value, page: 1 })}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All providers</SelectItem>
                  {providers.map((provider) => (
                    <SelectItem key={provider} value={provider}>
                      {provider}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Min amount">
              <Input type="number" step="0.01" value={filters.minAmount} placeholder="0.00" onChange={(event) => onChange({ minAmount: event.target.value, page: 1 })} />
            </Field>
            <Field label="Max amount">
              <Input type="number" step="0.01" value={filters.maxAmount} placeholder="0.00" onChange={(event) => onChange({ maxAmount: event.target.value, page: 1 })} />
            </Field>
            <SelectField<Period>
              label="Period view"
              value={filters.period}
              onValueChange={(period) => onChange({ period, page: 1 })}
              items={[
                { value: "month", label: "Month" },
                { value: "quarter", label: "Quarter" },
                { value: "year", label: "Year" },
              ]}
            />
            <SelectField<SortBy>
              label="Sort by"
              value={filters.sortBy}
              onValueChange={(sortBy) => onChange({ sortBy, page: 1 })}
              items={[
                { value: "date", label: "Date" },
                { value: "amount", label: "Amount" },
                { value: "merchant", label: "Merchant" },
                { value: "category", label: "Category" },
                { value: "provider", label: "Provider" },
                { value: "description", label: "Description" },
              ]}
            />
            <SelectField<SortDir>
              label="Direction"
              value={filters.sortDir}
              onValueChange={(sortDir) => onChange({ sortDir, page: 1 })}
              items={[
                { value: "desc", label: "Desc" },
                { value: "asc", label: "Asc" },
              ]}
            />
            <div className="flex flex-col gap-3 pt-1">
              <Label>Search modes</Label>
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <input type="checkbox" className="h-4 w-4 accent-primary" checked={filters.merchantRegex} onChange={(event) => onChange({ merchantRegex: event.target.checked, page: 1 })} />
                Regex search
              </label>
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <input type="checkbox" className="h-4 w-4 accent-primary" checked={filters.includeHouse} onChange={(event) => onChange({ includeHouse: event.target.checked, page: 1 })} />
                Include house category
              </label>
            </div>
          </div>
        ) : null}

        <Tabs value={filters.period} onValueChange={(value) => onChange({ period: value as Period, page: 1 })}>
          <TabsList>
            <TabsTrigger value="month">Month</TabsTrigger>
            <TabsTrigger value="quarter">Quarter</TabsTrigger>
            <TabsTrigger value="year">Year</TabsTrigger>
          </TabsList>
        </Tabs>
      </CardContent>
    </Card>
  );
}
