import { useMemo, useState, type ReactNode } from "react";
import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

function nodeToText(node: unknown): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(nodeToText).join("");
  if (node && typeof node === "object" && "props" in node) {
    const props = node as { props?: { children?: unknown } };
    return nodeToText(props.props?.children);
  }
  return "";
}

function CopyableCodeBlock({ children, language }: { children: unknown; language?: string }) {
  const [copied, setCopied] = useState(false);
  const text = useMemo(() => nodeToText(children).trimEnd(), [children]);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Copy is best-effort.
    }
  };

  return (
    <div className="my-4 overflow-hidden rounded-xl border border-zinc-200 bg-zinc-950 text-zinc-50 shadow-sm">
      <div className="flex items-center justify-between gap-3 border-b border-white/10 px-3 py-2 text-[11px] uppercase tracking-[0.18em] text-zinc-400">
        <span>{language || "code"}</span>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-zinc-300 hover:bg-white/10 hover:text-white"
          onClick={onCopy}
          aria-label="Copy code"
        >
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
        </Button>
      </div>
      <pre className="overflow-x-auto px-4 py-3 text-sm leading-6 text-zinc-100">
        <code>{children as ReactNode}</code>
      </pre>
    </div>
  );
}

export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  if (!content.trim()) return null;

  const components: Components = {
    h1: ({ className: headingClassName, ...props }) => (
      <h1 className={cn("mt-6 text-xl font-semibold tracking-tight text-foreground first:mt-0", headingClassName)} {...props} />
    ),
    h2: ({ className: headingClassName, ...props }) => (
      <h2 className={cn("mt-5 text-lg font-semibold tracking-tight text-foreground first:mt-0", headingClassName)} {...props} />
    ),
    h3: ({ className: headingClassName, ...props }) => (
      <h3 className={cn("mt-4 text-base font-semibold tracking-tight text-foreground first:mt-0", headingClassName)} {...props} />
    ),
    p: ({ className: paragraphClassName, ...props }) => (
      <p className={cn("my-2 leading-7 text-foreground/95", paragraphClassName)} {...props} />
    ),
    ul: ({ className: listClassName, ...props }) => (
      <ul className={cn("my-3 list-disc space-y-1 pl-5 leading-7", listClassName)} {...props} />
    ),
    ol: ({ className: listClassName, ...props }) => (
      <ol className={cn("my-3 list-decimal space-y-1 pl-5 leading-7", listClassName)} {...props} />
    ),
    li: ({ className: itemClassName, ...props }) => <li className={cn("pl-1", itemClassName)} {...props} />,
    blockquote: ({ className: blockquoteClassName, ...props }) => (
      <blockquote
        className={cn("my-4 rounded-xl border border-border bg-muted/50 px-4 py-3 text-foreground/90", blockquoteClassName)}
        {...props}
      />
    ),
    hr: ({ className: hrClassName, ...props }) => <hr className={cn("my-6 border-border", hrClassName)} {...props} />,
    strong: ({ className: strongClassName, ...props }) => <strong className={cn("font-semibold text-foreground", strongClassName)} {...props} />,
    em: ({ className: emClassName, ...props }) => <em className={cn("italic", emClassName)} {...props} />,
    a: ({ className: anchorClassName, ...props }) => (
      <a className={cn("font-medium text-primary underline underline-offset-4 hover:text-primary/90", anchorClassName)} {...props} />
    ),
    table: ({ className: tableClassName, ...props }) => (
      <div className="my-4 overflow-x-auto rounded-xl border border-border bg-background">
        <table className={cn("w-full border-separate border-spacing-0 text-sm", tableClassName)} {...props} />
      </div>
    ),
    thead: ({ className: theadClassName, ...props }) => <thead className={cn("bg-muted/60", theadClassName)} {...props} />,
    tbody: ({ className: tbodyClassName, ...props }) => <tbody className={cn("divide-y divide-border", tbodyClassName)} {...props} />,
    tr: ({ className: trClassName, ...props }) => <tr className={cn("transition-colors hover:bg-muted/50", trClassName)} {...props} />,
    th: ({ className: thClassName, ...props }) => (
      <th
        className={cn("border-b border-border px-3 py-2 text-left text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground", thClassName)}
        {...props}
      />
    ),
    td: ({ className: tdClassName, ...props }) => <td className={cn("border-b border-border px-3 py-2 align-top", tdClassName)} {...props} />,
    code: ({ className: codeClassName, children, ...props }) => {
      const inline = !codeClassName || !codeClassName.includes("language-");
      if (inline) {
        return (
          <code
            className={cn("rounded-md border border-border bg-muted px-1.5 py-0.5 font-mono text-[0.92em] font-medium text-foreground", codeClassName)}
            {...props}
          >
            {children}
          </code>
        );
      }
      const language = codeClassName?.replace("language-", "");
      return <CopyableCodeBlock language={language} children={children} />;
    },
    pre: ({ children }) => <>{children}</>,
    img: ({ className: imageClassName, ...props }) => (
      <img className={cn("my-4 rounded-xl border border-border", imageClassName)} alt="" {...props} />
    ),
  };

  return (
    <div
      className={cn(
        "max-w-none text-sm leading-7 text-foreground",
        "prose prose-sm sm:prose-base dark:prose-invert prose-zinc",
        "prose-headings:scroll-mt-24 prose-p:my-2 prose-ul:my-2 prose-ol:my-2 prose-li:my-0 prose-table:my-0",
        "prose-headings:mb-2 prose-h1:mb-3 prose-h2:mb-2 prose-h3:mb-2",
        className,
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
