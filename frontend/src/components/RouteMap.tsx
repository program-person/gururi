"use client";

import { useEffect, useState } from "react";
import { OmawariRoute } from "@/lib/api";
import PREFECTURES from "@/data/prefectures";
import LAKES from "@/data/lakes";

export const LINE_COLORS: Record<string, string> = {
  C:  "#e80000", // 大阪環状線: 赤 (O)
  A:  "#0072ba", // JR京都線・琵琶湖線: 青 (A)
  JK: "#0072ba", // JR神戸線: 青 (JK) ※A同色
  G:  "#ffba00", // JR宝塚線: 黄 (G)
  T:  "#ff1493", // JR東西線: 桜桃色 (T)
  H:  "#ff1493", // 学研都市線: 桜桃色 (H) ※T同色・旧黄緑から2014年変更
  Q:  "#00b17b", // 大和路線: 緑 (Q)
  F:  "#347293", // おおさか東線: ブルーグレー (F)
  R:  "#ff8e1f", // 阪和線: オレンジ (R)
  D:  "#aa731c", // 奈良線: 茶色 (D)
  KS: "#00acd1", // 湖西線: 水色 (KS)
  NR: "#0072ba", // 北陸本線: 青 (NR) ※A同色
  KB: "#5a9934", // 草津線: 緑 (KB)
  KN: "#795548", // 関西本線(非電化): 茶系 ※公式未定義
  E:  "#878ddc", // 嵯峨野線: 紫 (E)
  U:  "#b31c31", // 桜井線: 赤系 (U)
  W:  "#f79fba", // 和歌山線: ピーチ (W)
  HA: "#ff8e1f", // 羽衣支線: ※阪和線(R)と同系統
  KA: "#ff8e1f", // 関西空港線: ※阪和線(R)と同系統
};

const DEFAULT_COLOR = "#6b7280";

const MIN_PAD_DEG = 0.35;

export interface StationGeo {
  lat: number;
  lng: number;
}

interface Props {
  route: OmawariRoute;
  stationMap: Record<string, string>;
  lineMap: Record<string, string>;
  stationGeo: Record<string, StationGeo>;
}

function centroid(coords: [number, number][]): [number, number] {
  const lat = coords.reduce((s, c) => s + c[0], 0) / coords.length;
  const lng = coords.reduce((s, c) => s + c[1], 0) / coords.length;
  return [lat, lng];
}

/**
 * ラベル配置: 接続セグメントの平均方向の反対側にラベルを置く。
 * 路線と重なりにくい位置を自動選択する。
 */
type TextAnchor = "start" | "middle" | "end";
type DomBaseline = "auto" | "middle" | "hanging";

function smartLabel(
  cx: number,
  cy: number,
  neighborPx: Array<[number, number]>,
  r: number,
): { lx: number; ly: number; anchor: TextAnchor; baseline: DomBaseline } {
  if (neighborPx.length === 0) {
    return { lx: cx + r + 5, ly: cy, anchor: "start", baseline: "middle" };
  }
  let dx = 0, dy = 0;
  for (const [nx, ny] of neighborPx) {
    dx += nx - cx;
    dy += ny - cy;
  }
  dx /= neighborPx.length;
  dy /= neighborPx.length;
  const len = Math.sqrt(dx * dx + dy * dy) || 1;
  const ndx = -dx / len;
  const ndy = -dy / len;
  const DIST = r + 10;
  const lx = cx + ndx * DIST;
  const ly = cy + ndy * DIST;
  const anchor: TextAnchor = ndx > 0.35 ? "start" : ndx < -0.35 ? "end" : "middle";
  // SVGはy軸下向き: ndy<0=上方向=文字を上に(auto=baseline at ly), ndy>0=下方向=文字を下に(hanging=top at ly)
  const baseline: DomBaseline = ndy < -0.35 ? "auto" : ndy > 0.35 ? "hanging" : "middle";
  return { lx, ly, anchor, baseline };
}

