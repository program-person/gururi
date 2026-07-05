"use client";

import {
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { OmawariRoute } from "@/lib/api";
import PREFECTURES from "@/data/prefectures";
import LAKES from "@/data/lakes";

// キーは graph.json の路線ID（JR西日本公式の路線記号に準拠）
export const LINE_COLORS: Record<string, string> = {
  O:  "#e80000", // 大阪環状線: 赤
  A:  "#0072ba", // JR京都線・琵琶湖線・JR神戸線・北陸本線: 青
  G:  "#ffba00", // JR宝塚線: 黄
  H:  "#ff1493", // JR東西線・学研都市線: 桜桃色（旧黄緑から2014年変更）
  Q:  "#00b17b", // 大和路線: 緑
  F:  "#347293", // おおさか東線: ブルーグレー
  R:  "#ff8e1f", // 阪和線: オレンジ
  D:  "#aa731c", // 奈良線: 茶色
  B:  "#00acd1", // 湖西線: 水色
  C:  "#5a9934", // 草津線: 緑
  V:  "#795548", // 関西本線(非電化): 茶系 ※公式未定義
  E:  "#878ddc", // 嵯峨野線: 紫
  U:  "#b31c31", // 万葉まほろば線: 赤系
  T:  "#f79fba", // 和歌山線: ピーチ
  S:  "#ff8e1f", // 関西空港線: ※阪和線(R)と同系統
  HA: "#ff8e1f", // 羽衣支線: ※阪和線(R)と同系統
  I:  "#009944", // 加古川線: 緑系 ※公式未定義
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
 * ラベル配置: 候補位置を「配置済みラベル・路線セグメント・画面外」との衝突で
 * スコアリングし、最も衝突の少ない位置を greedy に選ぶ。
 */
type TextAnchor = "start" | "middle" | "end";
type DomBaseline = "auto" | "middle" | "hanging";

interface LabelPos {
  lx: number;
  ly: number;
  anchor: TextAnchor;
  baseline: DomBaseline;
}

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

// 8方向の単位ベクトル（右・左・上・下・斜め4方向）
const DIRS: Array<[number, number]> = [
  [1, 0], [-1, 0], [0, -1], [0, 1],
  [0.707, -0.707], [-0.707, -0.707], [0.707, 0.707], [-0.707, 0.707],
];

function anchorFor(ndx: number): TextAnchor {
  return ndx > 0.35 ? "start" : ndx < -0.35 ? "end" : "middle";
}

// SVGはy軸下向き: ndy<0=上方向=文字を上に(auto=baseline at ly), ndy>0=下方向=文字を下に(hanging=top at ly)
function baselineFor(ndy: number): DomBaseline {
  return ndy < -0.35 ? "auto" : ndy > 0.35 ? "hanging" : "middle";
}

function makeRect(
  lx: number,
  ly: number,
  w: number,
  h: number,
  anchor: TextAnchor,
  baseline: DomBaseline,
): Rect {
  const x = anchor === "start" ? lx : anchor === "end" ? lx - w : lx - w / 2;
  const y = baseline === "hanging" ? ly : baseline === "auto" ? ly - h : ly - h / 2;
  return { x, y, w, h };
}

function rectsOverlap(a: Rect, b: Rect, pad = 2): boolean {
  return (
    a.x - pad < b.x + b.w &&
    a.x + a.w + pad > b.x &&
    a.y - pad < b.y + b.h &&
    a.y + a.h + pad > b.y
  );
}

function cross(ox: number, oy: number, ax: number, ay: number, bx: number, by: number): number {
  return (ax - ox) * (by - oy) - (ay - oy) * (bx - ox);
}

function segsIntersect(
  x1: number, y1: number, x2: number, y2: number,
  x3: number, y3: number, x4: number, y4: number,
): boolean {
  const d1 = cross(x3, y3, x4, y4, x1, y1);
  const d2 = cross(x3, y3, x4, y4, x2, y2);
  const d3 = cross(x1, y1, x2, y2, x3, y3);
  const d4 = cross(x1, y1, x2, y2, x4, y4);
  return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0));
}

