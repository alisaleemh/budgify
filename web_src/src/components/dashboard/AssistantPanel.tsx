import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  Bot,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Loader2,
  RotateCcw,
  Sparkles,
  MessageSquareText,
  TrendingDown,
  TrendingUp,
  User,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MarkdownRenderer } from "@/components/ui/markdown-renderer";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { askAssistant, fetchAssistantStatus } from "@/lib/api";
import { recordSessionCost, sessionCostSummaryLabel, useSessionCostLedger } from "@/lib/session-cost";
import { cn } from "@/lib/utils";
import type {
  AssistantCard,
  AssistantDataUse,
  AssistantStatus,
  AssistantTable,
} from "@/lib/types";
import { useStreamingText } from "@/hooks/use-streaming-text";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  streaming?: boolean;
  loading?: boolean;
  summary?: string;
  bullets?: string[];
  followup?: string;
  cards?: AssistantCard[];
  tables?: AssistantTable[];
  dataUsed?: AssistantDataUse[];
}

const STORAGE_KEY = "budgify.assistant.messages.v2";
const TYPED_PROMPTS = [
  "How much did I spend on restaurants last month?",
  "Compare groceries this month vs last month.",
  "Show unusual spending over the last 90 days.",
  "Which merchants repeat every month?",
];

function uid() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function statusLabel(status: AssistantStatus | null) {
  if (!status) return "Checking AI";
  return `${status.provider} · ${status.model} · ${status.apiKeyPresent ? "ready" : "missing key"}`;
}

function rateLabel(status: AssistantStatus | null) {
  const pricing = status?.pricing;
  if (!pricing) return "pricing unavailable";
  return `${pricing.model} · ${pricing.promptPerMillion.toFixed(2)}/M in · ${pricing.completionPerMillion.toFixed(2)}/M out`;
}

function normalizeTableKey(column: string) {
  return column.toLowerCase().replace(/[^a-z0-9]+/g, "_");
}

function safeString(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (value == null) return "";
  if (Array.isArray(value)) return value.map(safeString).filter(Boolean).join(", ");
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return "";
    }
  }
  return String(value);
}

function looksLikeStructuredJson(text: string) {
  const trimmed = text.trim();
  return trimmed.startsWith("{") || trimmed.startsWith("[") || trimmed.startsWith("```");
}

function summarizeResult(result: Record<string, unknown>) {
  if (Array.isArray(result.transactions)) return `${result.transactions.length} transactions`;
  if (Array.isArray(result.categories)) return `${result.categories.length} categories`;
  if (Array.isArray(result.merchants)) return `${result.merchants.length} merchants`;
  if (Array.isArray(result.recurring)) return `${result.recurring.length} recurring merchants`;
  if (result.period_a && result.period_b) return "2 periods compared";
  return Object.keys(result).slice(0, 3).join(", ");
}

function isRows(value: unknown): value is Record<string, unknown>[] {
  return Array.isArray(value) && value.every((item) => item && typeof item === "object");
}

