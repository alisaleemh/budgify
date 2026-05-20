import { useEffect, useRef, useState } from "react";
import { Maximize2, Minimize2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { formatCurrency } from "@/lib/format";

interface ChartDatum {
  label: string;
  value: number;
}

interface ChartCardProps {
  title: string;
  subtitle: string;
  type: "bar" | "line";
  data: ChartDatum[];
  expanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
}

interface HitTarget {
  x: number;
  y: number;
  w?: number;
  h?: number;
  r?: number;
  label: string;
  value: number;
}

const axisColor = "#3f3f46";
const labelColor = "#71717a";
const gridColor = "rgba(113, 113, 122, 0.18)";
const lineColor = "#d95f2d";
const barColor = "#2c756f";

function fitCanvas(canvas: HTMLCanvasElement) {
  const scale = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * scale;
  canvas.height = rect.height * scale;
  return scale;
}

function drawEmpty(ctx: CanvasRenderingContext2D, width: number, height: number) {
  ctx.fillStyle = labelColor;
  ctx.font = "13px Inter, system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("No chart data", width / 2, height / 2);
}

function drawBarChart(canvas: HTMLCanvasElement, data: ChartDatum[]) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return [];
  const scale = fitCanvas(canvas);
  const widthPx = canvas.width / scale;
  const heightPx = canvas.height / scale;
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
  ctx.clearRect(0, 0, widthPx, heightPx);
  if (data.length === 0) {
    drawEmpty(ctx, widthPx, heightPx);
    return [];
  }

  const paddingX = 38;
  const paddingTop = 24;
  const paddingBottom = 62;
  const width = widthPx - paddingX * 2;
  const height = heightPx - paddingTop - paddingBottom;
  const maxValue = Math.max(...data.map((d) => d.value), 1);
  const barWidth = width / Math.max(data.length, 1);
  const targets: HitTarget[] = [];

  ctx.strokeStyle = gridColor;
  ctx.lineWidth = 1;
  for (let i = 0; i <= 3; i += 1) {
    const y = paddingTop + height - (i / 3) * height;
    ctx.beginPath();
    ctx.moveTo(paddingX, y);
    ctx.lineTo(paddingX + width, y);
    ctx.stroke();
  }

  data.forEach((item, index) => {
    const barHeight = (item.value / maxValue) * height;
    const x = paddingX + index * barWidth + barWidth * 0.17;
    const y = paddingTop + height - barHeight;
    const w = Math.max(barWidth * 0.66, 4);
    ctx.fillStyle = barColor;
    ctx.fillRect(x, y, w, barHeight);
    targets.push({ x, y, w, h: barHeight, label: item.label, value: item.value });
  });

  ctx.fillStyle = labelColor;
  ctx.font = "12px Inter, system-ui, sans-serif";
  data.forEach((item, index) => {
    const x = paddingX + index * barWidth + barWidth * 0.5;
    ctx.save();
    ctx.translate(x, paddingTop + height + 28);
    ctx.rotate(-0.42);
    ctx.textAlign = "right";
    ctx.fillText(item.label, 0, 0, Math.max(72, barWidth * 1.8));
    ctx.restore();
  });

  return targets;
}

