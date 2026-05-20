import { FormEvent, useEffect, useState } from "react";
import { Bot, Send, User } from "lucide-react";
import { askAssistant, fetchAssistantStatus } from "@/lib/api";
import type { AssistantStatus } from "@/lib/types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  dataUsed?: unknown[];
}

function statusLabel(status: AssistantStatus | null) {
  if (!status) return "Checking AI";
  return `${status.provider} · ${status.model} · ${status.apiKeyPresent ? "ready" : "missing key"}`;
}

export function AssistantPanel() {
  const [status, setStatus] = useState<AssistantStatus | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAssistantStatus()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const text = question.trim();
    if (!text || loading) return;
    setQuestion("");
    setError(null);
    setLoading(true);
    setMessages((current) => [...current, { role: "user", text }]);
    try {
      const result = await askAssistant(text);
      setMessages((current) => [...current, { role: "assistant", text: result.answer || "No answer returned.", dataUsed: result.dataUsed }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Assistant request failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card id="assistant">
      <CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
        <div>
          <CardTitle>Ask Budgify</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">Spending, merchants, categories, trends, recurring charges.</p>
        </div>
        <Badge variant={status?.apiKeyPresent ? "default" : "outline"}>{statusLabel(status)}</Badge>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="grid max-h-96 gap-3 overflow-y-auto rounded-lg border bg-zinc-50 p-3">
          {messages.length === 0 ? <p className="text-sm text-muted-foreground">Try: How much did I spend at Costco year to date?</p> : null}
          {messages.map((message, index) => (
            <div key={`${message.role}-${index}`} className={message.role === "user" ? "ml-auto max-w-[85%]" : "mr-auto max-w-[85%]"}>
              <div className="mb-1 flex items-center gap-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {message.role === "user" ? <User className="h-3 w-3" /> : <Bot className="h-3 w-3" />}
                {message.role === "user" ? "You" : "Budgify"}
              </div>
              <div className={message.role === "user" ? "rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground" : "rounded-lg border bg-white px-3 py-2 text-sm"}>
                <p className="whitespace-pre-wrap">{message.text}</p>
              </div>
              {message.dataUsed && message.dataUsed.length > 0 ? (
                <details className="mt-1 text-xs text-muted-foreground">
                  <summary className="cursor-pointer">Data used ({message.dataUsed.length})</summary>
                  <pre className="mt-1 max-h-48 overflow-auto rounded-md border bg-white p-2">{JSON.stringify(message.dataUsed, null, 2)}</pre>
                </details>
              ) : null}
            </div>
          ))}
        </div>

        {error ? (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        <form className="grid gap-2 sm:grid-cols-[1fr_auto]" onSubmit={submit}>
          <textarea
            className="min-h-20 rounded-lg border bg-white px-3 py-2 text-sm outline-none ring-offset-background focus-visible:ring-2 focus-visible:ring-ring"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask about your spending"
            disabled={loading}
          />
          <Button type="submit" disabled={loading || !question.trim()} className="sm:self-end">
            <Send className="h-4 w-4" />
            {loading ? "Asking" : "Ask"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