function segIntersectsRect(
  x1: number, y1: number, x2: number, y2: number,
  r: Rect, pad = 2,
): boolean {
  const rx = r.x - pad;
  const ry = r.y - pad;
  const rx2 = r.x + r.w + pad;
  const ry2 = r.y + r.h + pad;
  const inside = (x: number, y: number) => x >= rx && x <= rx2 && y >= ry && y <= ry2;
  if (inside(x1, y1) || inside(x2, y2)) return true;
  return (
    segsIntersect(x1, y1, x2, y2, rx, ry, rx2, ry) ||
    segsIntersect(x1, y1, x2, y2, rx2, ry, rx2, ry2) ||
    segsIntersect(x1, y1, x2, y2, rx2, ry2, rx, ry2) ||
    segsIntersect(x1, y1, x2, y2, rx, ry2, rx, ry)
  );
}

function pointInRing(x: number, y: number, ring: Array<[number, number]>): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

interface ViewBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

const MAX_ZOOM = 8;
const ZOOM_STEP = 1.5;

export default function RouteMap({ route, stationMap, lineMap, stationGeo }: Props) {
  const [isDark, setIsDark] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    setIsDark(mq.matches);
    const handler = (e: MediaQueryListEvent) => setIsDark(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  // --- ズーム・パン ---
  // view = 表示中の viewBox。null は全体表示。
  const [view, setView] = useState<ViewBox | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  // SVG全体のサイズはルートごとに変わるので、ハンドラから ref 経由で参照する
  const dimsRef = useRef({ w: 680, h: 400 });
  const pointersRef = useRef<Map<number, { x: number; y: number }>>(new Map());

  useEffect(() => {
    setView(null);
  }, [route]);

  // (px, py) = SVG要素上のピクセル位置を中心に factor 倍ズーム
  const zoomAt = (factor: number, px: number, py: number) => {
    setView((prev) => {
      const { w: W, h: H } = dimsRef.current;
      const cur = prev ?? { x: 0, y: 0, w: W, h: H };
      const newW = Math.min(Math.max(cur.w / factor, W / MAX_ZOOM), W);
      if (newW >= W) return null;
      const newH = newW * (H / W);
      const bx = cur.x + (px / W) * cur.w;
      const by = cur.y + (py / H) * cur.h;
      const nx = Math.min(Math.max(bx - (px / W) * newW, 0), W - newW);
      const ny = Math.min(Math.max(by - (py / H) * newH, 0), H - newH);
      return { x: nx, y: ny, w: newW, h: newH };
    });
  };

  const panBy = (dxPx: number, dyPx: number) => {
    setView((prev) => {
      if (!prev) return prev;
      const { w: W, h: H } = dimsRef.current;
      const scale = prev.w / W;
      const nx = Math.min(Math.max(prev.x - dxPx * scale, 0), W - prev.w);
      const ny = Math.min(Math.max(prev.y - dyPx * scale, 0), H - prev.h);
      return { ...prev, x: nx, y: ny };
    });
  };

  const onPointerDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    pointersRef.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
  };

  const onPointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    const pts = pointersRef.current;
    const prev = pts.get(e.pointerId);
    if (!prev) return;
    const cur = { x: e.clientX, y: e.clientY };
    if (pts.size === 1) {
      panBy(cur.x - prev.x, cur.y - prev.y);
    } else if (pts.size === 2) {
      // ピンチズーム: 2点間距離の変化率で拡縮、中点を固定
      const otherEntry = [...pts.entries()].find(([id]) => id !== e.pointerId);
      if (otherEntry) {
        const other = otherEntry[1];
        const prevDist = Math.hypot(prev.x - other.x, prev.y - other.y);
        const curDist = Math.hypot(cur.x - other.x, cur.y - other.y);
        if (prevDist > 0 && curDist > 0) {
          const rect = e.currentTarget.getBoundingClientRect();
          zoomAt(curDist / prevDist, (cur.x + other.x) / 2 - rect.left, (cur.y + other.y) / 2 - rect.top);
        }
      }
    }
    pts.set(e.pointerId, cur);
  };

  const onPointerUp = (e: ReactPointerEvent<SVGSVGElement>) => {
    pointersRef.current.delete(e.pointerId);
  };

  const onDoubleClick = (e: ReactMouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    zoomAt(2, e.clientX - rect.left, e.clientY - rect.top);
  };

  // ホイールズーム: ページスクロールを止めるため non-passive で直接リスナ登録する
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const handler = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      zoomAt(e.deltaY < 0 ? 1.25 : 0.8, e.clientX - rect.left, e.clientY - rect.top);
    };
    el.addEventListener("wheel", handler, { passive: false });
    return () => el.removeEventListener("wheel", handler);
  });

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

  dimsRef.current = { w: SVG_W, h: svgH };
  const v = view ?? { x: 0, y: 0, w: SVG_W, h: svgH };
  const zoom = SVG_W / v.w;
  // 線幅・文字サイズ・ドット半径を画面上で一定に保つための係数
  const k = 1 / zoom;

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
    const ringPts = pref.rings.map(toSvgPts);
    // ラベルは本土（最大リング = rings[0]）の重心を起点に配置する
    const mainPx = pref.rings[0].map(([lat, lng]) => toXY(lat, lng));
    const [cLat, cLng] = centroid(pref.rings[0]);
    const [cx, cy] = toXY(cLat, cLng);
    return { ...pref, ringPts, mainPx, cx, cy };
  });

  const lakePolygons = LAKES.map((lake) => {
    const pts = toSvgPts(lake.coords);
    const ringPx = lake.coords.map(([lat, lng]) => toXY(lat, lng));
    const [cLat, cLng] = centroid(lake.coords);
    const [cx, cy] = toXY(cLat, cLng);
    return { ...lake, pts, ringPx, cx, cy };
  });

  // 各駅のピクセル座標を先に計算しておく（ラベル位置計算に使う）
  const stationPx = rawCoords.map((c) => (c ? toXY(c.lat, c.lng) : null));

  // --- ラベル配置（衝突回避） ---

  const stationMeta = path.map((_, i) => {
    const isStart = i === 0;
    const isEnd = i === n - 1;
    const isXfer = xfers.has(i);
    return {
      isStart,
      isEnd,
      isXfer,
      showLabel: isStart || isEnd || isXfer,
      r: isStart || isEnd ? 8 : isXfer ? 6 : 3.5,
    };
  });

  const routeSegsPx: Array<[number, number, number, number]> = [];
  for (let i = 1; i < n; i++) {
    const a = stationPx[i - 1];
    const b = stationPx[i];
    if (a && b) routeSegsPx.push([a[0], a[1], b[0], b[1]]);
  }

  const STATION_FONT = 11;
  const MID_FONT = 10;
  // ズームインしたら（2.2倍以上）画面内の中間駅にもラベルを出す
  const MID_LABEL_ZOOM = 2.2;
  const VIEW_MARGIN = 30 * k;
  const inViewPx = (p: [number, number] | null): p is [number, number] =>
    p != null &&
    p[0] >= v.x - VIEW_MARGIN && p[0] <= v.x + v.w + VIEW_MARGIN &&
    p[1] >= v.y - VIEW_MARGIN && p[1] <= v.y + v.h + VIEW_MARGIN;
  const labeled = stationMeta.map(
    (m, i) => (m.showLabel || zoom >= MID_LABEL_ZOOM) && inViewPx(stationPx[i]),
  );

  const placedRects: Rect[] = [];
  const stationLabelPos: Array<LabelPos | null> = new Array(n).fill(null);

  // 駅ラベル: 隣接駅と反対の方向を優先しつつ、8方向×2距離の候補から最良を選ぶ。
  // 出発・到着・乗換を先に配置し、中間駅ラベルは残った隙間に置く。
  const labelOrder = [...Array(n).keys()].filter((i) => labeled[i]);
  labelOrder.sort((a, b) => Number(stationMeta[b].showLabel) - Number(stationMeta[a].showLabel));

  for (const i of labelOrder) {
    const meta = stationMeta[i];
    const px = stationPx[i];
    if (!px) continue;
    const [cx, cy] = px;
    const name = stationMap[path[i].stationId] ?? path[i].stationId;
    const fontSize = (meta.showLabel ? STATION_FONT : MID_FONT) * k;
    const w = name.length * fontSize;
    const h = fontSize * 1.25;

    let pdx = 0, pdy = 0, cnt = 0;
    for (const j of [i - 1, i + 1]) {
      const p = j >= 0 && j < n ? stationPx[j] : null;
      if (p) { pdx += p[0] - cx; pdy += p[1] - cy; cnt++; }
    }
    let prefX = 1, prefY = 0;
    if (cnt > 0) {
      const len = Math.hypot(pdx, pdy) || 1;
      prefX = -pdx / len;
      prefY = -pdy / len;
    }
    const dirs = [...DIRS].sort(
      (a, b) => b[0] * prefX + b[1] * prefY - (a[0] * prefX + a[1] * prefY),
    );

    let best: { pos: LabelPos; rect: Rect; score: number } | null = null;
    const dists = [(meta.r + 10) * k, (meta.r + 22) * k];
    for (let di = 0; di < dists.length; di++) {
      const dist = dists[di];
      for (let rank = 0; rank < dirs.length; rank++) {
        const [dx, dy] = dirs[rank];
        const lx = cx + dx * dist;
        const ly = cy + dy * dist;
        const anchor = anchorFor(dx);
        const baseline = baselineFor(dy);
        const rect = makeRect(lx, ly, w, h, anchor, baseline);
        // 好ましい方向・近い距離ほど低コスト。衝突は種類ごとに加点
        let score = rank + di * 4;
        for (const pr of placedRects) {
          if (rectsOverlap(rect, pr, 2 * k)) score += 100;
        }
        for (const [x1, y1, x2, y2] of routeSegsPx) {
          if (segIntersectsRect(x1, y1, x2, y2, rect, 2 * k)) score += 25;
        }
        if (
          rect.x < v.x + 2 * k || rect.y < v.y + 2 * k ||
          rect.x + rect.w > v.x + v.w - 2 * k || rect.y + rect.h > v.y + v.h - 2 * k
        ) {
          score += 60;
        }
        if (!best || score < best.score) best = { pos: { lx, ly, anchor, baseline }, rect, score };
      }
    }
    if (!best) continue;
    // 中間駅ラベルは他のラベルと重なるくらいなら出さない
    if (!meta.showLabel && best.score >= 100) continue;
    placedRects.push(best.rect);
    stationLabelPos[i] = best.pos;
  }

  // 県名・湖名: 重心を起点に同心円状の候補から、路線・駅ラベルと重ならない位置へ退避。
  // 逃げ場がない場合は dim（薄く表示）にする。
  const placeAreaLabel = (
    cx0: number,
    cy0: number,
    w: number,
    h: number,
    ringPx: Array<[number, number]> | null,
  ): { x: number; y: number; dim: boolean } => {
    let best: { x: number; y: number; score: number } | null = null;
    for (const baseRad of [0, 30, 60, 90]) {
      const rad = baseRad * k;
      const offsets: Array<[number, number]> =
        baseRad === 0 ? [[0, 0]] : DIRS.map(([dx, dy]) => [dx * rad, dy * rad]);
      for (const [ox, oy] of offsets) {
        const x = cx0 + ox;
        const y = cy0 + oy;
        if (ringPx && !pointInRing(x, y, ringPx)) continue;
        const rect: Rect = { x: x - w / 2, y: y - h / 2, w, h };
        let score = baseRad * 0.1; // 重心に近いほど優先
        for (const pr of placedRects) {
          if (rectsOverlap(rect, pr, 4 * k)) score += 100;
        }
        for (const [x1, y1, x2, y2] of routeSegsPx) {
          if (segIntersectsRect(x1, y1, x2, y2, rect, 4 * k)) score += 30;
        }
        if (!best || score < best.score) best = { x, y, score };
      }
    }
    if (!best) return { x: cx0, y: cy0, dim: true };
    placedRects.push({ x: best.x - w / 2, y: best.y - h / 2, w, h });
    return { x: best.x, y: best.y, dim: best.score >= 30 };
  };

  const PREF_FONT = 12;
  const prefLabels = prefPolygons.map((pref) => {
    // letterSpacing 0.3em ぶん幅を広めに見積もる
    const w = pref.name.length * PREF_FONT * 1.3 * k;
    return { name: pref.name, ...placeAreaLabel(pref.cx, pref.cy, w, PREF_FONT * 1.3 * k, pref.mainPx) };
  });

  const LAKE_FONT = 10;
  const lakeLabels = lakePolygons.map((lake) => {
    const w = lake.name.length * LAKE_FONT * k;
    return { name: lake.name, ...placeAreaLabel(lake.cx, lake.cy, w, LAKE_FONT * 1.3 * k, lake.ringPx) };
  });

  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-gray-900 shadow-sm">
      <div className="flex">
        {/* 路線図 SVG */}
        <div className="relative flex-1 min-w-0">
          <div className="overflow-x-auto">
          <svg
            ref={svgRef}
            width={SVG_W}
            height={svgH}
            viewBox={`${v.x} ${v.y} ${v.w} ${v.h}`}
            style={{
              display: "block",
              overflow: "hidden",
              touchAction: "none",
              cursor: zoom > 1 ? "grab" : "default",
            }}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
            onDoubleClick={onDoubleClick}
          >
            {/* 海（背景） */}
            <rect width={SVG_W} height={svgH} fill={isDark ? "#0f172a" : "#e0f2fe"} />

            {/* 都道府県ポリゴン — 不透明ベース層（陸と海の境界を明確にする） */}
            {prefPolygons.map((pref) =>
              pref.ringPts.map((pts, ri) => (
                <polygon
                  key={`base-${pref.name}-${ri}`}
                  points={pts}
                  fill={isDark ? "#334155" : "#f8fafc"}
                  stroke={isDark ? "#334155" : "#f8fafc"}
                  strokeWidth={3 * k}
                  strokeLinejoin="round"
                />
              ))
            )}

            {/* 都道府県ポリゴン — パステルfill層 */}
            <g opacity={isDark ? 0.3 : 0.4}>
              {prefPolygons.map((pref) =>
                pref.ringPts.map((pts, ri) => (
                  <polygon
                    key={`fill-${pref.name}-${ri}`}
                    points={pts}
                    fill={pref.fill}
                    stroke={pref.fill}
                    strokeWidth={3 * k}
                    strokeLinejoin="round"
                  />
                ))
              )}
            </g>

            {/* 琵琶湖 */}
            {lakePolygons.map((lake) => (
              <polygon
                key={`lake-${lake.name}`}
                points={lake.pts}
                fill={isDark ? "#1e3a8a" : "#bae6fd"}
                stroke={isDark ? "#1d4ed8" : "#60a5fa"}
                strokeWidth={1 * k}
                strokeLinejoin="round"
                opacity={isDark ? 0.75 : 1}
              />
            ))}

            {/* 都道府県ポリゴン — border層 */}
            {prefPolygons.map((pref) =>
              pref.ringPts.map((pts, ri) => (
                <polygon
                  key={`border-${pref.name}-${ri}`}
                  points={pts}
                  fill="none"
                  stroke={isDark ? "#64748b" : "#64748b"}
                  strokeWidth={1.2 * k}
                  strokeLinejoin="round"
                />
              ))
            )}

            {/* 琵琶湖ラベル（青イタリック = 水域名） */}
            {lakeLabels.map((lake) => (
              <text
                key={`lake-label-${lake.name}`}
                x={lake.x}
                y={lake.y}
                fontSize={LAKE_FONT * k}
                textAnchor="middle"
                dominantBaseline="middle"
                fill={isDark ? "#93c5fd" : "#1e40af"}
                fontWeight="600"
                fontStyle="italic"
                opacity={lake.dim ? 0.55 : 1}
                stroke={isDark ? "#0f172a" : "white"}
                strokeWidth={2.5 * k}
                paintOrder="stroke"
                style={{ userSelect: "none", pointerEvents: "none" }}
              >
                {lake.name}
              </text>
            ))}

            {/* 県名ラベル（グレー・字間広め = 行政地名。駅名と区別する） */}
            {prefLabels.map((pref) => (
              <text
                key={`label-${pref.name}`}
                x={pref.x}
                y={pref.y}
                fontSize={PREF_FONT * k}
                textAnchor="middle"
                dominantBaseline="middle"
                fill={isDark ? "#94a3b8" : "#64748b"}
                fontWeight="500"
                letterSpacing="0.3em"
                opacity={pref.dim ? 0.55 : 1}
                stroke={isDark ? "#334155" : "#f8fafc"}
                strokeWidth={2 * k}
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
                  stroke={isDark ? "#0f172a" : "#e2e8f0"}
                  strokeWidth={6 * k}
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
              if (seg.lineId && !(seg.lineId in LINE_COLORS)) {
                console.warn(`[RouteMap] unknown lineId: "${seg.lineId}"`);
              }
              const color = LINE_COLORS[seg.lineId] ?? DEFAULT_COLOR;
              return (
                <line
                  key={`seg-${i}`}
                  x1={x1} y1={y1} x2={x2} y2={y2}
                  stroke={color}
                  strokeWidth={4 * k}
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
              const { isStart, isEnd, isXfer, showLabel, r } = stationMeta[i];
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

              // ラベル配置は事前計算済み（衝突回避）
              const labelPos = stationLabelPos[i];

              return (
                <g key={`st-${i}`}>
                  {/* 全駅ホバー tooltip */}
                  <circle cx={cx} cy={cy} r={(r + 7) * k} fill="transparent">
                    <title>{tooltip}</title>
                  </circle>
                  {/* リング */}
                  {(isStart || isEnd || isXfer) && (
                    <circle cx={cx} cy={cy} r={(r + 2) * k} fill={isDark ? "#0f172a" : "white"} />
                  )}
                  {/* 駅ドット */}
                  <circle
                    cx={cx} cy={cy} r={r * k}
                    fill={fill === "white" ? (isDark ? "#e2e8f0" : "white") : fill}
                    stroke={strokeColor}
                    strokeWidth={(isStart || isEnd ? 2.5 : isXfer ? 2 : 1.5) * k}
                  />
                  {/* ラベル（ハロー付き）。showLabel=主要駅、それ以外はズーム時の中間駅 */}
                  {labelPos && (
                    <text
                      x={labelPos.lx}
                      y={labelPos.ly}
                      fontSize={(showLabel ? STATION_FONT : MID_FONT) * k}
                      textAnchor={labelPos.anchor}
                      dominantBaseline={labelPos.baseline}
                      fill={
                        isStart ? (isDark ? "#4ade80" : "#15803d") :
                        isEnd   ? (isDark ? "#f87171" : "#b91c1c") :
                                  (isDark ? "#f1f5f9" : "#1e293b")
                      }
                      fontWeight={showLabel ? 700 : 600}
                      stroke={isDark ? "#0f172a" : "white"}
                      strokeWidth={3 * k}
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

          {/* ズームコントロール */}
          <div className="absolute top-2 left-2 flex flex-col gap-1">
            {[
              { label: "＋", title: "拡大", onClick: () => zoomAt(ZOOM_STEP, dimsRef.current.w / 2, dimsRef.current.h / 2) },
              { label: "−", title: "縮小", onClick: () => zoomAt(1 / ZOOM_STEP, dimsRef.current.w / 2, dimsRef.current.h / 2) },
              { label: "⛶", title: "全体表示", onClick: () => setView(null) },
            ].map(({ label, title, onClick }) => (
              <button
                key={title}
                type="button"
                title={title}
                onClick={onClick}
                className="h-7 w-7 rounded-md border border-slate-200 dark:border-slate-600 bg-white/90 dark:bg-gray-800/90 text-slate-600 dark:text-slate-300 shadow-sm text-sm font-bold leading-none hover:bg-slate-50 dark:hover:bg-gray-700"
              >
                {label}
              </button>
            ))}
          </div>

          {/* ズームスライダー（対数スケール: 1〜MAX_ZOOM倍） */}
          <div className="absolute bottom-2 right-2 flex items-center gap-2 rounded-md border border-slate-200 dark:border-slate-600 bg-white/90 dark:bg-gray-800/90 px-2 py-1 shadow-sm">
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={Math.log(zoom) / Math.log(MAX_ZOOM)}
              onChange={(e) => {
                const target = Math.pow(MAX_ZOOM, Number(e.target.value));
                zoomAt(target / zoom, dimsRef.current.w / 2, dimsRef.current.h / 2);
              }}
              className="w-28 accent-blue-600"
              aria-label="ズーム倍率"
            />
            <span className="w-9 text-right text-[10px] tabular-nums text-slate-500 dark:text-slate-400">
              ×{zoom.toFixed(1)}
            </span>
          </div>
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
        ドラッグで移動・ホイール/ダブルクリックでズーム・ホバーで路線名・駅名を表示
      </div>
    </div>
  );
}
