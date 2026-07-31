"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api, OmawariRoute, TimetableResponse } from "@/lib/api";
import { fromSearchParams, runSearch, searchHref } from "@/lib/searchQuery";
import { useRailData } from "@/lib/useRailData";
import { LINE_COLORS } from "@/components/RouteMap";

const DEFAULT_COLOR = "#6b7280";
const MINUTES_PER_DAY = 24 * 60;

function formatDuration(totalMin: number): string {
  const hours = Math.floor(totalMin / 60);
  const minutes = Math.round(totalMin % 60);
  if (hours === 0) return `${minutes}分`;
  return minutes > 0 ? `${hours}時間${minutes}分` : `${hours}時間`;
}

/** 出発時刻＋所要時間が日付をまたぐ日数。0なら当日中。 */
function dayOffset(departTime: string, totalMin: number): number {
  const [hh, mm] = departTime.split(":").map((v) => Number.parseInt(v, 10));
  if (!Number.isFinite(hh) || !Number.isFinite(mm)) return 0;
  return Math.floor((hh * 60 + mm + totalMin) / MINUTES_PER_DAY);
}

export default function TimetablePage() {
  // useSearchParams はプリレンダリング時に Suspense 境界を要求する
  return (
    <Suspense>
      <Timetable />
    </Suspense>
  );
}

interface Keyed<T> {
  /** どの入力に対する結果か。現在の値と一致しない間が「取得中」 */
  key: string;
  value: T | null;
  error: string | null;
}

const NOT_LOADED: Keyed<never> = { key: "", value: null, error: null };

