import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Check, HelpCircle, Loader2, ShieldCheck, Sparkles, X } from "lucide-react";
import { askBeta, fetchAssistantStatus, fetchBetaBriefing } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import type { AssistantStatus, BetaBriefing, BetaCitation, BetaInsight, BetaRecommendation } from "@/lib/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { SessionCostCard } from "@/components/session/SessionCostCard";
import { recordSessionCost, useSessionCostLedger } from "@/lib/session-cost";

const examples = [
  "Can I afford a $5,000 trip in September?",
  "Why was spending high this month?",
  "What subscriptions should I cancel?",
  "How much is safe to spend this week?",
];

export function BetaHome() {
  const [briefing, setBriefing] = useState<BetaBriefing | null>(null);
  const [answer, setAnswer] = useState<BetaBriefing | null>(null);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(true);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionStates, setActionStates] = useState<Record<string, "approved" | "ignored">>({});
  const [status, setStatus] = useState<AssistantStatus | null>(null);
  const { summary } = useSessionCostLedger();

  useEffect(() => {
    fetchAssistantStatus().then(setStatus).catch(() => setStatus(null));
    setLoading(true);
    fetchBetaBriefing()
      .then((payload) => {
        setBriefing(payload);
        if (payload.sessionCost && !payload.sessionCost.cached) {
          recordSessionCost(payload.sessionCost);
        }
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Unable to load AI beta briefing"))
      .finally(() => setLoading(false));
  }, []);

  const active = answer || briefing;
  const citationMap = useMemo(() => {
    const map = new Map<string, BetaCitation>();
    for (const citation of active?.citations || []) map.set(citation.id, citation);
    return map;
  }, [active?.citations]);

  async function submit(nextQuestion = question) {
    const cleaned = nextQuestion.trim();
    if (!cleaned) return;
    setQuestion(cleaned);
    setAsking(true);
    setError(null);
    try {
      const payload = await askBeta(cleaned);
      if (payload.sessionCost && !payload.sessionCost.cached) {
        recordSessionCost(payload.sessionCost);
      }
      setAnswer(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to ask Budgify");
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_#e7f2ef,_transparent_34rem),linear-gradient(135deg,_#f8faf9,_#f1eee8)] text-zinc-950">
      <main className="mx-auto grid w-full max-w-7xl gap-6 px-4 py-5 sm:px-6 lg:grid-cols-[1fr_360px] lg:px-8">
        <section className="grid gap-5">
          <header className="rounded-[2rem] border border-white/70 bg-white/75 p-5 shadow-sm backdrop-blur">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <a href="/" className="inline-flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground">
                  <ArrowLeft className="h-4 w-4" />
                  Classic dashboard
                </a>
                <div className="mt-8 flex items-center gap-2">
                  <Badge className="bg-emerald-800 text-white hover:bg-emerald-800">AI Beta</Badge>
                  {active?.estimated ? <Badge variant="outline">Estimated where noted</Badge> : null}
                </div>
                <h1 className="mt-3 max-w-3xl text-4xl font-semibold tracking-tight md:text-5xl">Your money briefing</h1>
                <p className="mt-3 max-w-2xl text-lg text-muted-foreground">
                  Budgify reads your ledger through MCP, explains what changed, and shows the transactions behind important claims.
                </p>
              </div>
            <div className="rounded-2xl border bg-zinc-950 px-4 py-3 text-sm text-white shadow-sm">
              <p className="font-medium">Personal CFO mode</p>
              <p className="mt-1 text-zinc-300">No money movement. Approval required for future actions.</p>
            </div>
          </div>
        </header>

          {error ? (
            <Alert variant="destructive">
              <AlertTitle>AI beta unavailable</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {loading ? (
            <Card className="rounded-[1.5rem]">
              <CardContent className="flex items-center gap-3 p-6 text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin" />
                Building a grounded MCP briefing...
              </CardContent>
            </Card>
          ) : active ? (
            <>
              <BriefingSummary briefing={active} />
              <Section title="What changed">
                {active.insights.length ? (
                  active.insights.map((insight) => <InsightCard key={insight.title} insight={insight} citations={citationMap} />)
                ) : (
                  <EmptyCard text="Budgify did not find enough recent change to call out." />
                )}
              </Section>
              <Section title="What it means">
                <MeaningCard briefing={active} />
              </Section>
              <Section title="Recommended actions">
                {active.recommendations.length ? (
                  active.recommendations.map((item) => {
                    const state = actionStates[item.title] || item.state;
                    return (
                      <ActionCard
                        key={item.title}
                        item={{ ...item, state }}
                        citations={citationMap}
                        onApprove={() => setActionStates((current) => ({ ...current, [item.title]: "approved" }))}
                        onIgnore={() => setActionStates((current) => ({ ...current, [item.title]: "ignored" }))}
                      />
                    );
                  })
                ) : (
                  <EmptyCard text="No safe action recommended from the current data." />
                )}
              </Section>
            </>
          ) : null}
        </section>

        <aside className="grid h-fit gap-4 lg:sticky lg:top-5">
          <SessionCostCard summary={summary} status={status} title="Session cost" />
          <Card className="rounded-[1.5rem] border-zinc-200 bg-white/85 shadow-sm backdrop-blur">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-emerald-800" />
                Ask Budgify
              </CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3">
              <Textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Ask about a trip, spending spike, subscriptions, or this week's safe spend."
                className="min-h-28 resize-none bg-white"
              />
              <Button type="button" onClick={() => void submit()} disabled={asking || !question.trim()} className="bg-emerald-800 hover:bg-emerald-900">
                {asking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                Ask
              </Button>
              <div className="grid gap-2">
                {examples.map((example) => (
                  <button
                    key={example}
                    type="button"
                    className="rounded-xl border bg-zinc-50 px-3 py-2 text-left text-sm text-muted-foreground hover:bg-white hover:text-foreground"
                    onClick={() => void submit(example)}
                  >
                    {example}
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>

          {answer ? (
            <Card className="rounded-[1.5rem] border-emerald-900/20 bg-emerald-950 text-white shadow-sm">
              <CardHeader>
                <CardTitle>Answer</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-lg font-medium">{answer.summary}</p>
                <p className="mt-3 text-sm text-emerald-100">
                  Grounded in {answer.citations.length} cited transaction{answer.citations.length === 1 ? "" : "s"} from MCP context.
                </p>
              </CardContent>
            </Card>
          ) : null}

          {active ? <FreshnessCard briefing={active} /> : null}
        </aside>
      </main>
    </div>
  );
}

function BriefingSummary({ briefing }: { briefing: BetaBriefing }) {
  return (
    <Card className="rounded-[1.5rem] border-zinc-200 bg-white shadow-sm">
      <CardContent className="grid gap-4 p-6 md:grid-cols-[1fr_auto] md:items-center">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-emerald-800">Daily briefing</p>
          <p className="mt-2 text-2xl font-semibold tracking-tight">{briefing.summary}</p>
        </div>
        <div className="rounded-2xl bg-zinc-100 p-4 text-sm">
          <p className="text-muted-foreground">Source</p>
          <p className="font-medium">{briefing.context.transactionCount} ledger transactions</p>
          <p className="mt-1 text-muted-foreground">{briefing.dataFreshness.rangeStart} to {briefing.dataFreshness.rangeEnd}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-3">
      <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
      <div className="grid gap-3">{children}</div>
    </section>
  );
}

function InsightCard({ insight, citations }: { insight: BetaInsight; citations: Map<string, BetaCitation> }) {
  return (
    <Card className="rounded-[1.5rem] bg-white shadow-sm">
      <CardContent className="grid gap-4 p-5">
        <div>
          <h3 className="text-lg font-semibold">{insight.title}</h3>
          <p className="mt-2 text-muted-foreground">{insight.body}</p>
        </div>
        {insight.why ? (
          <div className="rounded-xl border bg-zinc-50 p-3 text-sm text-muted-foreground">
            <span className="inline-flex items-center gap-2 font-medium text-foreground">
              <HelpCircle className="h-4 w-4" />
              Why am I seeing this?
            </span>
            <p className="mt-1">{insight.why}</p>
          </div>
        ) : null}
        <CitationList ids={insight.citationIds} citations={citations} />
      </CardContent>
    </Card>
  );
}

function MeaningCard({ briefing }: { briefing: BetaBriefing }) {
  return (
    <Card className="rounded-[1.5rem] bg-stone-950 text-white shadow-sm">
      <CardContent className="grid gap-3 p-5">
        <ShieldCheck className="h-5 w-5 text-emerald-300" />
        <p className="text-lg font-medium">{briefing.summary}</p>
        <p className="text-sm text-stone-300">
          This beta treats MCP transaction data as source of truth. If the ledger is incomplete, Budgify marks conclusions as estimates and avoids certainty.
        </p>
      </CardContent>
    </Card>
  );
}

function ActionCard({
  item,
  citations,
  onApprove,
  onIgnore,
}: {
  item: BetaRecommendation;
  citations: Map<string, BetaCitation>;
  onApprove: () => void;
  onIgnore: () => void;
}) {
  return (
    <Card className="rounded-[1.5rem] bg-white shadow-sm">
      <CardContent className="grid gap-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-lg font-semibold">{item.title}</h3>
            <p className="mt-2 text-muted-foreground">{item.body}</p>
          </div>
          <Badge variant={item.state === "approved" ? "default" : item.state === "ignored" ? "secondary" : "outline"}>{item.state}</Badge>
        </div>
        <CitationList ids={item.citationIds} citations={citations} />
        <div className="flex gap-2">
          <Button type="button" size="sm" onClick={onApprove} disabled={item.state !== "open"}>
            <Check className="h-4 w-4" />
            Approve
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={onIgnore} disabled={item.state !== "open"}>
            <X className="h-4 w-4" />
            Ignore
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function CitationList({ ids, citations }: { ids: string[]; citations: Map<string, BetaCitation> }) {
  const rows = ids.map((id) => citations.get(id)).filter((item): item is BetaCitation => Boolean(item));
  if (!rows.length) return null;
  return (
    <div className="grid gap-2">
      {rows.map((item) => (
        <div key={item.id} className="grid gap-1 rounded-xl border bg-zinc-50 p-3 text-sm sm:grid-cols-[1fr_auto] sm:items-center">
          <div>
            <p className="font-medium">{item.merchant}</p>
            <p className="text-muted-foreground">{item.date} · {item.category}{item.account ? ` · ${item.account}` : ""}</p>
          </div>
          <p className="font-semibold numeric">{formatCurrency(item.amount)}</p>
        </div>
      ))}
    </div>
  );
}

function FreshnessCard({ briefing }: { briefing: BetaBriefing }) {
  return (
    <Card className="rounded-[1.5rem] bg-white/85 shadow-sm backdrop-blur">
      <CardHeader>
        <CardTitle className="text-base">Trust controls</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-2 text-sm text-muted-foreground">
        <p>As of {briefing.dataFreshness.asOf}</p>
        <p>Briefing range: {briefing.dataFreshness.rangeStart} to {briefing.dataFreshness.rangeEnd}</p>
        <p>Ledger range: {briefing.dataFreshness.ledgerStart || "unknown"} to {briefing.dataFreshness.ledgerEnd || "unknown"}</p>
        <p>Tools: {briefing.context.tools.join(", ")}</p>
      </CardContent>
    </Card>
  );
}

function EmptyCard({ text }: { text: string }) {
  return (
    <Card className="rounded-[1.5rem] border-dashed bg-white/70">
      <CardContent className="p-5 text-sm text-muted-foreground">{text}</CardContent>
    </Card>
  );
}
