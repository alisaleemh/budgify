import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type AnalyticsMetadata = Record<string, unknown>;
type AnalyticsEventType = string;

interface AnalyticsEventInput {
  eventType: AnalyticsEventType;
  page?: string;
  component?: string;
  metadata?: AnalyticsMetadata;
  ts?: string;
}

interface AnalyticsSettings {
  enabled: boolean;
  samplingRate: number;
  devLogging: boolean;
}

interface AnalyticsEventPayload {
  eventId: string;
  userId: string;
  sessionId: string;
  eventType: string;
  page: string;
  component: string | null;
  metadata: AnalyticsMetadata;
  ts: string;
}

interface AnalyticsQueueState {
  settings: AnalyticsSettings;
  sampled: boolean;
  userId: string;
  sessionId: string;
  startedAt: string;
}

const STORAGE_USER_ID = "budgify.analytics.user-id";
const STORAGE_SESSION_KEY = "budgify.analytics.session";
const ENDPOINT = "/api/analytics/events";

let queue: AnalyticsEventPayload[] = [];
let flushTimer: number | null = null;
let inFlight = false;

function isBrowser() {
  return typeof window !== "undefined" && typeof document !== "undefined";
}

function randomId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (char) => {
    const value = (Math.random() * 16) | 0;
    const next = char === "x" ? value : (value & 0x3) | 0x8;
    return next.toString(16);
  });
}

function stripControlChars(value: string) {
  let out = "";
  for (const char of value) {
    const code = char.charCodeAt(0);
    if (code <= 31 || code === 127) {
      out += " ";
    } else {
      out += char;
    }
  }
  return out;
}

function cleanText(value: string, limit = 120) {
  return stripControlChars(value).replace(/\s+/g, " ").trim().slice(0, limit);
}

function normalizeKey(value: string) {
  return cleanText(value, 64).toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "");
}

function looksSensitive(value: string) {
  return /\b(?:\d[ -]*?){6,}\b/.test(value) || /\b[^@\s]+@[^@\s]+\.[^@\s]+\b/.test(value);
}

function sanitizeValue(key: string | null, value: unknown, depth = 0): unknown {
  if (depth > 3) return undefined;
  if (value === null || value === undefined) return undefined;
  if (typeof value === "boolean" || typeof value === "number") return value;
  if (typeof value === "string") {
    const text = cleanText(value);
    if (!text) return undefined;
    if (key && ["query", "term", "search", "search_term"].includes(key)) return looksSensitive(text) ? "[redacted]" : text;
    if (key && /password|pass|token|secret|api[_-]?key|auth|credential|session|cookie|card|cvv|pin|account|routing|iban|bank/i.test(key)) return "[redacted]";
    if (looksSensitive(text)) return "[redacted]";
    return text;
  }
  if (Array.isArray(value)) {
    const items = value.slice(0, 8).map((item) => sanitizeValue(key, item, depth + 1)).filter((item) => item !== undefined);
    return items;
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    const out: Record<string, unknown> = {};
    for (const [rawKey, rawValue] of entries.slice(0, 16)) {
      const nextKey = normalizeKey(rawKey);
      if (!nextKey) continue;
      if (/password|pass|token|secret|api[_-]?key|auth|credential|session|cookie|card|cvv|pin|account|routing|iban|bank/i.test(nextKey)) {
        out[nextKey] = "[redacted]";
        continue;
      }
      const sanitized = sanitizeValue(nextKey, rawValue, depth + 1);
      if (sanitized !== undefined) out[nextKey] = sanitized;
    }
    return out;
  }
  return undefined;
}

function getRootSettings(): AnalyticsSettings {
  if (!isBrowser()) return { enabled: false, samplingRate: 0, devLogging: false };
  const root = document.getElementById("root");
  const enabled = root?.dataset.analyticsEnabled ?? "false";
  const samplingRate = root?.dataset.analyticsSamplingRate ?? "1";
  const devLogging = root?.dataset.analyticsDevLogging ?? "false";
  return {
    enabled: enabled === "true",
    samplingRate: Math.max(0, Math.min(1, Number(samplingRate) || 0)),
    devLogging: devLogging === "true",
  };
}