export default function RouteMap({ route, stationMap, lineMap, stationGeo }: Props) {
  const [isDark, setIsDark] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    setIsDark(mq.matches);
    const handler = (e: MediaQueryListEvent) => setIsDark(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  const path = route.path;
  const n = path.length;

  const xfers = new Set<number>();
  for (let i = 1; i < n - 1; i++) {
    if (path[i].lineId && path[i + 1]?.lineId && path[i].lineId !== path[i + 1].lineId) {
      xfers.add(i);
    }
  }

  const usedLines = [...new Set(path.slice(1).map((s) => s.lineId).filter(Boolean))];

  const rawCoords = path.map((seg) => stationGeo[seg.stationId] ?? null);
  const validCoords = rawCoords.filter((c): c is StationGeo => c != null);

  if (validCoords.length < 2) {
    return (
      <div className="mt-3 rounded-lg border border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 p-3 text-xs text-gray-400 dark:text-gray-500">
        座標データがありません
      </div>
    );
  }

  const routeLats = validCoords.map((c) => c.lat);
  const routeLngs = validCoords.map((c) => c.lng);
  const minLat = Math.min(...routeLats);
  const maxLat = Math.max(...routeLats);
  const minLng = Math.min(...routeLngs);
  const maxLng = Math.max(...routeLngs);

  const latSpan = Math.max(maxLat - minLat, 0.04);
  const lngSpan = Math.max(maxLng - minLng, 0.04);

  const latPad = Math.max(latSpan * 0.20, MIN_PAD_DEG);
  const lngPad = Math.max(lngSpan * 0.20, MIN_PAD_DEG);

  const bMinLat = minLat - latPad;
  const bMaxLat = maxLat + latPad;
  const bMinLng = minLng - lngPad;
  const bMaxLng = maxLng + lngPad;
  const bLatSpan = bMaxLat - bMinLat;
  const bLngSpan = bMaxLng - bMinLng;

  const cosCenter = Math.cos(((bMinLat + bMaxLat) / 2) * (Math.PI / 180));

  const BASE_W = 680;
  const SVG_W = Math.min(Math.max(BASE_W, Math.round(BASE_W * bLngSpan / 1.8)), 960);
  const PAD = 24;
  const innerW = SVG_W - 2 * PAD;
  const innerH = Math.round(innerW * bLatSpan / (bLngSpan * cosCenter));
  const svgH = Math.max(innerH + 2 * PAD, 180);
  const actualInnerH = svgH - 2 * PAD;

  const toXY = (lat: number, lng: number): [number, number] => {
    const x = PAD + ((lng - bMinLng) / bLngSpan) * innerW;
    const y = PAD + ((bMaxLat - lat) / bLatSpan) * actualInnerH;
    return [x, y];
  };

  const toSvgPts = (coords: [number, number][]) =>
    coords.map(([lat, lng]) => {
      const [x, y] = toXY(lat, lng);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");

  const prefPolygons = PREFECTURES.map((pref) => {
    const pts = toSvgPts(pref.coords);
    const [cLat, cLng] = centroid(pref.coords);
    const [cx, cy] = toXY(cLat, cLng);
    return { ...pref, pts, cx, cy };
  });

  const lakePolygons = LAKES.map((lake) => {
    const pts = toSvgPts(lake.coords);
    const [cLat, cLng] = centroid(lake.coords);
    const [cx, cy] = toXY(cLat, cLng);
    return { ...lake, pts, cx, cy };
  });

  // 各駅のピクセル座標を先に計算しておく（ラベル位置計算に使う）
  const stationPx = rawCoords.map((c) => (c ? toXY(c.lat, c.lng) : null));

  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-gray-900 shadow-sm">
      <div className="flex">
        {/* 路線図 SVG */}
        <div className="flex-1 min-w-0 overflow-x-auto">
          <svg
            width={SVG_W}
            height={svgH}
            style={{ display: "block", overflow: "hidden" }}
          >
            {/* 海（背景） */}
            <rect width={SVG_W} height={svgH} fill={isDark ? "#0f172a" : "#bfdbfe"} />

            {/* 都道府県ポリゴン — fill層 */}
            <g opacity={0.2}>
              {prefPolygons.map((pref) => (
                <polygon
                  key={`fill-${pref.name}`}
                  points={pref.pts}
                  fill={pref.fill}
                  stroke={pref.fill}
                  strokeWidth={3}
                  strokeLinejoin="round"
                />
              ))}
            </g>

            {/* 琵琶湖 */}
            {lakePolygons.map((lake) => (
              <polygon
                key={`lake-${lake.name}`}
                points={lake.pts}
                fill={isDark ? "#1e3a8a" : "#60a5fa"}
                stroke={isDark ? "#1d4ed8" : "#2563eb"}
                strokeWidth={1}
                strokeLinejoin="round"
                opacity={isDark ? 0.75 : 0.9}
              />
            ))}

            {/* 都道府県ポリゴン — border層 */}
            {prefPolygons.map((pref) => (
              <polygon
                key={`border-${pref.name}`}
                points={pref.pts}
                fill="none"
                stroke={isDark ? "#334155" : "#64748b"}
                strokeWidth={1.2}
                strokeLinejoin="round"
              />
            ))}

            {/* 琵琶湖ラベル */}
            {lakePolygons.map((lake) => (
              <text
                key={`lake-label-${lake.name}`}
                x={lake.cx}
                y={lake.cy}
                fontSize={10}
                textAnchor="middle"
                dominantBaseline="middle"
                fill={isDark ? "#93c5fd" : "#1e40af"}
                fontWeight="600"
                fontStyle="italic"
                stroke={isDark ? "#0f172a" : "white"}
                strokeWidth={2.5}
                paintOrder="stroke"
                style={{ userSelect: "none", pointerEvents: "none" }}
              >
                {lake.name}
              </text>
            ))}

            {/* 県名ラベル */}
            {prefPolygons.map((pref) => (
              <text
                key={`label-${pref.name}`}
                x={pref.cx}
                y={pref.cy}
                fontSize={11}
                textAnchor="middle"
                dominantBaseline="middle"
                fill={isDark ? "#cbd5e1" : "#1e293b"}
                fontWeight="700"
                stroke={isDark ? "#0f172a" : "white"}
                strokeWidth={3}
                paintOrder="stroke"
                style={{ userSelect: "none", pointerEvents: "none" }}
              >
                {pref.name}
              </text>
            ))}

            {/* 路線セグメント（黒ケーシング） */}
            {path.slice(1).map((seg, i) => {
              const from = rawCoords[i];
              const to = rawCoords[i + 1];
              if (!from || !to) return null;
              const [x1, y1] = toXY(from.lat, from.lng);
              const [x2, y2] = toXY(to.lat, to.lng);
              return (
                <line
                  key={`casing-${i}`}
                  x1={x1} y1={y1} x2={x2} y2={y2}
                  stroke="#000"
                  strokeWidth={6}
                  strokeLinecap="round"
                />
              );
            })}

            {/* 路線セグメント（本体） */}
            {path.slice(1).map((seg, i) => {
              const from = rawCoords[i];
              const to = rawCoords[i + 1];
              if (!from || !to) return null;
              const [x1, y1] = toXY(from.lat, from.lng);
              const [x2, y2] = toXY(to.lat, to.lng);
              const color = LINE_COLORS[seg.lineId] ?? DEFAULT_COLOR;
              return (
                <line
                  key={`seg-${i}`}
                  x1={x1} y1={y1} x2={x2} y2={y2}
                  stroke={color}
                  strokeWidth={4}
                  strokeLinecap="round"
                />
              );
            })}

            {/* 駅ドット＋ラベル */}
            {path.map((seg, i) => {
              const coord = rawCoords[i];
              if (!coord) return null;
              const [cx, cy] = toXY(coord.lat, coord.lng);
              const name = stationMap[seg.stationId] ?? seg.stationId;
              const isStart = i === 0;
              const isEnd = i === n - 1;
              const isXfer = xfers.has(i);
              const showLabel = isStart || isEnd || isXfer;

              const r = isStart || isEnd ? 8 : isXfer ? 6 : 3.5;
              const fill =
                isStart ? "#22c55e" :
                isEnd   ? "#ef4444" :
                isXfer  ? "#fbbf24" : "white";
              const strokeColor =
                isStart ? "#15803d" :
                isEnd   ? "#b91c1c" :
                isXfer  ? "#d97706" :
                (LINE_COLORS[seg.lineId] ?? DEFAULT_COLOR);

              // ホバーツールチップ: 路線名 / 駅名
              const lineIdForTip = i === 0 ? (path[1]?.lineId ?? "") : seg.lineId;
              const lineNameForTip = lineIdForTip ? (lineMap[lineIdForTip] ?? lineIdForTip) : null;
              const tooltip = lineNameForTip ? `${lineNameForTip} / ${name}` : name;

              // ラベル配置: 接続駅の方向と反対側
              let labelPos: { lx: number; ly: number; anchor: TextAnchor; baseline: DomBaseline } = { lx: cx + r + 5, ly: cy, anchor: "start", baseline: "middle" };
              if (showLabel) {
                const neighbors: Array<[number, number]> = [];
                if (i > 0) {
                  const p = stationPx[i - 1];
                  if (p) neighbors.push(p);
                }
                if (i < n - 1) {
                  const p = stationPx[i + 1];
                  if (p) neighbors.push(p);
                }
                labelPos = smartLabel(cx, cy, neighbors, r);
              }

              return (
                <g key={`st-${i}`}>
                  {/* 全駅ホバー tooltip */}
                  <circle cx={cx} cy={cy} r={r + 7} fill="transparent">
                    <title>{tooltip}</title>
                  </circle>
                  {/* リング */}
                  {(isStart || isEnd || isXfer) && (
                    <circle cx={cx} cy={cy} r={r + 2} fill={isDark ? "#0f172a" : "white"} />
                  )}
                  {/* 駅ドット */}
                  <circle
                    cx={cx} cy={cy} r={r}
                    fill={fill === "white" ? (isDark ? "#374151" : "white") : fill}
                    stroke={strokeColor}
                    strokeWidth={isStart || isEnd ? 2.5 : isXfer ? 2 : 1.5}
                  />
                  {/* ラベル（ハロー付き） */}
                  {showLabel && (
                    <text
                      x={labelPos.lx}
                      y={labelPos.ly}
                      fontSize={11}
                      textAnchor={labelPos.anchor}
                      dominantBaseline={labelPos.baseline}
                      fill={
                        isStart ? (isDark ? "#4ade80" : "#15803d") :
                        isEnd   ? (isDark ? "#f87171" : "#b91c1c") :
                                  (isDark ? "#f1f5f9" : "#1e293b")
                      }
                      fontWeight="700"
                      stroke={isDark ? "#0f172a" : "white"}
                      strokeWidth={3}
                      paintOrder="stroke"
                      style={{ userSelect: "none" }}
                    >
                      {name}
                    </text>
                  )}
                </g>
              );
            })}
          </svg>
        </div>

        {/* 凡例サイドバー */}
        <div className="shrink-0 w-28 border-l border-slate-100 dark:border-slate-700 px-2 py-3 flex flex-col gap-1.5 overflow-y-auto" style={{ maxHeight: svgH }}>
          <p className="text-[10px] font-semibold text-slate-400 dark:text-slate-500 mb-0.5">路線</p>
          {usedLines.map((lid) => (
            <span key={lid} className="flex items-center gap-1.5 text-[10px] text-slate-600 dark:text-slate-300 leading-tight">
              <span
                className="shrink-0 inline-block h-2 w-4 rounded-full"
                style={{ backgroundColor: LINE_COLORS[lid] ?? DEFAULT_COLOR }}
              />
              <span className="break-all">{lineMap[lid] ?? lid}</span>
            </span>
          ))}
          <div className="mt-1 border-t border-slate-100 dark:border-slate-700 pt-1.5 flex flex-col gap-1">
            {[
              { color: "#22c55e", label: "出発" },
              { color: "#ef4444", label: "到着" },
              { color: "#fbbf24", label: "乗換" },
            ].map(({ color, label }) => (
              <span key={label} className="flex items-center gap-1.5 text-[10px] text-slate-500 dark:text-slate-400">
                <span className="shrink-0 inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
                {label}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* フッター */}
      <div className="border-t border-slate-100 dark:border-slate-700 px-3 py-1.5 text-xs text-slate-400 dark:text-slate-500 text-right">
        ホバーで路線名・駅名を表示
      </div>
    </div>
  );
}