function Timetable() {
  const searchParams = useSearchParams();
  const { stationMap, lineMap } = useRailData();

  const queryString = searchParams.toString();
  const query = useMemo(
    () => fromSearchParams(new URLSearchParams(queryString)),
    [queryString]
  );
  const routeIndex = Number.parseInt(searchParams.get("i") ?? "0", 10);
  const urlDepartTime = searchParams.get("depart") ?? "";

  // 「検索」を押した出発時刻。押すまではURL由来の値で取得する
  const [submittedDepartTime, setSubmittedDepartTime] = useState<string | null>(null);
  const departTime = submittedDepartTime ?? urlDepartTime;
  // 入力欄の下書き。取得対象の departTime とは別に持つ
  const [draftDepartTime, setDraftDepartTime] = useState<string | null>(null);
  const departInput = draftDepartTime ?? departTime;

  // ルート取得（0.4秒程度）とダイヤ照会（区間ごとに外部APIを叩くので十数秒）は
  // 所要時間の桁が違うので、状態を分けてルート概要だけ先に出す
  const routeKey = `${queryString}|${routeIndex}`;
  const [loadedRoute, setLoadedRoute] = useState<Keyed<OmawariRoute>>(NOT_LOADED);
  const routeResult = loadedRoute.key === routeKey ? loadedRoute : NOT_LOADED;
  const route: OmawariRoute | null = routeResult.value;

  const timetableKey = `${routeKey}|${departTime}`;
  const [loadedTimetable, setLoadedTimetable] = useState<Keyed<TimetableResponse>>(NOT_LOADED);
  const timetableResult = loadedTimetable.key === timetableKey ? loadedTimetable : NOT_LOADED;
  const timetable: TimetableResponse | null = timetableResult.value;

  const loading =
    query !== null &&
    departTime !== "" &&
    routeResult.error === null &&
    timetableResult.key !== timetableKey;
  const error =
    query === null
      ? "URLに検索条件が含まれていません。検索ページからやり直してください。"
      : routeResult.error ?? timetableResult.error;

  // 探索はシード固定なので、検索結果ページと同じ条件で同じルートが取り直せる。
  // ルート本体（最大216駅）をURLに載せずに済ませるための仕組み
  useEffect(() => {
    if (query === null) return;
    let cancelled = false;
    runSearch(query)
      .then((routes) => {
        if (cancelled) return;
        const found = routes[routeIndex];
        setLoadedRoute({
          key: routeKey,
          value: found ?? null,
          error: found
            ? null
            : "このURLのルートを再現できませんでした。探索アルゴリズムかダイヤデータが更新された可能性があります。",
        });
      })
      .catch((e) => {
        if (cancelled) return;
        setLoadedRoute({
          key: routeKey,
          value: null,
          error: e instanceof Error ? e.message : "ルートの取得に失敗しました",
        });
      });
    return () => { cancelled = true; };
  }, [routeKey, query, routeIndex]);

  useEffect(() => {
    if (route === null || !departTime) return;
    let cancelled = false;
    api
      .timetable(route.path, departTime)
      .then((result) => {
        if (!cancelled) setLoadedTimetable({ key: timetableKey, value: result, error: null });
      })
      .catch((e) => {
        if (cancelled) return;
        setLoadedTimetable({
          key: timetableKey,
          value: null,
          error: e instanceof Error ? e.message : "時刻表の取得に失敗しました",
        });
      });
    return () => { cancelled = true; };
  }, [timetableKey, route, departTime]);

  const startName = route ? stationMap[route.path[0].stationId] ?? route.path[0].stationId : "";
  const endName = route
    ? stationMap[route.path[route.path.length - 1].stationId] ??
      route.path[route.path.length - 1].stationId
    : "";
  const crossesDay = timetable ? dayOffset(timetable.departTime, timetable.totalMin) : 0;

  return (
    <main className="mx-auto max-w-3xl px-3 py-5 sm:px-4 sm:py-8">
      <Link
        href={query ? searchHref(query) : "/"}
        className="mb-4 inline-flex items-center gap-1 text-sm text-slate-500 transition-colors hover:text-blue-700 dark:text-slate-400 dark:hover:text-blue-400"
      >
        ← 検索結果に戻る
      </Link>

      <h1 className="text-[22px] font-bold leading-tight tracking-[-0.02em] text-slate-900 sm:text-[28px] dark:text-white">
        乗換案内
      </h1>

      {route && (
        <p className="mt-1.5 flex flex-wrap items-baseline gap-x-2 text-sm text-slate-500 dark:text-slate-400">
          <span className="font-semibold text-slate-900 dark:text-white">{startName}</span>
          <span>→</span>
          <span className="font-semibold text-slate-900 dark:text-white">{endName}</span>
          <span className="font-mono text-xs tabular-nums">
            {route.stationCount}駅 / {route.totalDistance}km / 運賃{route.fareIc}円
          </span>
        </p>
      )}

      {/* 出発時刻 */}
      <div className="mt-5 flex flex-wrap items-center gap-2 rounded-xl border border-slate-200/80 bg-white/90 p-4 dark:border-slate-700/80 dark:bg-slate-800/90">
        <label className="text-xs font-semibold tracking-wide text-slate-500 dark:text-slate-400">
          出発時刻
        </label>
        <input
          type="time"
          value={departInput}
          onChange={(e) => setDraftDepartTime(e.target.value)}
          className="min-h-10 rounded-lg border border-slate-300 bg-white px-2 py-1 text-base text-slate-900 sm:text-sm dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100"
        />
        <button
          onClick={() => setSubmittedDepartTime(departInput)}
          disabled={loading || !departInput || !route}
          className="min-h-10 whitespace-nowrap rounded-lg bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400 dark:disabled:bg-slate-700 dark:disabled:text-slate-500"
        >
          時刻を検索
        </button>
      </div>

      {error && (
        <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-900/30 dark:text-red-300">
          {error}
        </div>
      )}

      {loading && (
        <div className="mt-4 flex items-center gap-2 rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
          <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
          </svg>
          {/* 区間ごとに外部の乗換案内APIを叩くため、長いルートでは十数秒かかる */}
          区間ごとにダイヤを照会中… 長いルートでは十数秒かかります
        </div>
      )}

      {timetable && !loading && (
        <div className="mt-4">
          {/* サマリー */}
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 rounded-xl border border-slate-200/80 bg-white/90 p-4 dark:border-slate-700/80 dark:bg-slate-800/90">
            <span className="text-lg font-bold tabular-nums text-slate-900 dark:text-white">
              {timetable.departTime}発
            </span>
            <span className="text-slate-400">→</span>
            <span className="text-lg font-bold tabular-nums text-slate-900 dark:text-white">
              {timetable.arrivalTime}着
            </span>
            {crossesDay > 0 && (
              <span className="rounded bg-slate-900 px-1.5 py-0.5 text-xs font-semibold text-white dark:bg-white dark:text-slate-900">
                {crossesDay === 1 ? "翌日" : `${crossesDay}日後`}
              </span>
            )}
            <span className="text-sm text-slate-500 dark:text-slate-400">
              （{formatDuration(timetable.totalMin)}）
            </span>
          </div>

          {crossesDay > 0 && (
            <p className="mt-2 rounded-lg bg-red-50 p-2.5 text-xs leading-relaxed text-red-700 dark:bg-red-900/30 dark:text-red-300">
              ⚠ 日付をまたぎます。大回り乗車は当日中に下車するのが条件のため、この旅程は成立しません。出発時刻を早めるか、より短いルートを選んでください。
            </p>
          )}

          {timetable.hasEstimate && (
            <p className="mt-2 rounded-lg bg-amber-50 p-2.5 text-xs leading-relaxed text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
              ⚠ 「目安」の区間はダイヤ未収録路線（奈良線・関西空港線・JR東西線など）または取得失敗のため、運転間隔からの推定時間です
            </p>
          )}

          {/* レッグ一覧 */}
          <ol className="mt-3 flex flex-col gap-2">
            {timetable.legs.map((leg, i) => {
              const fromName = stationMap[leg.fromStationId] ?? leg.fromStationId;
              const toName = stationMap[leg.toStationId] ?? leg.toStationId;
              const lineColor = LINE_COLORS[leg.lineId] ?? DEFAULT_COLOR;
              return (
                <li
                  key={i}
                  className="flex items-stretch gap-2.5 rounded-lg border border-slate-200/80 bg-white/90 p-3 dark:border-slate-700/80 dark:bg-slate-800/90"
                >
                  <div className="w-1 shrink-0 rounded-full" style={{ backgroundColor: lineColor }} />
                  <div className="min-w-0 flex-1 text-sm">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                      <span className="font-bold tabular-nums text-slate-900 dark:text-white">
                        {leg.departure}
                      </span>
                      <span className="font-semibold text-slate-800 dark:text-slate-200">{fromName}</span>
                      <span className="text-slate-400">→</span>
                      <span className="font-bold tabular-nums text-slate-900 dark:text-white">
                        {leg.arrival}
                      </span>
                      <span className="font-semibold text-slate-800 dark:text-slate-200">{toName}</span>
                      {leg.source === "estimate" && (
                        <span className="rounded bg-amber-100 px-1 py-0 text-xs text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
                          目安
                        </span>
                      )}
                    </div>
                    <div className="mt-0.5 text-xs text-slate-400 dark:text-slate-500">
                      {lineMap[leg.lineId] ?? leg.lineId}
                      {leg.headsign ? ` ${leg.headsign}` : leg.trainType ? ` ${leg.trainType}` : ""}
                      ・乗車{Math.round(leg.rideMin)}分
                      {leg.waitMin > 0 && `・待ち${Math.round(leg.waitMin)}分`}
                    </div>
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      )}
    </main>
  );
}