function getQueueState(): AnalyticsQueueState | null {
  if (!isBrowser()) return null;
  const settings = getRootSettings();
  if (!settings.enabled) return { settings, sampled: false, userId: "", sessionId: "", startedAt: new Date().toISOString() };

  const now = new Date().toISOString();
  let userId = "";
  try {
    userId = localStorage.getItem(STORAGE_USER_ID) || "";
    if (!userId) {
      userId = randomId();
      localStorage.setItem(STORAGE_USER_ID, userId);
    }
  } catch {
    userId = randomId();
  }

  try {
    const rawSession = sessionStorage.getItem(STORAGE_SESSION_KEY);
    if (rawSession) {
      const parsed = JSON.parse(rawSession) as AnalyticsQueueState;
      if (parsed?.sessionId) {
        return {
          settings,
          sampled: Boolean(parsed.sampled),
          userId,
          sessionId: parsed.sessionId,
          startedAt: parsed.startedAt || now,
        };
      }
    }
  } catch {
    // ignore bad or inaccessible session storage and rebuild.
  }

  const sampled = Math.random() < settings.samplingRate;
  const sessionState: AnalyticsQueueState = {
    settings,
    sampled,
    userId,
    sessionId: randomId(),
    startedAt: now,
  };
  try {
    sessionStorage.setItem(STORAGE_SESSION_KEY, JSON.stringify(sessionState));
  } catch {
    // ignore inaccessible storage; the current page session still works.
  }
  return sessionState;
}

function getSessionState() {
  const state = getQueueState();
  if (!state) return null;
  if (!state.settings.enabled || !state.sampled) return state;
  return state;
}

function currentPage() {
  if (!isBrowser()) return "/";
  return window.location.pathname || "/";
}

function scheduleFlush() {
  if (!isBrowser() || flushTimer !== null) return;
  flushTimer = window.setTimeout(() => {
    flushTimer = null;
    void flushAnalytics();
  }, 400);
}

async function flushAnalytics(force = false) {
  if (!isBrowser()) return;
  if (inFlight || queue.length === 0) return;
  const state = getSessionState();
  if (!state || !state.settings.enabled || !state.sampled) {
    queue = [];
    return;
  }

  const batch = queue;
  queue = [];
  inFlight = true;
  try {
    const payload = JSON.stringify({ events: batch });
    const useBeacon = force || document.visibilityState === "hidden";
    if (useBeacon && navigator.sendBeacon) {
      navigator.sendBeacon(ENDPOINT, new Blob([payload], { type: "application/json" }));
      return;
    }
    await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: payload,
      keepalive: true,
    });
  } catch {
    queue = batch.concat(queue);
  } finally {
    inFlight = false;
  }
}

export function trackEvent(input: AnalyticsEventInput) {
  if (!isBrowser()) return;
  const state = getSessionState();
  if (!state || !state.settings.enabled || !state.sampled) return;

  const event: AnalyticsEventPayload = {
    eventId: randomId(),
    userId: state.userId,
    sessionId: state.sessionId,
    eventType: normalizeKey(input.eventType) || "interaction",
    page: cleanText(input.page || currentPage(), 120) || "/",
    component: input.component ? cleanText(input.component, 80) : null,
    metadata: (sanitizeValue(null, input.metadata || {}) as AnalyticsMetadata) || {},
    ts: input.ts || new Date().toISOString(),
  };

  if (state.settings.devLogging) {
    console.debug("[analytics]", event.eventType, event.page, event.component, event.metadata);
  }

  queue.push(event);
  if (queue.length >= 8) {
    void flushAnalytics();
    return;
  }
  scheduleFlush();
}

