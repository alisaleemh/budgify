import { Database, DollarSign, Hash, RefreshCw, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatSessionCost, type SessionCostSummary } from "@/lib/session-cost";
import type { AssistantStatus } from "@/lib/types";

function formatPerMillion(value: number | null | undefined) {
  const amount = Number(value || 0);
  if (!Number.isFinite(amount) || amount <= 0) return "$0/M";
  return `$${amount.toFixed(amount < 10 ? 2 : 0)}/M`;
}

export function SessionCostCard({
  summary,
  status,
  title = "Session cost",
}: {
  summary: SessionCostSummary;
  status?: AssistantStatus | null;
  title?: string;
}) {
  const pricing = status?.pricing;
  const priceLabel = pricing ? `${formatPerMillion(pricing.promptPerMillion)} in · ${formatPerMillion(pricing.completionPerMillion)} out` : "Pricing unavailable";
  const sourceCount = Object.keys(summary.sources).length;
  const activeSource =
    summary.sources.beta && summary.sources.assistant ? "mixed AI" : summary.sources.beta ? "AI beta" : summary.sources.assistant ? "Ask Budgify" : "none";
  const costLabel = summary.aiCallCount > 0 && summary.unpricedCallCount === summary.aiCallCount ? "Cost unavailable" : formatSessionCost(summary.totalEstimatedCostUsd);

  return (
    <Card className="rounded-2xl border-zinc-200 bg-white/85 shadow-sm backdrop-blur">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between gap-3 text-base">
          <span className="inline-flex items-center gap-2">
            <DollarSign className="h-4 w-4 text-emerald-800" />
            {title}
          </span>
          <Badge variant={summary.aiCallCount > 0 ? "default" : "outline"} className="rounded-full">
            {summary.aiCallCount > 0 ? `${summary.aiCallCount} calls` : "No AI spend"}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div className="grid gap-1">
          <p className="text-3xl font-semibold tracking-tight numeric">{costLabel}</p>
          <p className="text-sm text-muted-foreground">
            {summary.totalTokens.toLocaleString()} tokens · {activeSource} · {sourceCount} source{sourceCount === 1 ? "" : "s"}
          </p>
        </div>
        <div className="grid gap-2 rounded-xl border bg-zinc-50 p-3 text-sm text-muted-foreground">
          <p className="flex items-center gap-2 text-foreground">
            <Sparkles className="h-4 w-4 text-emerald-800" />
            {priceLabel}
          </p>
          {status?.deployCommit ? (
            <p className="flex items-center gap-2">
              <Hash className="h-4 w-4" />
              Build <span className="font-mono text-foreground">{status.deployCommit.slice(0, 7)}</span>
            </p>
          ) : null}
          <p className="flex items-center gap-2">
            <RefreshCw className="h-4 w-4" />
            Refresh-safe. Cached responses do not add cost.
          </p>
          <p className="flex items-center gap-2">
            <Database className="h-4 w-4" />
            Session only. Cleared when this browser session ends.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
