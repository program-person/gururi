"use client";

import { OmawariRoute } from "@/lib/api";
import PREFECTURES from "@/data/prefectures";

export const LINE_COLORS: Record<string, string> = {
  C:  "#f97316", // 大阪環状線: オレンジ
  A:  "#1d4ed8", // JR京都線・琵琶湖線: ブルー
  JK: "#0284c7", // JR神戸線: スカイブルー
  G:  "#7c3aed", // JR宝塚線: パープル
  T:  "#0891b2", // JR東西線: シアン
  H:  "#db2777", // 学研都市線: ピンク
  Q:  "#16a34a", // 大和路線: グリーン
  F:  "#d97706", // おおさか東線: アンバー
  R:  "#dc2626", // 阪和線: レッド
  D:  "#991b1b", // 奈良線: ダークレッド
};

const DEFAULT_COLOR = "#6b7280";

// 全体ビューポートの最小パディング（度）
// 路線が短くても周辺の県が見えるように確保する
const MIN_PAD_DEG = 0.35;

// cos(35°) — 経度スケールの緯度換算係数
const COS35 = Math.cos((35 * Math.PI) / 180);

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

/** ポリゴン重心を計算 */
function centroid(coords: [number, number][]): [number, number] {
  const lat = coords.reduce((s, c) => s + c[0], 0) / coords.length;
  const lng = coords.reduce((s, c) => s + c[1], 0) / coords.length;
  return [lat, lng];
}

