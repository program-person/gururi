import { OmawariRoute } from "@/lib/api";

interface Props {
  route: OmawariRoute;
  rank: number;
  stationMap: Record<string, string>;
  lineMap: Record<string, string>;
}

export default function RouteCard({ route, rank, stationMap, lineMap }: Props) {
  const start = stationMap[route.path[0]?.stationId] ?? route.path[0]?.stationId;
  const end = stationMap[route.path.at(-1)?.stationId ?? ""] ?? route.path.at(-1)?.stationId;

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
          {rank}
        </span>
        <span className="text-sm text-gray-500">
          {start} → {end}
        </span>
      </div>

      <div className="mb-3 grid grid-cols-4 gap-2 text-center">
        <div>
          <p className="text-xs text-gray-400">駅数</p>
          <p className="text-lg font-bold text-blue-700">{route.stationCount}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">距離</p>
          <p className="text-lg font-bold">{route.totalDistance}<span className="text-xs">km</span></p>
        </div>
        <div>
          <p className="text-xs text-gray-400">所要時間</p>
          <p className="text-lg font-bold">{Math.floor(route.totalTime / 60) > 0 ? `${Math.floor(route.totalTime / 60)}h` : ""}{route.totalTime % 60}<span className="text-xs">分</span></p>
        </div>
        <div>
          <p className="text-xs text-gray-400">運賃(IC)</p>
          <p className="text-lg font-bold text-green-700">{route.fareIc}<span className="text-xs">円</span></p>
        </div>
      </div>

      <details className="text-xs text-gray-600">
        <summary className="cursor-pointer select-none text-blue-600 hover:underline">
          経路を表示（{route.path.length}駅）
        </summary>
        <div className="mt-2 flex flex-wrap gap-1">
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
                {i < route.path.length - 1 && <span className="text-gray-300">›</span>}
              </span>
            );
          })}
        </div>
      </details>
    </div>
  );
}