export function useAnalytics(page?: string) {
  const pageRef = useRef(page || currentPage());
  const lastSearchRef = useRef<string>("");
  const sessionEndedRef = useRef(false);
  const [sessionState] = useState(() => getSessionState());
  const sessionStateRef = useRef(sessionState);

  useEffect(() => {
    sessionStateRef.current = sessionState;
  }, [sessionState]);

  useEffect(() => {
    pageRef.current = page || currentPage();
  }, [page]);

  useEffect(() => {
    const endSession = (reason: string) => {
      if (sessionEndedRef.current) return;
      sessionEndedRef.current = true;
      trackEvent({
        eventType: "session_ended",
        page: pageRef.current,
        component: "Analytics",
        metadata: { reason },
      });
      void flushAnalytics(true);
    };

    trackEvent({
      eventType: "session_started",
      page: pageRef.current,
      component: "Analytics",
      metadata: { startedAt: new Date().toISOString() },
    });
    trackEvent({
      eventType: "page_view",
      page: pageRef.current,
      component: "Analytics",
      metadata: { path: pageRef.current },
    });
    const onPageHide = () => {
      endSession("pagehide");
    };
    const onVisibilityChange = () => {
      if (document.visibilityState === "hidden") {
        endSession("visibility_hidden");
      }
    };
    window.addEventListener("pagehide", onPageHide);
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      endSession("unmount");
      window.removeEventListener("pagehide", onPageHide);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, []);

  const track = useCallback((input: Omit<AnalyticsEventInput, "page"> & { page?: string }) => {
    trackEvent({ ...input, page: input.page || pageRef.current });
  }, []);

  const trackButtonClick = useCallback(
    (component: string, action: string, metadata: AnalyticsMetadata = {}) => {
      track({ eventType: "button_clicked", component, metadata: { action, ...metadata } });
    },
    [track],
  );

  const trackNavigation = useCallback(
    (component: string, target: string, metadata: AnalyticsMetadata = {}) => {
      track({ eventType: "navigation_flow", component, metadata: { target, ...metadata } });
    },
    [track],
  );

  const trackFilterChange = useCallback(
    (filter: string, value: unknown, metadata: AnalyticsMetadata = {}) => {
      track({
        eventType: "filter_changed",
        component: "FiltersPanel",
        metadata: { filter, value, ...metadata },
      });
    },
    [track],
  );

  const trackSortChange = useCallback(
    (sortBy: string, sortDir: string, metadata: AnalyticsMetadata = {}) => {
      track({
        eventType: "sort_changed",
        component: "TransactionTable",
        metadata: { sort: sortBy, direction: sortDir, ...metadata },
      });
    },
    [track],
  );

  const trackCategorySelection = useCallback(
    (category: string, selected: boolean) => {
      track({
        eventType: "category_selected",
        component: "FiltersPanel",
        metadata: { category, selected },
      });
    },
    [track],
  );

  const trackTransactionDrilldown = useCallback(
    (metadata: AnalyticsMetadata = {}) => {
      track({
        eventType: "transaction_drilldown",
        component: "TransactionTable",
        metadata,
      });
    },
    [track],
  );

  const trackAssistantUsage = useCallback(
    (action: string, metadata: AnalyticsMetadata = {}) => {
      track({
        eventType: "assistant_used",
        component: "Assistant",
        metadata: { action, ...metadata },
      });
    },
    [track],
  );

  const trackModalChange = useCallback(
    (name: string, open: boolean, metadata: AnalyticsMetadata = {}) => {
      track({
        eventType: open ? "modal_opened" : "modal_closed",
        component: name,
        metadata,
      });
    },
    [track],
  );

  const trackSettingsChange = useCallback(
    (setting: string, value: unknown, metadata: AnalyticsMetadata = {}) => {
      track({
        eventType: "settings_changed",
        component: "FiltersPanel",
        metadata: { setting, value, ...metadata },
      });
    },
    [track],
  );

  const trackSearchSubmitted = useCallback(
    (query: string, metadata: AnalyticsMetadata = {}) => {
      const normalized = cleanText(query, 120);
      if (!normalized || normalized === lastSearchRef.current) return;
      lastSearchRef.current = normalized;
      track({
        eventType: "search_submitted",
        component: "FiltersPanel",
        metadata: { query: normalized, queryLength: normalized.length, ...metadata },
      });
    },
    [track],
  );

  const trackSearchZeroResults = useCallback(
    (query: string, metadata: AnalyticsMetadata = {}) => {
      const normalized = cleanText(query, 120);
      if (!normalized) return;
      track({
        eventType: "search_zero_results",
        component: "FiltersPanel",
        metadata: { query: normalized, queryLength: normalized.length, ...metadata },
      });
    },
    [track],
  );

  const trackSearchAbandoned = useCallback(
    (query: string, metadata: AnalyticsMetadata = {}) => {
      const normalized = cleanText(query, 120);
      if (!normalized) return;
      track({
        eventType: "search_abandoned",
        component: "FiltersPanel",
        metadata: { query: normalized, queryLength: normalized.length, ...metadata },
      });
    },
    [track],
  );

  return useMemo(
    () => ({
      trackEvent: track,
      trackButtonClick,
      trackNavigation,
      trackFilterChange,
      trackSortChange,
      trackCategorySelection,
      trackTransactionDrilldown,
      trackAssistantUsage,
      trackModalChange,
      trackSettingsChange,
      trackSearchSubmitted,
      trackSearchZeroResults,
      trackSearchAbandoned,
      flushAnalytics: () => flushAnalytics(true),
      enabled: sessionStateRef.current?.settings.enabled ?? false,
    }),
    [
      track,
      trackButtonClick,
      trackNavigation,
      trackFilterChange,
      trackSortChange,
      trackCategorySelection,
      trackTransactionDrilldown,
      trackAssistantUsage,
      trackModalChange,
      trackSettingsChange,
      trackSearchSubmitted,
      trackSearchZeroResults,
      trackSearchAbandoned,
    ],
  );
}
