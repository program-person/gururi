"use client";

import { useEffect, useState } from "react";
import { api, OmawariRoute, Station } from "@/lib/api";
import StationSearch from "@/components/StationSearch";
import RouteCard from "@/components/RouteCard";

const APP_VERSION = "0.3.0";

type Mode = "free" | "fare" | "dest";

export const LINE_MAP: Record<string, string> = {
  C:  "大阪環状線",
  A:  "JR京都線・琵琶湖線",
  JK: "JR神戸線",
  G:  "JR宝塚線",
  T:  "JR東西線",
  H:  "学研都市線",
  Q:  "大和路線",
  F:  "おおさか東線",
  R:  "阪和線",
  D:  "奈良線",
  KS: "湖西線",
  NR: "北陸本線",
  KB: "草津線",
  KN: "関西本線",
  E:  "嵯峨野線",
  U:  "桜井線",
  W:  "和歌山線",
  HA: "羽衣支線",
};

const FARE_OPTIONS = [133, 143, 165, 198, 220, 253, 286, 330, 363, 396, 429, 462, 506, 550, 616];
const TIME_OPTIONS = [60, 120, 180, 240, 360, 480, 600];
const RESULTS_OPTIONS = [3, 5, 10, 20];

const MODE_LABELS: Record<Mode, string> = {
  free: "最長ルート",
  fare: "運賃で指定",
  dest: "駅間指定",
};

const MODE_DESCRIPTIONS: Record<Mode, string> = {
  free: "出発駅から最も多くの駅を回るルートを探索します",
  fare: "指定した運賃（直通運賃）で乗れる最長ルートを探索します",
  dest: "出発駅から到着駅まで最長ルートで移動します",
};

