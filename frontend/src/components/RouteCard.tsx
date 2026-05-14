"use client";

import { useState } from "react";
import { OmawariRoute } from "@/lib/api";
import RouteMap from "./RouteMap";

interface Props {
  route: OmawariRoute;
  rank: number;
  stationMap: Record<string, string>;
  lineMap: Record<string, string>;
}

export default function RouteCard({ route, rank, stationMap, lineMap }: Props) {
  const [showMap, setShowMap] = useState(false);

  const start = stationMap[route.path[0]?.stationId] ?? route.path[0]?.stationId;
  const end   = stationMap[route.path.at(-1)?.stationId ?? ""] ?? route.path.at(-1)?.stationId;

  const hh = Math.floor(route.totalTime / 60);
  const mm = Math.round(route.totalTime % 60);
  const timeStr = hh > 0 ? `${hh}時間${mm}分` : `${mm}分`;

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      {/* ヘッダー行 */}
      <div className="mb-2 flex items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
          {rank}
        </span>
        <span className="text-sm text-gray-500">
          {start} → {end}
        </span>
      </div>

      {/* サマリー数値 */}
      <div className="mb-3 grid grid-cols-4 gap-2 text-center">
        <div>
          <p className="text-xs text-gray-400">駅数</p>
          <p className="text-lg font-bold text-blue-700">{route.stationCount}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">距離</p>
          <p className="text-lg font-bold">
            {route.totalDistance}<span className="text-xs">km</span>
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-400">所要時間</p>
          <p className="text-lg font-bold">{timeStr}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">運賃(IC)</p>
          <p className="text-lg font-bold text-green-700">
            {route.fareIc}<span className="text-xs">円</span>
          </p>
        </div>
      </div>

      {/* アクションボタン */}
      <div className="flex gap-2">
        <button
          onClick={() => setShowMap((v) => !v)}
          className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
            showMap
              ? "bg-blue-600 text-white"
              : "border border-blue-300 text-blue-600 hover:bg-blue-50"
          }`}
        >
          {showMap ? "ルート図を閉じる" : "ルート図を表示"}
        </button>

        <details className="flex-1">
          <summary className="cursor-pointer select-none rounded-md border border-gray-200 px-3 py-1.5 text-xs text-gray-500 hover:bg-gray-50">
            駅一覧（{route.path.length}駅）
          </summary>
          <div className="mt-2 flex flex-wrap gap-1 text-xs text-gray-600">
            {route.path.map((seg, i) => {
              const sname = stationMap[seg.stationId] ?? seg.stationId;
              const lname = seg.lineId ? lineMap[seg.lineId] ?? seg.lineId : null;
              return (
                <span key={i} className="flex items-center gap-1">
                  {lname && (
                    <span className="rounded bg-gray-100 px-1 py-0.5 text-gray-500">
                      {lname}
                    </span>
                  )}
                  <span className="font-medium">{sname}</span>
                  {i < route.path.length - 1 && (
                    <span className="text-gray-300">›</span>
                  )}
                </span>
              );
            })}
          </div>
        </details>
      </div>

      {/* ルート図 */}
      {showMap && (
        <RouteMap route={route} stationMap={stationMap} lineMap={lineMap} />
      )}
    </div>
  );
}
