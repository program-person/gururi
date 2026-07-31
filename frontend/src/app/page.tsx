"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { OmawariRoute, Station } from "@/lib/api";
import {
  DEFAULT_QUERY,
  Mode,
  SearchQuery,
  fromSearchParams,
  makeSeed,
  runSearch,
  searchHref,
} from "@/lib/searchQuery";
import { useRailData } from "@/lib/useRailData";
import StationSearch from "@/components/StationSearch";
import RouteCard from "@/components/RouteCard";
import { LINE_COLORS } from "@/components/RouteMap";

const APP_VERSION = "0.5.0";

// JR西日本 2025-04改定後の電車特定区間 普通運賃（fare_table.json の denshaku 帯と一致）。
// 大回りの出発駅はグラフ上ほぼ全て電車特定区間内のため denshaku 表の額を採用
const FARE_OPTIONS = [150, 180, 200, 240, 320, 410, 490, 580, 660];
// 「制限なし」はバックエンドの maxTimeMin 上限値（le=10000）を送って表現する。
// 0 を無制限センチネルにする旧仕様は廃止済み（バックエンドが ge=1 で拒否する）
const UNLIMITED_TIME_MIN = 10000;
const TIME_OPTIONS = [60, 120, 180, 240, 360, 480, 600, 1080, UNLIMITED_TIME_MIN];
const RESULTS_OPTIONS = [3, 5, 10, 20];

// サインバーに並べる路線記号（環状線から順に、色が隣り合って濁らない並び）
const SIGN_BAR_LINE_IDS = ["O", "A", "G", "H", "Q", "F", "R", "D", "B", "C", "E", "U", "T", "S", "I", "P", "J", "W"];

const MODE_LABELS: Record<Mode, string> = {
  free: "最長ルート",
  fare: "運賃で指定",
  dest: "駅間指定",
};

interface FormValues {
  mode: Mode;
  maxFare: number;
  maxTimeMin: number;
  numResults: number;
  startStation: Station | null;
  endStation: Station | null;
}

const MODE_DESCRIPTIONS: Record<Mode, string> = {
  free: "出発駅から最も多くの駅を回るルートを探索します",
  fare: "指定した運賃（直通運賃）で乗れる最長ルートを探索します",
  dest: "出発駅から到着駅まで最長ルートで移動します",
};

export default function Home() {
  // useSearchParams はプリレンダリング時に Suspense 境界を要求する
  return (
    <Suspense>
      <SearchPage />
    </Suspense>
  );
}

interface SearchResult {
  /** どのURLに対する結果か。これが現在のURLと一致しない間が「探索中」 */
  key: string;
  query: SearchQuery | null;
  routes: OmawariRoute[];
  error: string | null;
}

const EMPTY_RESULT: SearchResult = { key: "", query: null, routes: [], error: null };

function SearchPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { stations, stationMap, stationGeo, lineMap, lineCount } = useRailData();

  // 実行済みの検索はURLが唯一の情報源。こうしておくと、乗換案内ページから
  // 戻ったときやリロード・URL共有でも同じ結果がそのまま再現される
  const queryString = searchParams.toString();
  const urlQuery = useMemo(
    () => fromSearchParams(new URLSearchParams(queryString)),
    [queryString]
  );

  // フォームの入力値。URL由来の値を初期値とし、ユーザーが触った分だけ上書きする
  // （effect で state を同期すると余計な再レンダーを招くため、導出で済ませる）
  const [override, setOverride] = useState<Partial<FormValues>>({});
  const form: FormValues = {
    mode: override.mode ?? urlQuery?.mode ?? DEFAULT_QUERY.mode,
    maxFare: override.maxFare ?? urlQuery?.maxFare ?? DEFAULT_QUERY.maxFare,
    maxTimeMin: override.maxTimeMin ?? urlQuery?.maxTimeMin ?? DEFAULT_QUERY.maxTimeMin,
    numResults: override.numResults ?? urlQuery?.numResults ?? DEFAULT_QUERY.numResults,
    startStation:
      override.startStation !== undefined
        ? override.startStation
        : stations.find((s) => s.id === urlQuery?.startStationId) ?? null,
    endStation:
      override.endStation !== undefined
        ? override.endStation
        : stations.find((s) => s.id === urlQuery?.endStationId) ?? null,
  };
  const patch = (values: Partial<FormValues>) =>
    setOverride((prev) => ({ ...prev, ...values }));

  const [result, setResult] = useState<SearchResult>(EMPTY_RESULT);
  // ローディングは「結果がまだ現在のURLに追いついていない」ことから導出する
  const loading = urlQuery !== null && result.key !== queryString;
  const routes = result.key === queryString ? result.routes : [];
  const error = result.key === queryString ? result.error : null;

  useEffect(() => {
    if (urlQuery === null) return;
    let cancelled = false;
    runSearch(urlQuery)
      .then((found) => {
        if (cancelled) return;
        setResult({
          key: queryString,
          query: urlQuery,
          routes: found,
          error:
            found.length > 0
              ? null
              : urlQuery.mode === "dest"
                ? "指定した駅間のルートが見つかりませんでした。時間制限を延ばしてみてください。"
                : "ルートが見つかりませんでした。条件を変えて試してください。",
        });
      })
      .catch((e) => {
        if (cancelled) return;
        setResult({
          key: queryString,
          query: urlQuery,
          routes: [],
          error: e instanceof Error ? e.message : "エラーが発生しました",
        });
      });
    return () => { cancelled = true; };
  }, [queryString, urlQuery]);

  const { mode, maxFare, maxTimeMin, numResults, startStation, endStation } = form;

  const canSearch =
    !!startStation &&
    !loading &&
    (mode !== "dest" || (!!endStation && endStation.id !== startStation.id));

  const search = () => {
    if (!startStation) return;
    // 検索するたびに新しいシードを引く。URLに載るので、この結果はあとから再現できる
    setOverride({});
    router.push(
      searchHref({
        mode,
        startStationId: startStation.id,
        endStationId: mode === "dest" ? endStation?.id ?? null : null,
        maxFare,
        maxTimeMin,
        numResults,
        seed: makeSeed(),
      })
    );
  };

  return (
    <main className="mx-auto max-w-5xl px-3 py-5 sm:px-4 sm:py-8 xl:max-w-6xl">
      {/* 狭い画面は縦積み（フォーム→結果）、lg以上はフォームを左に固定して結果を横に並べる */}
      <div className="lg:flex lg:items-start lg:gap-6">
      {/* ヘッダー・検索フォームは読みやすい幅に絞り、結果カードは残り全幅を使う */}
      <div className="mx-auto max-w-2xl lg:mx-0 lg:w-88 lg:shrink-0 lg:sticky lg:top-6">
      {/* ヘッダー */}
      <div className="mb-6">
        {/* 路線記号カラーを並べたサインバー（JRの案内サインのライン帯を意識した装飾） */}
        <div className="mb-4 flex h-1 overflow-hidden rounded-full" aria-hidden="true">
          {SIGN_BAR_LINE_IDS.map((id) => (
            <span key={id} className="flex-1" style={{ backgroundColor: LINE_COLORS[id] }} />
          ))}
        </div>
        <div className="flex items-baseline gap-2">
          <h1 className="text-[22px] sm:text-[28px] font-bold leading-tight tracking-[-0.02em] text-slate-900 dark:text-white">
            大回り乗車 <span className="text-blue-700 dark:text-blue-400">ルート検索</span>
          </h1>
          <span className="font-mono text-[10px] text-slate-400 dark:text-slate-600">v{APP_VERSION}</span>
        </div>
        <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
          <span className="rounded-full bg-slate-900/5 px-2 py-0.5 font-medium text-slate-600 dark:bg-white/10 dark:text-slate-300">
            JR西日本 大阪近郊区間
          </span>
          {/* 路線数・駅数はグラフデータの実測値（ハードコードすると路線追加のたびに古くなる） */}
          {stations.length > 0 && (
            <span className="font-mono tabular-nums tracking-tight">
              {lineCount} lines / {stations.length} stations
            </span>
          )}
        </p>
      </div>

      {/* 検索フォーム */}
      <div className="mb-6 space-y-5 rounded-2xl border border-slate-200/80 bg-white/90 p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_8px_24px_-12px_rgba(15,23,42,0.15)] backdrop-blur-sm sm:p-6 dark:border-slate-700/80 dark:bg-slate-800/90">

        {/* モード選択: 枠付きボタンの並びより、切り替えであることが伝わるセグメンテッドコントロール */}
        <div>
          <label className="mb-2 block text-xs font-semibold tracking-wide text-slate-500 dark:text-slate-400">探索モード</label>
          <div className="flex gap-1 rounded-xl bg-slate-100 p-1 dark:bg-slate-900/60">
            {(["free", "fare", "dest"] as Mode[]).map((m) => (
              <button
                key={m}
                onClick={() => patch({ mode: m })}
                aria-pressed={mode === m}
                className={`min-h-10 flex-1 rounded-lg px-2 text-[13px] sm:text-sm font-medium transition-all duration-150 ${
                  mode === m
                    ? "bg-white text-blue-700 shadow-sm ring-1 ring-black/5 dark:bg-slate-700 dark:text-blue-300 dark:ring-white/10"
                    : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
                }`}
              >
                {MODE_LABELS[m]}
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs leading-relaxed text-slate-400 dark:text-slate-500">{MODE_DESCRIPTIONS[mode]}</p>
        </div>

        {/* 出発駅 */}
        <div>
          <label className="mb-1.5 block text-xs font-semibold tracking-wide text-slate-500 dark:text-slate-400">出発駅</label>
          <StationSearch
            stations={stations}
            value={startStation}
            onChange={(s) => patch({ startStation: s })}
            placeholder="例: 大阪、天王寺、京都..."
          />
        </div>

        {/* 到着駅（駅間指定モードのみ） */}
        {mode === "dest" && (
          <div>
            <label className="mb-1.5 block text-xs font-semibold tracking-wide text-slate-500 dark:text-slate-400">到着駅</label>
            <StationSearch
              stations={stations.filter((s) => s.id !== startStation?.id)}
              value={endStation}
              onChange={(s) => patch({ endStation: s })}
              placeholder="例: 京都、神戸、和歌山..."
            />
          </div>
        )}

        {/* 運賃選択（運賃指定モードのみ） */}
        {mode === "fare" && (
          <div>
            <label className="mb-1.5 block text-xs font-semibold tracking-wide text-slate-500 dark:text-slate-400">
              最大運賃（IC）
              <span className="ml-1 text-xs font-normal text-gray-400 dark:text-gray-500">— 実際に乗車する区間の直通運賃</span>
            </label>
            <select
              value={maxFare}
              onChange={(e) => patch({ maxFare: Number(e.target.value) })}
              className="min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base text-slate-900 transition-colors hover:border-slate-400 sm:text-sm dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100 dark:hover:border-slate-500"
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
            <label className="mb-1.5 block text-xs font-semibold tracking-wide text-slate-500 dark:text-slate-400">最大乗車時間</label>
            <select
              value={maxTimeMin}
              onChange={(e) => patch({ maxTimeMin: Number(e.target.value) })}
              className="min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base text-slate-900 transition-colors hover:border-slate-400 sm:text-sm dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100 dark:hover:border-slate-500"
            >
              {TIME_OPTIONS.map((t) => (
                <option key={t} value={t}>
                  {t === UNLIMITED_TIME_MIN
                    ? "制限なし"
                    : t === 1080
                      ? "終日（〜18時間）"
                      : `${Math.floor(t / 60) > 0 ? `${Math.floor(t / 60)}時間` : ""}${t % 60 > 0 ? `${t % 60}分` : ""}`
                  }
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-semibold tracking-wide text-slate-500 dark:text-slate-400">表示件数</label>
            <select
              value={numResults}
              onChange={(e) => patch({ numResults: Number(e.target.value) })}
              className="min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base text-slate-900 transition-colors hover:border-slate-400 sm:text-sm dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100 dark:hover:border-slate-500"
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
          className="flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-blue-700 py-2.5 text-base font-semibold text-white shadow-sm transition-all duration-150 hover:bg-blue-800 hover:shadow-md active:scale-[0.99] disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400 disabled:shadow-none dark:disabled:bg-slate-700 dark:disabled:text-slate-500"
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
        <div className="mb-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-900/30 dark:text-red-300">
          {error}
        </div>
      )}
      </div>

      {/* 結果カラム */}
      <div className="min-w-0 lg:flex-1">
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
          <h2 className="mb-3 flex items-baseline gap-2 text-sm font-semibold tracking-wide text-slate-500 dark:text-slate-400">
            探索結果
            <span className="font-mono text-base tabular-nums text-slate-900 dark:text-white">{routes.length}</span>
            <span className="text-xs font-normal text-slate-400">件</span>
          </h2>
          <div className="flex flex-col gap-3">
            {routes.map((r, i) => (
              <RouteCard
                key={i}
                route={r}
                rank={i + 1}
                stationMap={stationMap}
                lineMap={lineMap}
                stationGeo={stationGeo}
                query={result.query}
                routeIndex={i}
              />
            ))}
          </div>
        </div>
      )}
      </div>
      </div>
    </main>
  );
}
