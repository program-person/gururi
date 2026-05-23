"use client";

import { useEffect, useState } from "react";
import { api, OmawariRoute, Station } from "@/lib/api";
import StationSearch from "@/components/StationSearch";
import RouteCard from "@/components/RouteCard";

const APP_VERSION = "0.3.1";

type Mode = "free" | "fare" | "dest";

export const LINE_MAP: Record<string, string> = {
  C:  "螟ｧ髦ｪ迺ｰ迥ｶ邱・,
  A:  "JR莠ｬ驛ｽ邱壹・逅ｵ逅ｶ貉也ｷ・,
  JK: "JR逾樊虻邱・,
  G:  "JR螳晏｡夂ｷ・,
  T:  "JR譚ｱ隘ｿ邱・,
  H:  "蟄ｦ遐秘・蟶らｷ・,
  Q:  "螟ｧ蜥瑚ｷｯ邱・,
  F:  "縺翫♀縺輔°譚ｱ邱・,
  R:  "髦ｪ蜥檎ｷ・,
  D:  "螂郁憶邱・,
  KS: "貉冶･ｿ邱・,
  NR: "蛹鈴匣譛ｬ邱・,
  KB: "闕画ｴ･邱・,
  KN: "髢｢隘ｿ譛ｬ邱・,
  E:  "蠏ｯ蟲ｨ驥守ｷ・,
  U:  "譯應ｺ慕ｷ・,
  W:  "蜥梧ｭ悟ｱｱ邱・,
  HA: "鄒ｽ陦｣謾ｯ邱・,
};

const FARE_OPTIONS = [133, 143, 165, 198, 220, 253, 286, 330, 363, 396, 429, 462, 506, 550, 616];
const TIME_OPTIONS = [60, 120, 180, 240, 360, 480, 600];
const RESULTS_OPTIONS = [3, 5, 10, 20];

const MODE_LABELS: Record<Mode, string> = {
  free: "譛髟ｷ繝ｫ繝ｼ繝・,
  fare: "驕玖ｳ・〒謖・ｮ・,
  dest: "鬧・俣謖・ｮ・,
};

