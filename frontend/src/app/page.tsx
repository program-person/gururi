"use client";

import { useEffect, useState } from "react";
import { api, OmawariRoute, Station } from "@/lib/api";
import StationSearch from "@/components/StationSearch";
import RouteCard from "@/components/RouteCard";

type Mode = "free" | "fare";

const FARE_OPTIONS = [133, 143, 165, 198, 220, 253, 286, 330, 363, 396, 429, 462];
const TIME_OPTIONS = [60, 120, 180, 240, 360, 480];

const LINE_MAP: Record<string, string> = {
  C: "大阪環状線",
  A: "JR京都線・琵琶湖線",
  JK: "JR神戸線",
  G: "JR宝塚線",
  T: "JR東西線",
  H: "学研都市線",
  Q: "大和路線",
  F: "おおさか東線",
  R: "阪和線",
  D: "奈良線",
};

export default function Home() {
  const [stations, setStations] = useState<Station[]>([]);
  const [stationMap, setStationMap] = useState<Record<string, string>>({});
  const [stationGeo, setStationGeo] = useState<Record<string, { lat: number; lng: number }>>({});

  const [startStation, setStartStation] = useState<Station | null>(null);
  const [mode, setMode] = useState<Mode>("free");
  const [maxFare, setMaxFare] = useState(165);
  const [maxTimeMin, setMaxTimeMin] = useState(240);

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

  const search = async () => {
    if (!startStation) return;
    setLoading(true);
    setError(null);
    setRoutes([]);
    try {
      const result =
        mode === "fare"
          ? await api.omawariByFare(startStation.id, maxFare, { maxTimeMin, numResults: 5 })
          : await api.omawari(startStation.id, { maxTimeMin, numResults: 5 });
      if (result.length === 0) {
        setError("ルートが見つかりませんでした。条件を変えて試してください。");
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
      <h1 className="mb-1 text-2xl font-bold text-gray-900">大回り乗車 ルート検索</h1>
      <p className="mb-6 text-sm text-gray-500">JR西日本 大阪近郊区間</p>

      <div className="mb-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="mb-4">
          <label className="mb-1 block text-sm font-medium text-gray-700">出発駅</label>
          <StationSearch
            stations={stations}
            value={startStation}
            onChange={setStartStation}
            placeholder="例: 大阪、天王寺、京都..."
          />
        </div>

        <div className="mb-4">
          <label className="mb-1 block text-sm font-medium text-gray-700">探索モード</label>
          <div className="flex gap-3">
            <button
              onClick={() => setMode("free")}
              className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
                mode === "free"
                  ? "bg-blue-600 text-white"
                  : "border border-gray-300 text-gray-600 hover:bg-gray-50"
              }`}
            >
              最長ルート
            </button>
            <button
              onClick={() => setMode("fare")}
              className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
                mode === "fare"
                  ? "bg-blue-600 text-white"
                  : "border border-gray-300 text-gray-600 hover:bg-gray-50"
              }`}
            >
              運賃で指定
            </button>
          </div>
        </div>

        {mode === "fare" && (
          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium text-gray-700">最大運賃（IC）</label>
            <select
              value={maxFare}
              onChange={(e) => setMaxFare(Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            >
              {FARE_OPTIONS.map((f) => (
                <option key={f} value={f}>{f}円</option>
              ))}
            </select>
          </div>
        )}

        <div className="mb-4">
          <label className="mb-1 block text-sm font-medium text-gray-700">最大乗車時間</label>
          <select
            value={maxTimeMin}
            onChange={(e) => setMaxTimeMin(Number(e.target.value))}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
          >
            {TIME_OPTIONS.map((t) => (
              <option key={t} value={t}>
                {t >= 60 ? `${t / 60}時間${t % 60 > 0 ? `${t % 60}分` : ""}` : `${t}分`}
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={search}
          disabled={!startStation || loading}
          className="w-full rounded-md bg-blue-600 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-300"
        >
          {loading ? "探索中..." : "ルートを探索"}
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>
      )}

      {routes.length > 0 && (
        <div>
          <h2 className="mb-3 text-base font-semibold text-gray-700">
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
