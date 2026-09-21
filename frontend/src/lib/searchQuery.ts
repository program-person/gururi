/** 検索条件のURL表現。
 *
 * 大回り探索はランダムウォークなので、同じ条件でも呼ぶたびに結果が変わる。
 * 条件とシードをURLに載せて乗換案内ページ側で同じ探索をやり直すことで、
 * 「巨大なルートをURLに詰め込む」ことなくルートを一意に指せるようにしている。
 * ブラウザバック・リロード・URL共有もこの仕組みでそのまま動く。
 */
import { api, OmawariRoute } from "./api";

export type Mode = "free" | "fare" | "dest";

export interface SearchQuery {
  mode: Mode;
  startStationId: string;
  endStationId: string | null;
  maxFare: number;
  maxTimeMin: number;
  numResults: number;
  /** 探索の再現用シード。バックエンドの上限は 2^31-1 */
  seed: number;
}

export const MAX_SEED = 2 ** 31 - 1;

export const DEFAULT_QUERY: Omit<SearchQuery, "startStationId" | "seed"> = {
  mode: "free",
  endStationId: null,
  maxFare: 180,
  maxTimeMin: 240,
  numResults: 5,
};

export function makeSeed(): number {
  return Math.floor(Math.random() * (MAX_SEED + 1));
}

function parseIntParam(raw: string | null, fallback: number): number {
  if (raw === null) return fallback;
  const value = Number.parseInt(raw, 10);
  return Number.isFinite(value) ? value : fallback;
}

export function toSearchParams(query: SearchQuery): URLSearchParams {
  const params = new URLSearchParams({
    mode: query.mode,
    start: query.startStationId,
    time: String(query.maxTimeMin),
    n: String(query.numResults),
    seed: String(query.seed),
  });
  if (query.mode === "dest" && query.endStationId) {
    params.set("end", query.endStationId);
  }
  if (query.mode === "fare") {
    params.set("fare", String(query.maxFare));
  }
  return params;
}

/** URL から検索条件を復元する。出発駅が無い（＝未検索）なら null。 */
export function fromSearchParams(params: URLSearchParams): SearchQuery | null {
  const startStationId = params.get("start");
  if (!startStationId) return null;

  const rawMode = params.get("mode");
  const mode: Mode =
    rawMode === "fare" || rawMode === "dest" || rawMode === "free" ? rawMode : "free";

  return {
    mode,
    startStationId,
    endStationId: params.get("end"),
    maxFare: parseIntParam(params.get("fare"), DEFAULT_QUERY.maxFare),
    maxTimeMin: parseIntParam(params.get("time"), DEFAULT_QUERY.maxTimeMin),
    numResults: parseIntParam(params.get("n"), DEFAULT_QUERY.numResults),
    seed: parseIntParam(params.get("seed"), 0),
  };
}

export function runSearch(query: SearchQuery): Promise<OmawariRoute[]> {
  if (query.mode === "fare") {
    return api.omawariByFare(query.startStationId, query.maxFare, {
      maxTimeMin: query.maxTimeMin,
      numResults: query.numResults,
      seed: query.seed,
    });
  }
  return api.omawari(query.startStationId, {
    endStationId: query.mode === "dest" ? (query.endStationId ?? undefined) : undefined,
    maxTimeMin: query.maxTimeMin,
    numResults: query.numResults,
    seed: query.seed,
  });
}

const HHMM_RE = /^([01]?\d|2[0-3]):[0-5]\d$/;

/** 着時刻の上書き（駅ID -> "HH:MM"）。ダイヤ未収録区間のユーザー入力。 */
export type ArrivalOverrides = Record<string, string>;

/**
 * 上書きを URL の `arr` パラメータに詰める。形式は `駅ID:HH:MM` のカンマ区切り。
 *
 * 駅IDは英数字のみ（graph.json の全374駅で確認済み）なので、最初の `:` で
 * 分割すれば時刻側の `:` と衝突しない。レッグ番号ではなく駅IDをキーにしているのは、
 * 探索アルゴリズムやグラフデータが更新されてもレッグの切れ目がズレないため
 * （大回りは同一駅を再訪しないので、1ルート内で駅IDは一意）。
 */
export function encodeArrivalOverrides(overrides: ArrivalOverrides): string {
  return Object.entries(overrides)
    .filter(([stationId, time]) => stationId !== "" && HHMM_RE.test(time))
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)) // URLを安定させて無駄な再取得を防ぐ
    .map(([stationId, time]) => `${stationId}:${time}`)
    .join(",");
}

/** `arr` パラメータを読む。壊れたエントリは黙って捨てる（共有URLを落とさない）。 */
export function decodeArrivalOverrides(raw: string | null): ArrivalOverrides {
  if (!raw) return {};
  const out: ArrivalOverrides = {};
  for (const entry of raw.split(",")) {
    const sep = entry.indexOf(":");
    if (sep <= 0) continue;
    const stationId = entry.slice(0, sep);
    const time = entry.slice(sep + 1);
    if (HHMM_RE.test(time)) out[stationId] = time;
  }
  return out;
}

/** 乗換案内ページのURL。検索条件 + ルート番号 + 出発時刻 + 着時刻の上書き。 */
export function timetableHref(
  query: SearchQuery,
  routeIndex: number,
  departTime: string,
  arrivalOverrides: ArrivalOverrides = {}
): string {
  const params = toSearchParams(query);
  params.set("i", String(routeIndex));
  params.set("depart", departTime);
  const arr = encodeArrivalOverrides(arrivalOverrides);
  if (arr) params.set("arr", arr);
  return `/timetable?${params}`;
}

/** 検索結果ページのURL。 */
export function searchHref(query: SearchQuery): string {
  return `/?${toSearchParams(query)}`;
}