const MODE_DESCRIPTIONS: Record<Mode, string> = {
  free: "蜃ｺ逋ｺ鬧・°繧画怙繧ょ､壹￥縺ｮ鬧・ｒ蝗槭ｋ繝ｫ繝ｼ繝医ｒ謗｢邏｢縺励∪縺・,
  fare: "謖・ｮ壹＠縺滄°雉・ｼ育峩騾夐°雉・ｼ峨〒荵励ｌ繧区怙髟ｷ繝ｫ繝ｼ繝医ｒ謗｢邏｢縺励∪縺・,
  dest: "蜃ｺ逋ｺ鬧・°繧牙芦逹鬧・∪縺ｧ譛髟ｷ繝ｫ繝ｼ繝医〒遘ｻ蜍輔＠縺ｾ縺・,
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
            ? `${stationMap[startStation.id] ?? startStation.id} 竊・${stationMap[endStation?.id ?? ""] ?? endStation?.id} 縺ｮ繝ｫ繝ｼ繝医′隕九▽縺九ｊ縺ｾ縺帙ｓ縺ｧ縺励◆縲よ凾髢灘宛髯舌ｒ蟒ｶ縺ｰ縺励※縺ｿ縺ｦ縺上□縺輔＞縲Ａ
            : "繝ｫ繝ｼ繝医′隕九▽縺九ｊ縺ｾ縺帙ｓ縺ｧ縺励◆縲よ擅莉ｶ繧貞､峨∴縺ｦ隧ｦ縺励※縺上□縺輔＞縲・
        );
      }
      setRoutes(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "繧ｨ繝ｩ繝ｼ縺檎匱逕溘＠縺ｾ縺励◆");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="mx-auto max-w-2xl px-4 py-8">
      {/* 繝倥ャ繝繝ｼ */}
      <div className="mb-6">
        <div className="flex items-baseline gap-2">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">螟ｧ蝗槭ｊ荵苓ｻ・繝ｫ繝ｼ繝域､懃ｴ｢</h1>
          <span className="text-xs text-gray-400 dark:text-gray-500">v{APP_VERSION}</span>
        </div>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          JR隘ｿ譌･譛ｬ 螟ｧ髦ｪ霑鷹リ蛹ｺ髢・窶・18霍ｯ邱・/ 260鬧・
        </p>
      </div>

      {/* 讀懃ｴ｢繝輔か繝ｼ繝 */}
      <div className="mb-6 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5 shadow-sm space-y-4">

        {/* 繝｢繝ｼ繝蛾∈謚・*/}
        <div>
          <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">謗｢邏｢繝｢繝ｼ繝・/label>
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

        {/* 蜃ｺ逋ｺ鬧・*/}
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">蜃ｺ逋ｺ鬧・/label>
          <StationSearch
            stations={stations}
            value={startStation}
            onChange={setStartStation}
            placeholder="萓・ 螟ｧ髦ｪ縲∝､ｩ邇句ｯｺ縲∽ｺｬ驛ｽ..."
          />
        </div>

        {/* 蛻ｰ逹鬧・ｼ磯ｧ・俣謖・ｮ壹Δ繝ｼ繝峨・縺ｿ・・*/}
        {mode === "dest" && (
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">蛻ｰ逹鬧・/label>
            <StationSearch
              stations={stations.filter((s) => s.id !== startStation?.id)}
              value={endStation}
              onChange={setEndStation}
              placeholder="萓・ 莠ｬ驛ｽ縲∫･樊虻縲∝柱豁悟ｱｱ..."
            />
          </div>
        )}

        {/* 驕玖ｳ・∈謚橸ｼ磯°雉・欠螳壹Δ繝ｼ繝峨・縺ｿ・・*/}
        {mode === "fare" && (
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              譛螟ｧ驕玖ｳ・ｼ・C・・
              <span className="ml-1 text-xs font-normal text-gray-400 dark:text-gray-500">窶・螳滄圀縺ｫ荵苓ｻ翫☆繧句玄髢薙・逶ｴ騾夐°雉・/span>
            </label>
            <select
              value={maxFare}
              onChange={(e) => setMaxFare(Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
            >
              {FARE_OPTIONS.map((f) => (
                <option key={f} value={f}>{f}蜀・/option>
              ))}
            </select>
          </div>
        )}

        {/* 譎る俣繝ｻ莉ｶ謨ｰ */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">譛螟ｧ荵苓ｻ頑凾髢・/label>
            <select
              value={maxTimeMin}
              onChange={(e) => setMaxTimeMin(Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
            >
              {TIME_OPTIONS.map((t) => (
                <option key={t} value={t}>
                  {Math.floor(t / 60) > 0 ? `${Math.floor(t / 60)}譎る俣` : ""}
                  {t % 60 > 0 ? `${t % 60}蛻・ : ""}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">陦ｨ遉ｺ莉ｶ謨ｰ</label>
            <select
              value={numResults}
              onChange={(e) => setNumResults(Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
            >
              {RESULTS_OPTIONS.map((n) => (
                <option key={n} value={n}>{n}莉ｶ</option>
              ))}
            </select>
          </div>
        </div>

        {/* 讀懃ｴ｢繝懊ち繝ｳ */}
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
          {loading ? "謗｢邏｢荳ｭ..." : "繝ｫ繝ｼ繝医ｒ謗｢邏｢"}
        </button>
      </div>

      {/* 繧ｨ繝ｩ繝ｼ */}
      {error && (
        <div className="mb-4 rounded-md bg-red-50 dark:bg-red-900/30 p-3 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      {/* 繧ｹ繧ｱ繝ｫ繝医ΦUI・域爾邏｢荳ｭ・・*/}
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
                  {/* 襍ｷ邨らせ */}
                  <div className="flex items-center gap-2">
                    <div className="h-6 w-6 rounded-full bg-gray-200 dark:bg-gray-700" />
                    <div className="h-4 w-20 rounded bg-gray-200 dark:bg-gray-700" />
                    <div className="h-3 w-3 rounded bg-gray-100 dark:bg-gray-600" />
                    <div className="h-4 w-20 rounded bg-gray-200 dark:bg-gray-700" />
                  </div>
                  {/* 霍ｯ邱壹ヰ繝・ず */}
                  <div className="flex gap-1">
                    <div className="h-5 w-20 rounded-full bg-gray-200 dark:bg-gray-700" />
                    <div className="h-5 w-16 rounded-full bg-gray-200 dark:bg-gray-700" />
                    <div className="h-5 w-24 rounded-full bg-gray-200 dark:bg-gray-700" />
                  </div>
                  {/* 謨ｰ蛟､繧ｵ繝槭Μ繝ｼ */}
                  <div className="grid grid-cols-4 gap-2">
                    {[...Array(4)].map((_, j) => (
                      <div key={j} className="rounded-lg bg-gray-50 dark:bg-gray-700/50 py-2 flex flex-col items-center gap-1">
                        <div className="h-3 w-8 rounded bg-gray-200 dark:bg-gray-600" />
                        <div className="h-5 w-10 rounded bg-gray-200 dark:bg-gray-600" />
                      </div>
                    ))}
                  </div>
                </div>
                {/* 繝輔ャ繧ｿ繝ｼ */}
                <div className="flex gap-2 border-t border-gray-100 dark:border-gray-700 px-4 py-2">
                  <div className="h-7 w-20 rounded-md bg-gray-100 dark:bg-gray-700" />
                  <div className="h-7 w-28 rounded-md bg-gray-100 dark:bg-gray-700" />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 邨先棡 */}
      {!loading && routes.length > 0 && (
        <div>
          <h2 className="mb-3 text-base font-semibold text-gray-700 dark:text-gray-300">
            謗｢邏｢邨先棡 {routes.length}莉ｶ
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