function drawLineChart(canvas: HTMLCanvasElement, data: ChartDatum[]) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return [];
  const scale = fitCanvas(canvas);
  const widthPx = canvas.width / scale;
  const heightPx = canvas.height / scale;
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
  ctx.clearRect(0, 0, widthPx, heightPx);
  if (data.length === 0) {
    drawEmpty(ctx, widthPx, heightPx);
    return [];
  }

  const paddingLeft = 56;
  const paddingRight = 22;
  const paddingTop = 26;
  const paddingBottom = 58;
  const width = widthPx - paddingLeft - paddingRight;
  const height = heightPx - paddingTop - paddingBottom;
  const values = data.map((d) => d.value);
  const minValue = Math.min(...values, 0);
  const maxValue = Math.max(...values, 0);
  const range = maxValue - minValue || 1;

  ctx.strokeStyle = gridColor;
  ctx.fillStyle = labelColor;
  ctx.font = "11px Inter, system-ui, sans-serif";
  for (let i = 0; i <= 4; i += 1) {
    const value = minValue + (range / 4) * i;
    const y = paddingTop + height - ((value - minValue) / range) * height;
    ctx.beginPath();
    ctx.moveTo(paddingLeft, y);
    ctx.lineTo(paddingLeft + width, y);
    ctx.stroke();
    ctx.textAlign = "right";
    ctx.fillText(formatCurrency(Math.round(value)), paddingLeft - 8, y + 4);
  }

  ctx.strokeStyle = axisColor;
  ctx.beginPath();
  ctx.moveTo(paddingLeft, paddingTop);
  ctx.lineTo(paddingLeft, paddingTop + height);
  ctx.lineTo(paddingLeft + width, paddingTop + height);
  ctx.stroke();

  ctx.strokeStyle = lineColor;
  ctx.lineWidth = 2;
  ctx.beginPath();
  data.forEach((item, index) => {
    const x = paddingLeft + (index / Math.max(data.length - 1, 1)) * width;
    const y = paddingTop + height - ((item.value - minValue) / range) * height;
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  const targets: HitTarget[] = [];
  ctx.fillStyle = lineColor;
  data.forEach((item, index) => {
    const x = paddingLeft + (index / Math.max(data.length - 1, 1)) * width;
    const y = paddingTop + height - ((item.value - minValue) / range) * height;
    ctx.beginPath();
    ctx.arc(x, y, 3.5, 0, Math.PI * 2);
    ctx.fill();
    targets.push({ x, y, r: 7, label: item.label, value: item.value });
  });

  ctx.fillStyle = labelColor;
  data.forEach((item, index) => {
    if (data.length > 10 && index % 2 !== 0) return;
    const x = paddingLeft + (index / Math.max(data.length - 1, 1)) * width;
    ctx.save();
    ctx.translate(x, paddingTop + height + 27);
    ctx.rotate(-0.42);
    ctx.textAlign = "right";
    ctx.fillText(item.label, 0, 0);
    ctx.restore();
  });

  return targets;
}

export function ChartCard({ title, subtitle, type, data, expanded, onExpandedChange }: ChartCardProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const targetsRef = useRef<HitTarget[]>([]);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; label: string; value: number } | null>(null);

  useEffect(() => {
    const draw = () => {
      if (!canvasRef.current) return;
      targetsRef.current = type === "bar" ? drawBarChart(canvasRef.current, data) : drawLineChart(canvasRef.current, data);
    };
    draw();
    window.addEventListener("resize", draw);
    return () => window.removeEventListener("resize", draw);
  }, [data, type, expanded]);

  return (
    <Card className={cn("min-w-0", expanded && "chart-card-expanded xl:col-span-2")}>
      <CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
        <div className="min-w-0">
          <CardTitle>{title}</CardTitle>
          <p className="mt-1 truncate text-sm text-muted-foreground">{subtitle}</p>
        </div>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button type="button" variant="ghost" size="icon" onClick={() => onExpandedChange(!expanded)} aria-label={expanded ? "Collapse chart" : "Expand chart"}>
                {expanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{expanded ? "Collapse" : "Expand"}</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </CardHeader>
      <CardContent className="relative">
        <canvas
          ref={canvasRef}
          className="chart-canvas"
          onMouseMove={(event) => {
            const rect = event.currentTarget.getBoundingClientRect();
            const x = event.clientX - rect.left;
            const y = event.clientY - rect.top;
            const hit = targetsRef.current.find((target) => {
              if (target.w !== undefined && target.h !== undefined) {
                return x >= target.x && x <= target.x + target.w && y >= target.y && y <= target.y + target.h;
              }
              const dx = x - target.x;
              const dy = y - target.y;
              return Math.sqrt(dx * dx + dy * dy) <= (target.r || 0);
            });
            setTooltip(hit ? { x: event.clientX - rect.left, y: event.clientY - rect.top, label: hit.label, value: hit.value } : null);
          }}
          onMouseLeave={() => setTooltip(null)}
        />
        {tooltip ? (
          <div className="pointer-events-none absolute z-10 rounded-md bg-zinc-950 px-2 py-1 text-xs text-zinc-50 shadow" style={{ left: tooltip.x, top: tooltip.y, transform: "translate(-50%, -125%)" }}>
            {tooltip.label}: {formatCurrency(tooltip.value)}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
