const BASE =
  typeof window === "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : "/api";

export interface Station {
  id: string;
  name: string;
  lat?: number;
  lng?: number;
}

export interface Line {
  id: string;
  name: string;
}

export interface PathSegment {
  stationId: string;
  lineId: string;
}

export interface RouteResponse {
  totalDistance: number;
  totalTime: number;
  path: PathSegment[];
}

export interface OmawariRoute {
  path: PathSegment[];
  totalDistance: number;
  totalTime: number;
  stationCount: number;
  directKm: number;
  fareIc: number;
}

export interface FareResponse {
  directKm: number;
  fareIc: number;
  fareTicket: number;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? res.statusText);
  }
  return res.json();
}

export const api = {
  stations: (): Promise<Station[]> => get("/stations"),

  lines: (): Promise<Line[]> => get("/lines"),

  route: (
    startStationId: string,
    endStationId: string,
    by: "time" | "distance" = "time"
  ): Promise<RouteResponse> =>
    get(`/route?startStationId=${encodeURIComponent(startStationId)}&endStationId=${encodeURIComponent(endStationId)}&by=${by}`),

  fare: (fromStationId: string, toStationId: string): Promise<FareResponse> =>
    get(`/fare?fromStationId=${encodeURIComponent(fromStationId)}&toStationId=${encodeURIComponent(toStationId)}`),

  omawari: (
    startStationId: string,
    opts: { endStationId?: string; maxTimeMin?: number; maxStations?: number; numResults?: number } = {}
  ): Promise<OmawariRoute[]> => {
    const p = new URLSearchParams({ startStationId });
    if (opts.endStationId) p.set("endStationId", opts.endStationId);
    if (opts.maxTimeMin) p.set("maxTimeMin", String(opts.maxTimeMin));
    if (opts.maxStations) p.set("maxStations", String(opts.maxStations));
    if (opts.numResults) p.set("numResults", String(opts.numResults));
    return get(`/omawari?${p}`);
  },

  omawariByFare: (
    startStationId: string,
    maxFare: number,
    opts: { maxTimeMin?: number; numResults?: number } = {}
  ): Promise<OmawariRoute[]> => {
    const p = new URLSearchParams({ startStationId, maxFare: String(maxFare) });
    if (opts.maxTimeMin) p.set("maxTimeMin", String(opts.maxTimeMin));
    if (opts.numResults) p.set("numResults", String(opts.numResults));
    return get(`/omawari/by-fare?${p}`);
  },
};
