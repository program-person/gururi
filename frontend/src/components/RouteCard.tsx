"use client";

import { useState } from "react";
import Link from "next/link";
import { OmawariRoute } from "@/lib/api";
import { SearchQuery, timetableHref } from "@/lib/searchQuery";
import RouteMap, { LINE_COLORS } from "./RouteMap";

interface Props {
  route: OmawariRoute;
  rank: number;
  stationMap: Record<string, string>;
  lineMap: Record<string, string>;
  stationGeo: Record<string, { lat: number; lng: number }>;
  /** 乗換案内ページへのリンク生成用。未実行なら null */
  query: SearchQuery | null;
  routeIndex: number;
}

const DEFAULT_COLOR = "#6b7280";

/** 路線の使用順リスト（連続する同一路線はまとめる） */
function usedLineSequence(path: OmawariRoute["path"]): string[] {
  const seq: string[] = [];
  for (const seg of path.slice(1)) {
    if (seg.lineId && seg.lineId !== seq[seq.length - 1]) {
      seq.push(seg.lineId);
    }
  }
  return seq;
}

function nowHHMM(): string {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export default function RouteCard({
  route, rank, stationMap, lineMap, stationGeo, query, routeIndex,
}: Props) {
  const [showMap, setShowMap] = useState(false);
  const [showStations, setShowStations] = useState(false);

  const start = stationMap[route.path[0]?.stationId] ?? route.path[0]?.stationId;
  const end   = stationMap[route.path.at(-1)?.stationId ?? ""] ?? route.path.at(-1)?.stationId;

  const hh = Math.floor(route.totalTime / 60);
  const mm = Math.round(route.totalTime % 60);
  const timeStr = hh > 0 ? `${hh}時間${mm > 0 ? `${mm}分` : ""}` : `${mm}分`;

  const lineSeq = usedLineSequence(route.path);
  const transferCount = lineSeq.length - 1;

  // 乗換駅インデックスを計算
  const xferIndices = new Set<number>();
  for (let i = 1; i < route.path.length - 1; i++) {
    if (route.path[i].lineId && route.path[i + 1]?.lineId &&
        route.path[i].lineId !== route.path[i + 1].lineId) {
      xferIndices.add(i);
    }
  }

  return (
    <div className="group relative overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition-shadow duration-200 hover:shadow-[0_1px_2px_rgba(15,23,42,0.04),0_12px_28px_-16px_rgba(15,23,42,0.25)] dark:border-slate-700/80 dark:bg-slate-800">
      {/* 経由する路線の色を上から順に並べた帯（どの路線を乗り継ぐか一目で分かる） */}
      <div className="absolute inset-y-0 left-0 flex w-1.5 flex-col" aria-hidden="true">
        {lineSeq.map((lid, i) => (
          <span key={i} className="flex-1" style={{ backgroundColor: LINE_COLORS[lid] ?? DEFAULT_COLOR }} />
        ))}
      </div>

      {/* ヘッダー */}
      <div className="pl-4 sm:pl-5 pr-3 sm:pr-4 pt-4 pb-3">
        {/* 順位・起終点 */}
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mb-2.5">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-slate-900 font-mono text-xs font-bold tabular-nums text-white dark:bg-white dark:text-slate-900">
            {rank}
          </span>
          <span className="text-[15px] font-bold tracking-tight text-slate-900 dark:text-white">
            {start}
          </span>
          <span className="text-gray-400 dark:text-gray-500 text-sm">→</span>
          <span className="text-[15px] font-bold tracking-tight text-slate-900 dark:text-white">
            {end}
          </span>
          {transferCount > 0 && (
            <span className="ml-auto shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-500 dark:bg-slate-700/60 dark:text-slate-300">
              乗換 {transferCount}回
            </span>
          )}
        </div>

        {/* 路線バッジ列: JRの案内サインに倣い、路線記号を色付きの丸で先頭に置く */}
        <div className="flex flex-wrap items-center gap-1.5 mb-3">
          {lineSeq.map((lid, i) => (
            <span key={i} className="flex items-center gap-1.5">
              <span className="inline-flex items-center gap-1 rounded-full border border-gray-200 dark:border-gray-600 py-0.5 pl-0.5 pr-2">
                <span
                  className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white"
                  style={{ backgroundColor: LINE_COLORS[lid] ?? DEFAULT_COLOR }}
                >
                  {lid}
                </span>
                <span className="text-xs font-medium whitespace-nowrap text-gray-700 dark:text-gray-200">
                  {lineMap[lid] ?? lid}
                </span>
              </span>
              {i < lineSeq.length - 1 && (
                <span className="text-gray-300 dark:text-gray-600 text-xs">›</span>
              )}
            </span>
          ))}
        </div>

        {/* 数値サマリー: 駅の案内表示のように罫線で等分した情報帯 */}
        <div className="grid grid-cols-4 divide-x divide-slate-200/70 overflow-hidden rounded-xl bg-slate-50 text-center dark:divide-slate-700 dark:bg-slate-900/40">
          <div className="py-2">
            <p className="text-[10px] font-medium tracking-wide text-slate-400 dark:text-slate-500">駅数</p>
            <p className="font-mono text-lg font-bold tabular-nums text-blue-700 dark:text-blue-400">{route.stationCount}</p>
          </div>
          <div className="py-2">
            <p className="text-[10px] font-medium tracking-wide text-slate-400 dark:text-slate-500">距離</p>
            <p className="font-mono text-lg font-bold tabular-nums text-slate-900 dark:text-slate-100">
              {route.totalDistance}<span className="ml-0.5 font-sans text-[10px] font-normal text-slate-400">km</span>
            </p>
          </div>
          <div className="py-2">
            <p className="text-[10px] font-medium tracking-wide text-slate-400 dark:text-slate-500">所要時間</p>
            {/* 「3時間52分」が折り返して他のタイルと高さがずれるため、狭い画面では一段小さく */}
            <p className="font-mono text-[13px] sm:text-base font-bold tabular-nums whitespace-nowrap text-slate-900 dark:text-slate-100">{timeStr}</p>
          </div>
          <div className="py-2">
            <p className="text-[10px] font-medium tracking-wide text-slate-400 dark:text-slate-500">運賃(IC)</p>
            <p className="font-mono text-lg font-bold tabular-nums text-emerald-600 dark:text-emerald-400">
              {route.fareIc}<span className="ml-0.5 font-sans text-[10px] font-normal text-emerald-600/70 dark:text-emerald-400/70">円</span>
            </p>
          </div>
        </div>
      </div>

      {/* アクション */}
      <div className="flex flex-wrap gap-2 border-t border-slate-100 py-2 pl-4 pr-3 sm:pl-5 sm:pr-4 dark:border-slate-700/70">
        <button
          onClick={() => setShowMap((v) => !v)}
          className={`min-h-10 whitespace-nowrap rounded-md px-3 py-1.5 text-[13px] sm:text-xs font-medium transition-colors ${
            showMap
              ? "bg-blue-700 text-white shadow-sm"
              : "border border-slate-200 text-slate-600 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 dark:border-slate-600 dark:text-slate-300 dark:hover:border-blue-700 dark:hover:bg-blue-900/30 dark:hover:text-blue-300"
          }`}
        >
          {showMap ? "ルート図を閉じる" : "ルート図"}
        </button>

        <button
          onClick={() => setShowStations((v) => !v)}
          className={`min-h-10 whitespace-nowrap rounded-md px-3 py-1.5 text-[13px] sm:text-xs font-medium transition-colors ${
            showStations
              ? "bg-slate-700 text-white shadow-sm"
              : "border border-slate-200 text-slate-600 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
          }`}
        >
          {showStations ? "駅一覧を閉じる" : `駅一覧（${route.path.length}駅）`}
        </button>

        {query && (
          <Link
            href={timetableHref(query, routeIndex, nowHHMM())}
            className="min-h-10 flex items-center whitespace-nowrap rounded-md border border-slate-200 px-3 py-1.5 text-[13px] sm:text-xs font-medium text-slate-600 transition-colors hover:border-emerald-300 hover:bg-emerald-50 hover:text-emerald-700 dark:border-slate-600 dark:text-slate-300 dark:hover:border-emerald-700 dark:hover:bg-emerald-900/30 dark:hover:text-emerald-300"
          >
            乗換案内 →
          </Link>
        )}
      </div>

      {/* ルート図 */}
      {showMap && (
        <div className="border-t border-gray-100 dark:border-gray-700 pl-1.5">
          <RouteMap route={route} stationMap={stationMap} lineMap={lineMap} stationGeo={stationGeo} />
        </div>
      )}

      {/* 駅一覧 */}
      {showStations && (
        <div className="border-t border-gray-100 dark:border-gray-700 pl-4 sm:pl-5 pr-3 sm:pr-4 py-3">
          <div className="flex flex-col gap-0.5 text-xs">
            {route.path.map((seg, i) => {
              const sname = stationMap[seg.stationId] ?? seg.stationId;
              const isStart = i === 0;
              const isEnd = i === route.path.length - 1;
              const isXfer = xferIndices.has(i);
              const lineColor = LINE_COLORS[seg.lineId] ?? DEFAULT_COLOR;

              return (
                <div key={i} className="flex items-center gap-2">
                  {/* 路線カラーバー */}
                  <div
                    className="w-1 shrink-0 rounded-full"
                    style={{
                      height: "20px",
                      backgroundColor: isStart ? "#22c55e" : isEnd ? "#ef4444" : lineColor,
                    }}
                  />
                  {/* 駅名 */}
                  <span className={`${
                    isStart || isEnd
                      ? "font-bold text-gray-900 dark:text-white"
                      : isXfer
                      ? "font-semibold text-amber-600 dark:text-amber-400"
                      : "text-gray-600 dark:text-gray-400"
                  }`}>
                    {sname}
                  </span>
                  {/* 乗換バッジ */}
                  {isXfer && (
                    <span className="rounded bg-amber-100 dark:bg-amber-900/40 px-1 py-0 text-amber-700 dark:text-amber-300">
                      乗換
                    </span>
                  )}
                  {isStart && (
                    <span className="rounded bg-green-100 dark:bg-green-900/40 px-1 py-0 text-green-700 dark:text-green-300">
                      出発
                    </span>
                  )}
                  {isEnd && (
                    <span className="rounded bg-red-100 dark:bg-red-900/40 px-1 py-0 text-red-700 dark:text-red-300">
                      到着
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