export default function RouteMap({ route, stationMap, lineMap, stationGeo }: Props) {
  const path = route.path;
  const n = path.length;

  // 乗換検出（路線が変わる駅）
  const xfers = new Set<number>();
  for (let i = 1; i < n - 1; i++) {
    if (path[i].lineId && path[i + 1]?.lineId && path[i].lineId !== path[i + 1].lineId) {
      xfers.add(i);
    }
  }

  // 使用路線一覧（凡例用）
  const usedLines = [...new Set(path.slice(1).map((s) => s.lineId).filter(Boolean))];

  // 各駅の座標
  const rawCoords = path.map((seg) => stationGeo[seg.stationId] ?? null);
  const validCoords = rawCoords.filter((c): c is StationGeo => c != null);

  if (validCoords.length < 2) {
    return (
      <div className="mt-3 rounded-lg border border-gray-100 bg-gray-50 p-3 text-xs text-gray-400">
        座標データがありません
      </div>
    );
  }

  // ─── バウンディングボックス計算 ─────────────────────────────
  // 路線駅の範囲
  const routeLats = validCoords.map((c) => c.lat);
  const routeLngs = validCoords.map((c) => c.lng);
  const minLat = Math.min(...routeLats);
  const maxLat = Math.max(...routeLats);
  const minLng = Math.min(...routeLngs);
  const maxLng = Math.max(...routeLngs);

  const latSpan = Math.max(maxLat - minLat, 0.04);
  const lngSpan = Math.max(maxLng - minLng, 0.04);

  // パディング：路線が短くても県境が見えるよう最小値を保証
  const latPad = Math.max(latSpan * 0.20, MIN_PAD_DEG);
  const lngPad = Math.max(lngSpan * 0.20, MIN_PAD_DEG);

  const bMinLat = minLat - latPad;
  const bMaxLat = maxLat + latPad;
  const bMinLng = minLng - lngPad;
  const bMaxLng = maxLng + lngPad;
  const bLatSpan = bMaxLat - bMinLat;
  const bLngSpan = bMaxLng - bMinLng;

  // ─── SVG寸法（メルカトル補正でアスペクト比を地理的に正確に） ──
  const SVG_W = 680;
  const PAD = 24; // 描画エリアの外枠余白
  const innerW = SVG_W - 2 * PAD;
  const innerH = Math.round(innerW * bLatSpan / (bLngSpan * COS35));
  const svgH = Math.max(innerH + 2 * PAD, 180);
  const actualInnerH = svgH - 2 * PAD;

  // 地理座標 → SVGピクセル
  const toXY = (lat: number, lng: number): [number, number] => {
    const x = PAD + ((lng - bMinLng) / bLngSpan) * innerW;
    const y = PAD + ((bMaxLat - lat) / bLatSpan) * actualInnerH;
    return [x, y];
  };

  // ─── 都道府県ポリゴンの SVG points 文字列を生成 ─────────────
  const prefPolygons = PREFECTURES.map((pref) => {
    const pts = pref.coords
      .map(([lat, lng]) => {
        const [x, y] = toXY(lat, lng);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
    const [cLat, cLng] = centroid(pref.coords);
    const [cx, cy] = toXY(cLat, cLng);
    return { ...pref, pts, cx, cy };
  });

  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      {/* 凡例 */}
      <div className="flex flex-wrap gap-x-3 gap-y-1 border-b border-slate-100 px-3 py-2">
        {usedLines.map((lid) => (
          <span key={lid} className="flex items-center gap-1 text-xs text-slate-600">
            <span
              className="inline-block h-2 w-5 rounded-full"
              style={{ backgroundColor: LINE_COLORS[lid] ?? DEFAULT_COLOR }}
            />
            {lineMap[lid] ?? lid}
          </span>
        ))}
        <span className="flex items-center gap-1 text-xs text-slate-400">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-amber-400" />
          乗換
        </span>
      </div>

      {/* 路線図 SVG */}
      <div className="overflow-x-auto">
        <svg
          width={SVG_W}
          height={svgH}
          style={{ display: "block", overflow: "hidden" }}
        >
          {/* 海（背景） */}
          <rect width={SVG_W} height={svgH} fill="#bfdbfe" />

          {/* 都道府県ポリゴン — fill層（stroke=fill色で外側に膨らませ隣接ポリゴン間の隙間を埋める） */}
          {prefPolygons.map((pref) => (
            <polygon
              key={`fill-${pref.name}`}
              points={pref.pts}
              fill={pref.fill}
              stroke={pref.fill}
              strokeWidth={2.5}
              strokeLinejoin="round"
            />
          ))}

          {/* 都道府県ポリゴン — border層（中立色の境界線を上書き） */}
          {prefPolygons.map((pref) => (
            <polygon
              key={`border-${pref.name}`}
              points={pref.pts}
              fill="none"
              stroke="#94a3b8"
              strokeWidth={1}
              strokeLinejoin="round"
            />
          ))}

          {/* 県名ラベル */}
          {prefPolygons.map((pref) => (
            <text
              key={`label-${pref.name}`}
              x={pref.cx}
              y={pref.cy}
              fontSize={9}
              textAnchor="middle"
              dominantBaseline="middle"
              fill="#64748b"
              fontWeight="500"
              style={{ userSelect: "none", pointerEvents: "none" }}
            >
              {pref.name}
            </text>
          ))}

          {/* 路線セグメント（影） */}
          {path.slice(1).map((seg, i) => {
            const from = rawCoords[i];
            const to = rawCoords[i + 1];
            if (!from || !to) return null;
            const [x1, y1] = toXY(from.lat, from.lng);
            const [x2, y2] = toXY(to.lat, to.lng);
            return (
              <line
                key={`shadow-${i}`}
                x1={x1} y1={y1} x2={x2} y2={y2}
                stroke="rgba(0,0,0,0.18)"
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
            const labelFill = isStart ? "#15803d" : isEnd ? "#b91c1c" : "#1e293b";

            // ラベルの横位置（SVG右端付近は左側に配置）
            const labelRight = cx > SVG_W * 0.75;
            const lx = labelRight ? cx - r - 3 : cx + r + 3;
            const anchor = labelRight ? "end" : "start";

            return (
              <g key={`st-${i}`}>
                {/* 全駅ホバー tooltip */}
                <circle cx={cx} cy={cy} r={r + 7} fill="transparent">
                  <title>{name}</title>
                </circle>
                {/* ドット外枠（白リング） */}
                {(isStart || isEnd || isXfer) && (
                  <circle cx={cx} cy={cy} r={r + 2} fill="white" />
                )}
                {/* 駅ドット */}
                <circle
                  cx={cx} cy={cy} r={r}
                  fill={fill}
                  stroke={strokeColor}
                  strokeWidth={isStart || isEnd ? 2.5 : isXfer ? 2 : 1.5}
                />
                {/* ラベル（白ハロー付き） */}
                {showLabel && (
                  <text
                    x={lx}
                    y={cy}
                    fontSize={11}
                    textAnchor={anchor}
                    dominantBaseline="middle"
                    fill={labelFill}
                    fontWeight="700"
                    stroke="white"
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

      {/* フッター */}
      <div className="flex items-center justify-between border-t border-slate-100 px-3 py-1.5 text-xs text-slate-400">
        <span className="flex gap-2">
          <span className="flex items-center gap-0.5">
            <svg width="10" height="10"><circle cx="5" cy="5" r="4" fill="#22c55e" /></svg>
            出発
          </span>
          <span className="flex items-center gap-0.5">
            <svg width="10" height="10"><circle cx="5" cy="5" r="4" fill="#ef4444" /></svg>
            到着
          </span>
          <span className="flex items-center gap-0.5">
            <svg width="10" height="10"><circle cx="5" cy="5" r="4" fill="#fbbf24" /></svg>
            乗換
          </span>
        </span>
        <span>ホバーで全駅名を表示</span>
      </div>
    </div>
  );
}
