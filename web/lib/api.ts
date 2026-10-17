import type { Alerts, Health, Report, Trend } from "./types";

export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
).replace(/\/+$/, "");

export const FIXTURES_BY_DEFAULT =
  process.env.NEXT_PUBLIC_USE_FIXTURES === "true";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly kind: "unreachable" | "status",
    readonly status?: number,
  ) {
    super(message);
  }
}

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ApiError(
      `The Knockout API at ${API_URL} did not answer.`,
      "unreachable",
    );
  }
  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json();
      detail = typeof body?.detail === "string" ? body.detail : "";
    } catch {}
    throw new ApiError(
      detail || `The API answered ${response.status} for ${path}.`,
      "status",
      response.status,
    );
  }
  return response.json() as Promise<T>;
}

const drugPath = (name: string) =>
  `/api/drugs/${encodeURIComponent(name.trim().toLowerCase())}`;

export const fetchReport = (
  name: string,
  options: { refresh?: boolean; signal?: AbortSignal } = {},
) =>
  getJson<Report>(
    `${drugPath(name)}/report${options.refresh ? "?refresh=true" : ""}`,
    { signal: options.signal },
  );

export const fetchTrend = (name: string, signal?: AbortSignal) =>
  getJson<Trend>(`${drugPath(name)}/trend`, { signal });

export const fetchAlerts = (name: string, signal?: AbortSignal) =>
  getJson<Alerts>(`${drugPath(name)}/alerts`, { signal });

export const fetchHealth = (signal?: AbortSignal) =>
  getJson<Health>("/api/health", { signal });

export const fetchWatchlist = (signal?: AbortSignal) =>
  getJson<{ drugs: string[] }>("/api/watchlist", { signal });

export const addToWatchlist = (drug: string) =>
  getJson<{ drugs: string[] }>("/api/watchlist", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ drug: drug.trim().toLowerCase() }),
  });
