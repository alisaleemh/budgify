import { useEffect, useMemo, useState } from "react";
import type { SessionCost } from "@/lib/types";

export interface SessionCostSummary {
  entries: SessionCost[];
  aiCallCount: number;
  unpricedCallCount: number;
  totalEstimatedCostUsd: number;
  totalPromptTokens: number;
  totalCompletionTokens: number;
  totalTokens: number;
  sources: Record<string, { calls: number; estimatedCostUsd: number; tokens: number }>;
}

const STORAGE_KEY = "budgify.session-cost.ledger.v1";
const UPDATE_EVENT = "budgify:session-cost-updated";

function isBrowser() {
  return typeof window !== "undefined" && typeof sessionStorage !== "undefined";
}

function readLedger(): SessionCost[] {
  if (!isBrowser()) return [];
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item): item is SessionCost => Boolean(item && typeof item === "object" && "requestId" in item));
  } catch {
    return [];
  }
}

function writeLedger(entries: SessionCost[]) {
  if (!isBrowser()) return;
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // ignore storage failures; the UI still works for the current render
  }
}

export function formatSessionCost(value: number | null | undefined) {
  const amount = Number(value || 0);
  if (!Number.isFinite(amount) || amount <= 0) return "$0.00";
  const digits = amount < 0.01 ? 4 : 2;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(amount);
}

export function sessionCostSummaryLabel(summary: SessionCostSummary) {
  if (summary.aiCallCount > 0 && summary.unpricedCallCount === summary.aiCallCount) {
    return "Cost unavailable";
  }
  return formatSessionCost(summary.totalEstimatedCostUsd);
}

export function summarizeSessionCosts(entries: SessionCost[]): SessionCostSummary {
  const sources: SessionCostSummary["sources"] = {};
  let totalEstimatedCostUsd = 0;
  let totalPromptTokens = 0;
  let totalCompletionTokens = 0;
  let totalTokens = 0;
  let aiCallCount = 0;
  let unpricedCallCount = 0;

  for (const entry of entries) {
    if (entry.cached) continue;
    aiCallCount += 1;
    const estimatedCost = entry.estimatedCostUsd;
    if (estimatedCost == null) {
      unpricedCallCount += 1;
    } else {
      totalEstimatedCostUsd += Number(estimatedCost);
    }
    totalPromptTokens += Number(entry.promptTokens || 0);
    totalCompletionTokens += Number(entry.completionTokens || 0);
    totalTokens += Number(entry.totalTokens || 0);
    const bucket = sources[entry.source] || { calls: 0, estimatedCostUsd: 0, tokens: 0 };
    bucket.calls += 1;
    bucket.estimatedCostUsd += Number(estimatedCost || 0);
    bucket.tokens += Number(entry.totalTokens || 0);
    sources[entry.source] = bucket;
  }

  return {
    entries,
    aiCallCount,
    unpricedCallCount,
    totalEstimatedCostUsd,
    totalPromptTokens,
    totalCompletionTokens,
    totalTokens,
    sources,
  };
}

function emitUpdate() {
  if (!isBrowser()) return;
  window.dispatchEvent(new Event(UPDATE_EVENT));
}

export function recordSessionCost(input: SessionCost) {
  if (!isBrowser()) return summarizeSessionCosts(readLedger());
  if (input.cached) return summarizeSessionCosts(readLedger());
  const current = readLedger();
  if (current.some((entry) => entry.requestId === input.requestId)) {
    return summarizeSessionCosts(current);
  }
  const next = [...current, input];
  writeLedger(next);
  emitUpdate();
  return summarizeSessionCosts(next);
}

export function useSessionCostLedger() {
  const [entries, setEntries] = useState<SessionCost[]>(() => readLedger());

  useEffect(() => {
    const sync = () => setEntries(readLedger());
    window.addEventListener(UPDATE_EVENT, sync);
    return () => window.removeEventListener(UPDATE_EVENT, sync);
  }, []);

  return useMemo(
    () => ({
      entries,
      summary: summarizeSessionCosts(entries),
      recordSessionCost,
    }),
    [entries],
  );
}
