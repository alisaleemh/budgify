import { BarChart3, Database, Menu, RefreshCw, Table2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

interface AppLayoutProps {
  title: string;
  eyebrow: string;
  headline: string;
  lede: string;
  lastSync: string;
  loading: boolean;
  mobileNavOpen: boolean;
  onMobileNavOpenChange: (open: boolean) => void;
  onNavigate: (href: string, label: string) => void;
  onRefresh: () => void;
  children: React.ReactNode;
}

const navItems = [
  { href: "#overview", label: "Overview", icon: BarChart3 },
  { href: "#charts", label: "Charts", icon: Database },
  { href: "#transactions", label: "Transactions", icon: Table2 },
];

function SidebarNav({ onNavigate }: { onNavigate: (href: string, label: string) => void }) {
  return (
    <nav className="grid gap-1">
      {navItems.map((item) => (
        <a
          key={item.href}
          href={item.href}
          className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
          onClick={() => onNavigate(item.href, item.label)}
        >
          <item.icon className="h-4 w-4" />
          {item.label}
        </a>
      ))}
    </nav>
  );
}

export function AppLayout({
  title,
  eyebrow,
  headline,
  lede,
  lastSync,
  loading,
  mobileNavOpen,
  onMobileNavOpenChange,
  onNavigate,
  onRefresh,
  children,
}: AppLayoutProps) {
  return (
    <div className="dashboard-shell">
      <div className="dashboard-main">
        <aside className="sticky top-4 hidden h-[calc(100vh-2rem)] w-64 shrink-0 rounded-2xl border bg-white p-4 shadow-sm lg:block">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">{eyebrow}</p>
            <h1 className="mt-2 text-xl font-semibold tracking-normal">{title}</h1>
          </div>
          <Separator className="my-4" />
          <SidebarNav onNavigate={onNavigate} />
          <div className="absolute bottom-4 left-4 right-4 rounded-xl border bg-zinc-50 p-3">
            <p className="text-xs text-muted-foreground">Database</p>
            <p className="mt-1 truncate text-sm font-medium">budgify.db</p>
            <p className="mt-3 text-xs text-muted-foreground">Last sync</p>
            <p className="mt-1 truncate text-sm font-medium">{lastSync}</p>
          </div>
        </aside>

        <div className="min-w-0 flex-1">
          <header className="sticky top-0 z-30 -mx-3 border-b bg-zinc-50/90 px-3 py-3 backdrop-blur sm:-mx-5 sm:px-5 lg:-mx-6 lg:px-6">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary lg:hidden">{eyebrow}</p>
                <h2 className="truncate text-lg font-semibold tracking-normal">{headline}</h2>
                <p className="hidden truncate text-sm text-muted-foreground md:block">{lede}</p>
              </div>
              <div className="flex items-center gap-2">
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button type="button" variant="outline" size="icon" onClick={onRefresh} disabled={loading} aria-label="Refresh now">
                        <RefreshCw className={loading ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Refresh now</TooltipContent>
                </Tooltip>
                </TooltipProvider>
                <Sheet open={mobileNavOpen} onOpenChange={onMobileNavOpenChange}>
                  <SheetTrigger asChild>
                    <Button type="button" variant="outline" size="icon" className="lg:hidden" aria-label="Open navigation">
                      <Menu className="h-4 w-4" />
                    </Button>
                  </SheetTrigger>
                  <SheetContent>
                    <SheetHeader>
                      <SheetTitle>{title}</SheetTitle>
                    </SheetHeader>
                    <div className="mt-6">
                      <SidebarNav onNavigate={onNavigate} />
                    </div>
                  </SheetContent>
                </Sheet>
              </div>
            </div>
          </header>

          <main className="grid gap-4 py-4">{children}</main>
        </div>
      </div>
    </div>
  );
}
