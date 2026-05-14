"use client";

import { OmawariRoute } from "@/lib/api";

// JR西日本 各路線の公式カラー（近似）
export const LINE_COLORS: Record<string, string> = {
  C:  "#F15A22", // 大阪環状線: オレンジ
  A:  "#003087", // JR京都線・琵琶湖線: ネイビー
  JK: "#0070C0", // JR神戸線: ブルー
  G:  "#9B59B6", // JR宝塚線: パープル
  T:  "#00A0E9", // JR東西線: シアン
  H:  "#E91E8C", // 学研都市線: ピンク
  Q:  "#00873C", // 大和路線: グリーン
  F:  "#F5A623", // おおさか東線: ゴールド
  R:  "#E74C3C", // 阪和線: レッド
  D:  "#8B0000", // 奈良線: ダークレッド
};

const DEFAULT_COLOR = "#9CA3AF";
const GAP = 72;       // 駅間隔 (px)
const LINE_Y = 52;    // 路線ラインのY座標
const SVG_H = 130;    // SVG高さ

// ラベルを表示するかどうかの判定
function showLabel(i: number, n: number, xfers: Set<number>): boolean {
  if (i === 0 || i === n - 1) return true;
  if (xfers.has(i)) return true;
  if (i % 5 === 0) return true;
  return false;
}

interface Props {
  route: OmawariRoute;
  stationMap: Record<string, string>;
  lineMap: Record<string, string>;
}

export default function RouteMap({ route, stationMap, lineMap }: Props) {
  const path = route.path;
  const n = path.length;

  // 乗換駅: 到着路線と次に乗る路線が異なる駅
  const xfers = new Set<number>();
  for (let i = 1; i < n - 1; i++) {
    const arriving = path[i].lineId;
    const departing = path[i + 1]?.lineId ?? "";
    if (arriving && departing && arriving !== departing) {
      xfers.add(i);
    }
  }

  const svgW = 20 + (n - 1) * GAP + 20;
  const x = (i: number) => 20 + i * GAP;

  // このルートで使われている路線一覧（重複除去・順序保持）
  const usedLines = [...new Set(path.slice(1).map((s) => s.lineId).filter(Boolean))];

  return (
    <div className="mt-3 rounded-lg border border-gray-100 bg-gray-50 p-3">
      {/* 凡例 */}
      <div className="mb-2 flex flex-wrap gap-x-3 gap-y-1">
        {usedLines.map((lid) => (
          <span key={lid} className="flex items-center gap-1 text-xs text-gray-600">
            <span
              className="inline-block h-2.5 w-5 rounded-full"
              style={{ backgroundColor: LINE_COLORS[lid] ?? DEFAULT_COLOR }}
            />
            {lineMap[lid] ?? lid}
          </span>
        ))}
        <span className="flex items-center gap-1 text-xs text-gray-400">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-amber-400" /> 乗換
        </span>
      </div>

      {/* 路線図 SVG */}
      <div className="overflow-x-auto">
        <svg
          width={svgW}
          height={SVG_H}
          style={{ minWidth: svgW, display: "block" }}
        >
          {/* 路線セグメント（線） */}
          {path.slice(1).map((seg, i) => {
            const color = LINE_COLORS[seg.lineId] ?? DEFAULT_COLOR;
            return (
              <line
                key={`seg-${i}`}
                x1={x(i)}     y1={LINE_Y}
                x2={x(i + 1)} y2={LINE_Y}
                stroke={color}
                strokeWidth={5}
                strokeLinecap="square"
              />
            );
          })}

          {/* 駅ノードとラベル */}
          {path.map((seg, i) => {
            const cx = x(i);
            const name = stationMap[seg.stationId] ?? seg.stationId;
            const isStart = i === 0;
            const isEnd   = i === n - 1;
            const isXfer  = xfers.has(i);

            // ノードのサイズ・色
            const r = isStart || isEnd ? 9 : isXfer ? 7 : 5;
            const fill =
              isStart ? "#22c55e" :
              isEnd   ? "#ef4444" :
              isXfer  ? "#fbbf24" : "white";
            const strokeColor =
              isStart ? "#15803d" :
              isEnd   ? "#b91c1c" :
              isXfer  ? "#d97706" :
              (LINE_COLORS[seg.lineId] ?? DEFAULT_COLOR);

            const labelY = LINE_Y + r + 5;

            return (
              <g key={`st-${i}`}>
                {/* ホバー時に駅名を表示するタイトル */}
                <circle cx={cx} cy={LINE_Y} r={r + 4} fill="transparent">
                  <title>{name}</title>
                </circle>
                {/* 駅ドット */}
                <circle
                  cx={cx} cy={LINE_Y} r={r}
                  fill={fill}
                  stroke={strokeColor}
                  strokeWidth={2.5}
                />
                {/* ラベル（-45° 回転） */}
                {showLabel(i, n, xfers) && (
                  <text
                    x={cx}
                    y={labelY}
                    fontSize={10}
                    textAnchor="end"
                    dominantBaseline="hanging"
                    transform={`rotate(-45 ${cx} ${labelY})`}
                    fill={isStart ? "#15803d" : isEnd ? "#b91c1c" : "#374151"}
                    fontWeight={isStart || isEnd || isXfer ? "600" : "400"}
                  >
                    {name}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      <p className="mt-1 text-right text-xs text-gray-400">
        ● 出発 &nbsp;● 到着 &nbsp;● 乗換 &nbsp;— ホバーで全駅名を表示
      </p>
    </div>
  );
}