function renderCompactRows(result: Record<string, unknown>) {
  const rows =
    (isRows(result.transactions) && result.transactions) ||
    (isRows(result.categories) && result.categories) ||
    (isRows(result.merchants) && result.merchants) ||
    (isRows(result.recurring) && result.recurring) ||
    [];
  if (!rows.length) return null;

  const first = rows[0];
  const keys = Object.keys(first).slice(0, 4);
  const numericColumns = new Set(["amount", "total", "average", "difference", "transactions"]);
  return (
    <div className="mt-3 overflow-hidden rounded-xl border bg-background">
      <Table>
        <TableHeader>
          <TableRow>
            {keys.map((key) => (
              <TableHead key={key} className={numericColumns.has(key) ? "text-right" : ""}>
                {key.replace(/_/g, " ")}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.slice(0, 3).map((row, index) => (
            <TableRow key={index}>
              {keys.map((key) => (
                <TableCell key={key} className={numericColumns.has(key) ? "text-right font-medium numeric" : ""}>
                  {safeString(row[key])}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {rows.length > 3 ? <p className="px-3 py-2 text-xs text-muted-foreground">+ {rows.length - 3} more rows</p> : null}
    </div>
  );
}

function StructuredCards({ cards }: { cards: AssistantCard[] }) {
  if (!cards.length) return null;

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {cards.map((card, index) => {
        if (card.kind === "metric") {
          return (
            <Card key={`${card.kind}-${index}`} className="shadow-sm">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">{card.label}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-semibold tracking-tight numeric">{card.value}</div>
                <p className="mt-1 text-sm text-muted-foreground">{card.detail}</p>
              </CardContent>
            </Card>
          );
        }

        if (card.kind === "comparison") {
          const comparison = card;
          const trendIcon =
            comparison.trend === "up" ? (
              <TrendingUp className="h-3.5 w-3.5" />
            ) : comparison.trend === "down" ? (
              <TrendingDown className="h-3.5 w-3.5" />
            ) : (
              <ArrowRight className="h-3.5 w-3.5" />
            );
          return (
            <Card key={`${card.kind}-${index}`} className="shadow-sm md:col-span-2">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium text-muted-foreground">{comparison.title}</CardTitle>
                {comparison.detail ? <p className="text-sm text-muted-foreground">{comparison.detail}</p> : null}
              </CardHeader>
              <CardContent className="grid gap-3 md:grid-cols-[1fr_auto_1fr] md:items-center">
                <div className="rounded-xl border bg-muted/30 p-3">
                  <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{comparison.leftLabel}</p>
                  <div className="mt-1 text-2xl font-semibold tracking-tight numeric">{comparison.leftValue}</div>
                  {comparison.leftDetail ? <p className="mt-1 text-sm text-muted-foreground">{comparison.leftDetail}</p> : null}
                </div>
                <div className="flex flex-col items-center gap-2 py-2 text-xs text-muted-foreground">
                  <div className="flex items-center gap-2 rounded-full border bg-background px-3 py-1">
                    {trendIcon}
                    <span>{comparison.deltaLabel || "Change"}</span>
                  </div>
                  {comparison.deltaValue ? <span className="font-medium text-foreground">{comparison.deltaValue}</span> : null}
                </div>
                <div className="rounded-xl border bg-muted/30 p-3">
                  <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{comparison.rightLabel}</p>
                  <div className="mt-1 text-2xl font-semibold tracking-tight numeric">{comparison.rightValue}</div>
                  {comparison.rightDetail ? <p className="mt-1 text-sm text-muted-foreground">{comparison.rightDetail}</p> : null}
                </div>
              </CardContent>
            </Card>
          );
        }

        if (card.kind === "list") {
          return (
            <Card key={`${card.kind}-${index}`} className="shadow-sm">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">{card.title}</CardTitle>
                {card.detail ? <p className="text-sm text-muted-foreground">{card.detail}</p> : null}
              </CardHeader>
              <CardContent className="space-y-3">
                {card.items.map((item) => (
                  <div key={item.label} className="flex items-start justify-between gap-3 rounded-xl border bg-muted/20 px-3 py-2">
                    <div className="min-w-0">
                      <p className="truncate font-medium">{item.label}</p>
                      {item.detail ? <p className="mt-0.5 text-sm text-muted-foreground">{item.detail}</p> : null}
                    </div>
                    {item.value ? <p className="shrink-0 font-semibold numeric">{item.value}</p> : null}
                  </div>
                ))}
              </CardContent>
            </Card>
          );
        }

        return (
          <Card key={`${card.kind}-${index}`} className="shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">{card.title}</CardTitle>
              {card.detail ? <p className="text-sm text-muted-foreground">{card.detail}</p> : null}
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              {card.chips.map((chip) => (
                <Badge key={chip} variant="secondary" className="rounded-full px-3 py-1 text-xs font-medium">
                  {chip}
                </Badge>
              ))}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

function CompactAnswer({ summary, bullets, followup }: { summary?: string; bullets?: string[]; followup?: string }) {
  if (!summary && !(bullets || []).length && !followup) return null;
  return (
    <div className="rounded-2xl border bg-muted/20 p-4">
      {summary ? <p className="text-base leading-7 text-foreground">{summary}</p> : null}
      {bullets?.length ? (
        <ul className={cn("mt-3 space-y-2", !summary && "mt-0")}>
          {bullets.map((bullet, index) => (
            <li key={`${bullet}-${index}`} className="flex gap-2 text-sm leading-6 text-foreground">
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary/70" aria-hidden="true" />
              <span>{bullet}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {followup ? (
        <div className="mt-3 flex items-start gap-2 rounded-xl border bg-background px-3 py-2">
          <MessageSquareText className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
          <p className="text-sm leading-6 text-muted-foreground">{followup}</p>
        </div>
      ) : null}
    </div>
  );
}

function AssistantTables({ tables }: { tables: AssistantTable[] }) {
  if (!tables.length) return null;
  const numericColumns = new Set(["amount", "total", "average", "difference", "transactions"]);

  return (
    <div className="grid gap-3">
      {tables.map((table) => (
        <Card key={table.title} className="overflow-hidden shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">{table.title}</CardTitle>
            {table.note ? <p className="text-sm text-muted-foreground">{table.note}</p> : null}
          </CardHeader>
          <CardContent className="pt-0">
            <Table>
              <TableHeader>
                <TableRow>
                  {table.columns.map((column) => (
                    <TableHead key={column} className={numericColumns.has(normalizeTableKey(column)) ? "text-right" : ""}>
                      {column}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {table.rows.map((row, rowIndex) => (
                  <TableRow key={`${table.title}-${rowIndex}`}>
                    {table.columns.map((column) => {
                      const key = normalizeTableKey(column);
                      return (
                        <TableCell key={column} className={numericColumns.has(key) ? "text-right font-medium numeric" : ""}>
                          {row[key] ?? row[column] ?? ""}
                        </TableCell>
                      );
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function ToolResultCollapse({ dataUsed }: { dataUsed: AssistantDataUse[] }) {
  if (!dataUsed.length) return null;

  return (
    <details className="group rounded-2xl border bg-muted/20 px-4 py-3">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180" />
          <span className="text-sm font-medium">Data used</span>
        </div>
        <span className="text-xs text-muted-foreground">{dataUsed.length} tool call{dataUsed.length === 1 ? "" : "s"}</span>
      </summary>
      <div className="mt-3 grid gap-3">
        {dataUsed.map((item, index) => (
          <div key={`${item.tool}-${index}`} className="rounded-xl border bg-background p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="secondary" className="rounded-full">
                {item.tool}
              </Badge>
              {Object.entries(item.arguments)
                .slice(0, 3)
                .map(([key, value]) => (
                  <Badge key={key} variant="outline" className="rounded-full">
                    {key}: {safeString(value)}
                  </Badge>
                ))}
            </div>
            <p className="mt-2 text-sm text-muted-foreground">{summarizeResult(item.result)}</p>
            {renderCompactRows(item.result)}
          </div>
        ))}
      </div>
    </details>
  );
}

function StreamingCursor() {
  return <span className="ml-1 inline-block h-4 w-2 animate-pulse rounded-sm bg-primary/70 align-middle" aria-hidden="true" />;
}

function LoadingMessage() {
  return (
    <div className="rounded-2xl border bg-card p-4 shadow-sm">
      <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Budgify
      </div>
      <div className="mt-3 space-y-2">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-1/2" />
      </div>
      <p className="mt-3 text-sm text-muted-foreground">Analyzing your ledger…</p>
    </div>
  );
}

function SuggestedPrompts({ onPrompt }: { onPrompt: (prompt: string) => void }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {TYPED_PROMPTS.map((prompt) => (
        <Button
          key={prompt}
          type="button"
          variant="outline"
          className="h-auto w-full justify-start rounded-xl px-3 py-3 text-left text-sm leading-6"
          onClick={() => onPrompt(prompt)}
        >
          <Sparkles className="mr-2 h-4 w-4 shrink-0 text-primary" />
          <span className="min-w-0">{prompt}</span>
        </Button>
      ))}
    </div>
  );
}

function AssistantMessage({ message }: { message: ChatMessage }) {
  const displayedText = useStreamingText(message.text, message.role === "assistant" && Boolean(message.streaming));

  if (message.role === "user") {
    return (
      <div className="ml-auto flex w-full max-w-[min(680px,88%)] flex-col items-end gap-1">
        <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
          <User className="h-3.5 w-3.5" />
          <span>You</span>
        </div>
        <div className="rounded-2xl bg-primary px-4 py-3 text-primary-foreground shadow-sm">
          <p className="whitespace-pre-wrap break-words leading-7">{message.text}</p>
        </div>
      </div>
    );
  }

  if (message.loading) {
    return (
      <div className="flex w-full max-w-[min(820px,100%)] flex-col items-start gap-1">
        <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
          <Bot className="h-3.5 w-3.5" />
          <span>Budgify</span>
        </div>
        <LoadingMessage />
      </div>
    );
  }

  return (
    <div className="flex w-full max-w-[min(820px,100%)] flex-col items-start gap-1">
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
        <Bot className="h-3.5 w-3.5" />
        <span>Budgify</span>
        {message.streaming ? <StreamingCursor /> : null}
      </div>
      <div className="w-full rounded-2xl border bg-card px-4 py-4 shadow-sm">
        <div className="grid gap-4">
          <CompactAnswer summary={message.summary} bullets={message.bullets} followup={message.followup} />
          <StructuredCards cards={message.cards || []} />
          <AssistantTables tables={message.tables || []} />
          {!message.summary && !message.bullets?.length && !looksLikeStructuredJson(displayedText) ? (
            <MarkdownRenderer
              content={displayedText}
              className={cn("prose prose-sm sm:prose-base dark:prose-invert max-w-none", !message.cards?.length && !message.tables?.length && "mt-0")}
            />
          ) : null}
          {!message.summary && !message.bullets?.length && looksLikeStructuredJson(displayedText) ? (
            <p className={cn("text-sm leading-6 text-muted-foreground", !message.cards?.length && !message.tables?.length && "mt-0")}>
              I couldn&apos;t format that answer cleanly. Please try again.
            </p>
          ) : null}
          <ToolResultCollapse dataUsed={message.dataUsed || []} />
        </div>
      </div>
    </div>
  );
}

function loadMessages(): ChatMessage[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item) => item && typeof item === "object" && typeof item.text === "string" && (item.role === "user" || item.role === "assistant"))
      .map((item) => ({ ...item, loading: false, streaming: false }));
  } catch {
    return [];
  }
}

function estimateStreamDuration(text: string) {
  return Math.min(2400, Math.max(900, 350 + text.length * 8));
}

export function AssistantPanel() {
  const [status, setStatus] = useState<AssistantStatus | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>(() => loadMessages());
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const shouldStickToBottom = useRef(true);
  const { summary: sessionSummary } = useSessionCostLedger();

  useEffect(() => {
    fetchAssistantStatus()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-40)));
    } catch {
      // persistence is best-effort
    }
  }, [messages]);

  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;

    const handleScroll = () => {
      const distance = node.scrollHeight - node.scrollTop - node.clientHeight;
      shouldStickToBottom.current = distance < 96;
    };

    node.addEventListener("scroll", handleScroll, { passive: true });
    handleScroll();
    return () => node.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    const node = scrollRef.current;
    if (!node || !shouldStickToBottom.current) return;
    node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  const onPrompt = (prompt: string) => setQuestion(prompt);

  const clearConversation = () => {
    setMessages([]);
    setQuestion("");
    setError(null);
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = question.trim();
    if (!text || loading) return;

    setQuestion("");
    setError(null);
    setLoading(true);

    const userMessage: ChatMessage = { id: uid(), role: "user", text };
    const loadingMessage: ChatMessage = { id: uid(), role: "assistant", text: "", loading: true };
    setMessages((current) => [...current, userMessage, loadingMessage]);

    try {
      const result = await askAssistant(text);
      if (result.sessionCost && !result.sessionCost.cached) {
        recordSessionCost(result.sessionCost);
      }
      const streamingMessage: ChatMessage = {
        id: loadingMessage.id,
        role: "assistant",
        text: result.answer || "No answer returned.",
        summary: result.summary || "",
        bullets: result.bullets || [],
        followup: result.followup || "",
        cards: result.cards || [],
        tables: result.tables || [],
        dataUsed: result.dataUsed || [],
        streaming: true,
      };
      setMessages((current) => current.map((message) => (message.id === loadingMessage.id ? streamingMessage : message)));
      window.setTimeout(() => {
        setMessages((current) =>
          current.map((message) => (message.id === loadingMessage.id ? { ...message, streaming: false } : message)),
        );
      }, estimateStreamDuration(streamingMessage.text));
    } catch (err) {
      setMessages((current) => current.filter((message) => message.id !== loadingMessage.id));
      setError(err instanceof Error ? err.message : "Assistant request failed");
    } finally {
      setLoading(false);
    }
  };

  const statusBadges = useMemo(
    () => [
      <Badge key="provider" variant={status?.apiKeyPresent ? "default" : "outline"} className="rounded-full px-3 py-1">
        {statusLabel(status)}
      </Badge>,
      status?.apiKeyPresent ? (
        <Badge key="key" variant="secondary" className="rounded-full px-3 py-1">
          <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
          Key ready
        </Badge>
      ) : (
        <Badge key="missing" variant="outline" className="rounded-full px-3 py-1">
          <CircleAlert className="mr-1 h-3.5 w-3.5" />
          Missing key
        </Badge>
      ),
    ],
    [status],
  );

  return (
    <Card id="assistant" className="overflow-hidden border-border/80 shadow-sm">
      <CardHeader className="gap-4 border-b bg-card/70">
      <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 space-y-2">
            <div className="flex items-center gap-2">
              <Bot className="h-5 w-5 text-primary" />
              <CardTitle className="text-lg">Ask Budgify</CardTitle>
            </div>
            <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
              Scannable answers for spending, merchants, categories, trends, recurring charges, and outliers.
            </p>
            <div className="flex flex-wrap gap-2">{statusBadges}</div>
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline" className="rounded-full px-3 py-1">Session {sessionCostSummaryLabel(sessionSummary)}</Badge>
              <Badge variant="secondary" className="rounded-full px-3 py-1">
                {sessionSummary.aiCallCount} AI call{sessionSummary.aiCallCount === 1 ? "" : "s"}
              </Badge>
              <Badge variant="outline" className="rounded-full px-3 py-1">
                {rateLabel(status)}
              </Badge>
            </div>
          </div>
          <Button type="button" variant="ghost" size="sm" onClick={clearConversation} className="rounded-full">
            <RotateCcw className="mr-2 h-4 w-4" />
            Clear
          </Button>
        </div>
      </CardHeader>

      <CardContent className="grid gap-4 p-4 sm:p-5">
        <div
          ref={scrollRef}
          role="log"
          aria-live="polite"
          aria-relevant="additions text"
          className="flex max-h-[72vh] min-h-[16rem] flex-col gap-4 overflow-y-auto rounded-2xl border bg-muted/20 p-3 sm:min-h-[19rem] sm:p-4"
        >
          {messages.length === 0 ? (
            <div className="grid gap-3">
              <div className="flex flex-wrap items-center gap-2 rounded-2xl border bg-card px-4 py-3 shadow-sm">
                <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                  <Sparkles className="h-3.5 w-3.5" />
                  Start here
                </div>
                <span className="text-sm text-muted-foreground">
                  Short answers first. Tables and cards only when they help.
                </span>
              </div>
              <SuggestedPrompts onPrompt={onPrompt} />
            </div>
          ) : null}

          {messages.map((message) => (
            <AssistantMessage key={message.id} message={message} />
          ))}
          <div />
        </div>

        {error ? (
          <Alert variant="destructive">
            <AlertTitle>Assistant request failed</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        <form className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end" onSubmit={submit}>
          <div className="grid gap-2">
            <label className="text-sm font-medium text-foreground" htmlFor="assistant-question">
              Ask a question
            </label>
            <Textarea
              id="assistant-question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                  return;
                }
                if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder="Ask Budgify about your spending"
              disabled={loading}
              className="min-h-24 resize-none rounded-2xl"
            />
          </div>
          <Button type="submit" disabled={loading || !question.trim()} className="h-11 rounded-full px-5">
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ArrowRight className="mr-2 h-4 w-4" />}
            {loading ? "Asking" : "Ask"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
