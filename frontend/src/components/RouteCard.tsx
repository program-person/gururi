"use client";

import { useState } from "react";
import { OmawariRoute } from "@/lib/api";
import RouteMap, { LINE_COLORS } from "./RouteMap";

interface Props {
  route: OmawariRoute;
  rank: number;
  stationMap: Record<string, string>;
  lineMap: Record<string, string>;
  stationGeo: Record<string, { lat: number; lng: number }>;
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

export default function RouteCard({ route, rank, stationMap, lineMap, stationGeo }: Props) {
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
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm overflow-hidden">
      {/* ヘッダー */}
      <div className="px-4 pt-4 pb-3">
        {/* 順位・起終点 */}
        <div className="flex items-center gap-2 mb-2">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
            {rank}
          </span>
          <span className="font-semibold text-gray-900 dark:text-white">
            {start}
          </span>
          <span className="text-gray-400 dark:text-gray-500 text-sm">→</span>
          <span className="font-semibold text-gray-900 dark:text-white">
            {end}
          </span>
          {transferCount > 0 && (
            <span className="ml-auto shrink-0 text-xs text-gray-400 dark:text-gray-500">
              乗換 {transferCount}回
            </span>
          )}
        </div>

        {/* 路線バッジ列 */}
        <div className="flex flex-wrap items-center gap-1 mb-3">
          {lineSeq.map((lid, i) => (
            <span key={i} className="flex items-center gap-1">
              <span
                className="rounded-full px-2 py-0.5 text-xs font-semibold text-white whitespace-nowrap"
                style={{ backgroundColor: LINE_COLORS[lid] ?? DEFAULT_COLOR }}
              >
                {lineMap[lid] ?? lid}
              </span>
              {i < lineSeq.length - 1 && (
                <span className="text-gray-300 dark:text-gray-600 text-xs">›</span>
              )}
            </span>
          ))}
        </div>

        {/* 数値サマリー */}
        <div className="grid grid-cols-4 gap-2 text-center">
          <div className="rounded-lg bg-gray-50 dark:bg-gray-700/50 py-2">
            <p className="text-xs text-gray-400 dark:text-gray-500">駅数</p>
            <p className="text-lg font-bold text-blue-600 dark:text-blue-400">{route.stationCount}</p>
          </div>
          <div className="rounded-lg bg-gray-50 dark:bg-gray-700/50 py-2">
            <p className="text-xs text-gray-400 dark:text-gray-500">距離</p>
            <p className="text-lg font-bold text-gray-900 dark:text-gray-100">
              {route.totalDistance}<span className="text-xs font-normal">km</span>
            </p>
          </div>
          <div className="rounded-lg bg-gray-50 dark:bg-gray-700/50 py-2">
            <p className="text-xs text-gray-400 dark:text-gray-500">所要時間</p>
            <p className="text-base font-bold text-gray-900 dark:text-gray-100">{timeStr}</p>
          </div>
          <div className="rounded-lg bg-gray-50 dark:bg-gray-700/50 py-2">
            <p className="text-xs text-gray-400 dark:text-gray-500">運賃(IC)</p>
            <p className="text-lg font-bold text-emerald-600 dark:text-emerald-400">
              {route.fareIc}<span className="text-xs font-normal">円</span>
            </p>
          </div>
        </div>
      </div>

      {/* アクション */}
      <div className="flex gap-2 border-t border-gray-100 dark:border-gray-700 px-4 py-2">
        <button
          onClick={() => setShowMap((v) => !v)}
          className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
            showMap
              ? "bg-blue-600 text-white"
              : "border border-blue-300 dark:border-blue-700 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/30"
          }`}
        >
          {showMap ? "ルート図を閉じる" : "ルート図"}
        </button>

        <button
          onClick={() => setShowStations((v) => !v)}
          className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
            showStations
              ? "bg-gray-600 text-white"
              : "border border-gray-300 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700"
          }`}
        >
          {showStations ? "駅一覧を閉じる" : `駅一覧（${route.path.length}駅）`}
        </button>
      </div>

      {/* ルート図 */}
      {showMap && (
        <div className="border-t border-gray-100 dark:border-gray-700">
          <RouteMap route={route} stationMap={stationMap} lineMap={lineMap} stationGeo={stationGeo} />
        </div>
      )}

      {/* 駅一覧 */}
      {showStations && (
        <div className="border-t border-gray-100 dark:border-gray-700 px-4 py-3">
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
