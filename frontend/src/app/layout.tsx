import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "大回り乗車 ルート検索",
  description: "JR西日本 大阪近郊区間の大回り乗車ルート検索",
};

// 乗換案内の実ダイヤは transit.ls8h.com API 経由で取得しており、その一次データ
// （GTFS フィード）のライセンスが最終ユーザーへのクレジット表示を求めているため、
// フッターに出典を明示する。
//
// API の /feeds から attribution を動的に取る方法もあるが、ここでは採らない:
//   - /feeds は全国 1,145 フィード・746KB を返すのに対し、本アプリが参照するのは
//     backend の LINE_FEEDS に列挙した JR西日本の 20 フィードのみで、その attribution は
//     全件が下記の 1 種類に一致する（2026-08 時点で確認）
//   - LINE_FEEDS 自体が手書きの固定リストなので、路線追加時は必ずコードを触る。
//     動的取得にしても「自動追従」の利点は成立しない
const TIMETABLE_SOURCE = {
  attribution: "JRおでかけネット 駅時刻表",
  url: "https://timetable.jr-odekake.net/",
} as const;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="ja"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {/* ページが短いときもフッターが下端に来るよう、本文側で余白を吸わせる */}
        <div className="flex-1">{children}</div>
        <footer className="mt-8 border-t border-slate-200/80 dark:border-slate-700/60">
          <div className="mx-auto max-w-5xl px-3 py-6 text-xs leading-relaxed text-slate-500 dark:text-slate-400 sm:px-4 xl:max-w-6xl">
            <p>
              時刻表データ:{" "}
              <a
                href={TIMETABLE_SOURCE.url}
                target="_blank"
                rel="noopener noreferrer"
                className="underline decoration-slate-300 underline-offset-2 hover:text-slate-700 dark:decoration-slate-600 dark:hover:text-slate-200"
              >
                {TIMETABLE_SOURCE.attribution}
              </a>{" "}
              （
              <a
                href="https://api.transit.ls8h.com/"
                target="_blank"
                rel="noopener noreferrer"
                className="underline decoration-slate-300 underline-offset-2 hover:text-slate-700 dark:decoration-slate-600 dark:hover:text-slate-200"
              >
                transit.ls8h.com API
              </a>
              {" "}経由）
            </p>
            <p className="mt-1">
              一部区間の時刻は運転間隔からの推定値です。本サービスは個人開発によるもので、
              西日本旅客鉄道株式会社とは関係ありません。
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