export default function Home() {
  const [stations, setStations] = useState<Station[]>([]);
  const [stationMap, setStationMap] = useState<Record<string, string>>({});
  const [stationGeo, setStationGeo] = useState<Record<string, { lat: number; lng: number }>>({});

  const [startStation, setStartStation] = useState<Station | null>(null);
  const [endStation, setEndStation] = useState<Station | null>(null);
  const [mode, setMode] = useState<Mode>("free");
  const [maxFare, setMaxFare] = useState(165);
  const [maxTimeMin, setMaxTimeMin] = useState(240);
  const [numResults, setNumResults] = useState(5);

  const [routes, setRoutes] = useState<OmawariRoute[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.stations().then((data) => {
      setStations(data);
      const sm: Record<string, string> = {};
      const geo: Record<string, { lat: number; lng: number }> = {};
      data.forEach((s) => {
        sm[s.id] = s.name;
        if (s.lat != null && s.lng != null) geo[s.id] = { lat: s.lat, lng: s.lng };
      });
      setStationMap(sm);
      setStationGeo(geo);
    });
  }, []);

  const canSearch =
    !!startStation &&
    !loading &&
    (mode !== "dest" || (!!endStation && endStation.id !== startStation?.id));

  const search = async () => {
    if (!startStation) return;
    setLoading(true);
    setError(null);
    setRoutes([]);
    try {
      let result: OmawariRoute[];
      if (mode === "fare") {
        result = await api.omawariByFare(startStation.id, maxFare, {
          maxTimeMin,
          numResults,
        });
      } else {
        result = await api.omawari(startStation.id, {
          endStationId: mode === "dest" ? endStation?.id : undefined,
          maxTimeMin,
          numResults,
        });
      }
      if (result.length === 0) {
        setError(
          mode === "dest"
            ? `${stationMap[startStation.id] ?? startStation.id} → ${stationMap[endStation?.id ?? ""] ?? endStation?.id} のルートが見つかりませんでした。時間制限を延ばしてみてください。`
            : "ルートが見つかりませんでした。条件を変えて試してください。"
        );
      }
      setRoutes(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "エラーが発生しました");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="mx-auto max-w-2xl px-4 py-8">
      {/* ヘッダー */}
      <div className="mb-6">
        <div className="flex items-baseline gap-2">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">大回り乗車 ルート検索</h1>
          <span className="text-xs text-gray-400 dark:text-gray-500">v{APP_VERSION}</span>
        </div>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          JR西日本 大阪近郊区間 — 18路線 / 260駅
        </p>
      </div>

      {/* 検索フォーム */}
      <div className="mb-6 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5 shadow-sm space-y-4">

        {/* モード選択 */}
        <div>
          <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">探索モード</label>
          <div className="flex gap-2">
            {(["free", "fare", "dest"] as Mode[]).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`flex-1 rounded-md px-3 py-2 text-xs font-medium transition-colors ${
                  mode === m
                    ? "bg-blue-600 text-white shadow-sm"
                    : "border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                }`}
              >
                {MODE_LABELS[m]}
              </button>
            ))}
          </div>
          <p className="mt-1.5 text-xs text-gray-400 dark:text-gray-500">{MODE_DESCRIPTIONS[mode]}</p>
        </div>

        {/* 出発駅 */}
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">出発駅</label>
          <StationSearch
            stations={stations}
            value={startStation}
            onChange={setStartStation}
            placeholder="例: 大阪、天王寺、京都..."
          />
        </div>

        {/* 到着駅（駅間指定モードのみ） */}
        {mode === "dest" && (
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">到着駅</label>
            <StationSearch
              stations={stations.filter((s) => s.id !== startStation?.id)}
              value={endStation}
              onChange={setEndStation}
              placeholder="例: 京都、神戸、和歌山..."
            />
          </div>
        )}

        {/* 運賃選択（運賃指定モードのみ） */}
        {mode === "fare" && (
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              最大運賃（IC）
              <span className="ml-1 text-xs font-normal text-gray-400 dark:text-gray-500">— 実際に乗車する区間の直通運賃</span>
            </label>
            <select
              value={maxFare}
              onChange={(e) => setMaxFare(Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
            >
              {FARE_OPTIONS.map((f) => (
                <option key={f} value={f}>{f}円</option>
              ))}
            </select>
          </div>
        )}

        {/* 時間・件数 */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">最大乗車時間</label>
            <select
              value={maxTimeMin}
              onChange={(e) => setMaxTimeMin(Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
            >
              {TIME_OPTIONS.map((t) => (
                <option key={t} value={t}>
                  {Math.floor(t / 60) > 0 ? `${Math.floor(t / 60)}時間` : ""}
                  {t % 60 > 0 ? `${t % 60}分` : ""}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">表示件数</label>
            <select
              value={numResults}
              onChange={(e) => setNumResults(Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
            >
              {RESULTS_OPTIONS.map((n) => (
                <option key={n} value={n}>{n}件</option>
              ))}
            </select>
          </div>
        </div>

        {/* 検索ボタン */}
        <button
          onClick={search}
          disabled={!canSearch}
          className="w-full rounded-md bg-blue-600 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-300 dark:disabled:bg-gray-600 dark:disabled:text-gray-400 flex items-center justify-center gap-2"
        >
          {loading && (
            <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
            </svg>
          )}
          {loading ? "探索中..." : "ルートを探索"}
        </button>
      </div>

      {/* エラー */}
      {error && (
        <div className="mb-4 rounded-md bg-red-50 dark:bg-red-900/30 p-3 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      {/* スケルトンUI（探索中） */}
      {loading && (
        <div>
          <div className="mb-3 h-5 w-24 rounded bg-gray-200 dark:bg-gray-700 animate-pulse" />
          <div className="flex flex-col gap-3">
            {Array.from({ length: numResults > 3 ? 3 : numResults }).map((_, i) => (
              <div
                key={i}
                className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm overflow-hidden animate-pulse"
              >
                <div className="px-4 pt-4 pb-3 space-y-3">
                  {/* 起終点 */}
                  <div className="flex items-center gap-2">
                    <div className="h-6 w-6 rounded-full bg-gray-200 dark:bg-gray-700" />
                    <div className="h-4 w-20 rounded bg-gray-200 dark:bg-gray-700" />
                    <div className="h-3 w-3 rounded bg-gray-100 dark:bg-gray-600" />
                    <div className="h-4 w-20 rounded bg-gray-200 dark:bg-gray-700" />
                  </div>
                  {/* 路線バッジ */}
                  <div className="flex gap-1">
                    <div className="h-5 w-20 rounded-full bg-gray-200 dark:bg-gray-700" />
                    <div className="h-5 w-16 rounded-full bg-gray-200 dark:bg-gray-700" />
                    <div className="h-5 w-24 rounded-full bg-gray-200 dark:bg-gray-700" />
                  </div>
                  {/* 数値サマリー */}
                  <div className="grid grid-cols-4 gap-2">
                    {[...Array(4)].map((_, j) => (
                      <div key={j} className="rounded-lg bg-gray-50 dark:bg-gray-700/50 py-2 flex flex-col items-center gap-1">
                        <div className="h-3 w-8 rounded bg-gray-200 dark:bg-gray-600" />
                        <div className="h-5 w-10 rounded bg-gray-200 dark:bg-gray-600" />
                      </div>
                    ))}
                  </div>
                </div>
                {/* フッター */}
                <div className="flex gap-2 border-t border-gray-100 dark:border-gray-700 px-4 py-2">
                  <div className="h-7 w-20 rounded-md bg-gray-100 dark:bg-gray-700" />
                  <div className="h-7 w-28 rounded-md bg-gray-100 dark:bg-gray-700" />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 結果 */}
      {!loading && routes.length > 0 && (
        <div>
          <h2 className="mb-3 text-base font-semibold text-gray-700 dark:text-gray-300">
            探索結果 {routes.length}件
          </h2>
          <div className="flex flex-col gap-3">
            {routes.map((r, i) => (
              <RouteCard
                key={i}
                route={r}
                rank={i + 1}
                stationMap={stationMap}
                lineMap={LINE_MAP}
                stationGeo={stationGeo}
              />
            ))}
          </div>
        </div>
      )}
    </main>
  );
}
