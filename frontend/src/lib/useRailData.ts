"use client";

/** 駅・路線のマスタデータ取得。検索ページと乗換案内ページで共通。 */
import { useEffect, useState } from "react";
import { api, Line, Station } from "./api";

// バックエンド /lines の取得前に使うフォールバック（一覧名のデフォルト）
// キーは graph.json の路線ID（JR西日本公式の路線記号に準拠）
export const LINE_MAP_FALLBACK: Record<string, string> = {
  O:  "大阪環状線",
  A:  "JR京都線・琵琶湖線・JR神戸線・北陸本線",
  G:  "JR宝塚線",
  H:  "JR東西線・学研都市線",
  Q:  "大和路線",
  F:  "おおさか東線",
  R:  "阪和線",
  D:  "奈良線",
  B:  "湖西線",
  C:  "草津線",
  V:  "関西本線",
  E:  "嵯峨野線",
  U:  "万葉まほろば線",
  T:  "和歌山線",
  S:  "関西空港線",
  HA: "羽衣支線",
  I:  "加古川線",
  P:  "JRゆめ咲線",
  J:  "播但線",
  W:  "紀勢本線",
};

export interface RailData {
  stations: Station[];
  stationMap: Record<string, string>;
  stationGeo: Record<string, { lat: number; lng: number }>;
  lineMap: Record<string, string>;
  lineCount: number;
}

export function useRailData(): RailData {
  const [stations, setStations] = useState<Station[]>([]);
  const [stationMap, setStationMap] = useState<Record<string, string>>({});
  const [stationGeo, setStationGeo] = useState<Record<string, { lat: number; lng: number }>>({});
  const [lineMap, setLineMap] = useState<Record<string, string>>(LINE_MAP_FALLBACK);
  // 表示用の路線数。/lines が取れるまではフォールバック表の件数を使う
  const [lineCount, setLineCount] = useState(Object.keys(LINE_MAP_FALLBACK).length);

  useEffect(() => {
    api.stations().then((data) => {
      setStations(data);
      const names: Record<string, string> = {};
      const geo: Record<string, { lat: number; lng: number }> = {};
      data.forEach((s) => {
        names[s.id] = s.name;
        if (s.lat != null && s.lng != null) geo[s.id] = { lat: s.lat, lng: s.lng };
      });
      setStationMap(names);
      setStationGeo(geo);
    }).catch(() => { /* 駅名はIDのまま表示される */ });

    api.lines().then((data: Line[]) => {
      const names: Record<string, string> = {};
      data.forEach((l) => { names[l.id] = l.name; });
      setLineMap((prev) => ({ ...prev, ...names }));
      if (data.length > 0) setLineCount(data.length);
    }).catch(() => { /* フォールバックを使う */ });
  }, []);

  return { stations, stationMap, stationGeo, lineMap, lineCount };
}
