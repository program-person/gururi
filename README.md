# ぐるり — JR西日本 大阪近郊区間 大回り乗車ルート検索

大都市近郊区間の特例を使った「大回り乗車」のルートを探索・可視化し、実ダイヤに基づく乗換案内まで出す Web アプリケーションです。

- フロントエンド: https://gururi.vercel.app
- API: https://gururi-production.up.railway.app

```
出発駅を選ぶ → 最安運賃で乗れる最長ルートを探索 → 地図で確認 → 出発時刻を入れて乗換案内
```

## 目次

- [大回り乗車とは](#大回り乗車とは)
- [技術スタック](#技術スタック)
- [ディレクトリ構成](#ディレクトリ構成)
- [データモデル](#データモデル)
- [ロジック: 最短経路探索](#ロジック-最短経路探索)
- [ロジック: 大回りルート探索](#ロジック-大回りルート探索)
- [ロジック: 運賃計算](#ロジック-運賃計算)
- [ロジック: 時刻の算出](#ロジック-時刻の算出)
- [API リファレンス](#api-リファレンス)
- [セットアップ](#セットアップ)
- [テスト](#テスト)
- [デプロイ](#デプロイ)
- [既知の制限](#既知の制限)
- [データ出典](#データ出典)

---

## 大回り乗車とは

JR の旅客営業規則に定める大都市近郊区間の特例です。近郊区間内の駅どうしを乗車する場合、**同じ駅を二度通らない限り、実際に乗った経路にかかわらず最短経路の運賃で乗車できます**。

つまり「大阪から隣の駅まで」の切符（150円）で、近郊区間内を何時間もかけて大きく迂回してから目的地に着ける、という遊びが成立します。本アプリは大阪近郊区間を対象に、この「最も長く乗れる経路」を計算します。

**ルールと実装上の扱い** — 探索アルゴリズムはこれらを前提にしています。

| ルール | 実装 |
|---|---|
| 同一駅を二度通れない | 探索中に訪問済み駅を再訪しない |
| 途中下車できない | 経路の途中駅は通過のみとして扱う |
| 発駅と着駅が同一だと成立しない | 自由探索モードでは末尾1駅をトリムして別駅で終える |
| 近郊区間の外に出られない | グラフに近郊区間内の路線しか収録していない |

---

## 技術スタック

| レイヤー | 使用技術 |
|---|---|
| バックエンド | Python / FastAPI / Pydantic v2 / httpx |
| フロントエンド | Next.js 16 (App Router) / React / TypeScript / Tailwind CSS v4 |
| 地図描画 | 自前の SVG レンダラ（地図ライブラリ非依存） |
| データ生成 | Python スクリプト（国土数値情報 GeoJSON → shapely） |
| ホスティング | Railway（API）/ Vercel（フロント） |

外部の経路検索ライブラリ・地図ライブラリは使わず、グラフ構築・Dijkstra・ルート探索・SVG 描画をすべて自前で実装しています。

---

## ディレクトリ構成

```
train/
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI エントリポイント・全エンドポイント・バリデーション
│   │   ├── models.py      # Pydantic モデル（JSON camelCase ⇄ Python snake_case）
│   │   ├── graph.py       # グラフ読み込み・隣接リスト構築
│   │   ├── routing.py     # Dijkstra 最短経路
│   │   ├── omawari.py     # 大回りルート探索エンジン（本体・約1,400行）
│   │   ├── fare.py        # 運賃計算
│   │   ├── timetable.py   # レッグ分割・実ダイヤ組み立て・推定フォールバック
│   │   ├── transit.py     # transit.ls8h.com API クライアント（キャッシュつき）
│   │   ├── ratelimit.py   # 自作スライディングウィンドウ・レート制限
│   │   └── config.py      # pydantic-settings 設定
│   ├── data/
│   │   ├── graph.json                # 374駅・387エッジ・20路線（生成物）
│   │   ├── fare_table.json           # キロ程→運賃テーブル
│   │   └── transit_station_map.json  # 路線ID×駅ID → transit API 駅ID（生成物）
│   ├── generate_graph.py  # graph.json を再生成
│   └── tests/
├── scripts/
│   ├── extract_jrw_routes.py        # 国土数値情報N02 → 路線GeoJSON抽出
│   ├── sync_geo_from_n02.py         # 駅座標・駅間キロを N02 から同期
│   └── build_transit_station_map.py # transit API 駅IDマッピングを再生成
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── page.tsx           # トップ（検索UI・結果一覧）
│       │   ├── timetable/page.tsx # 乗換案内（共有可能な独立ページ）
│       │   └── layout.tsx         # 共通レイアウト・出典フッター
│       ├── components/
│       │   ├── StationSearch.tsx  # 駅名インクリメンタルサーチ
│       │   ├── RouteCard.tsx      # ルート1件のカード
│       │   └── RouteMap.tsx       # SVG路線図（ズーム・パン・ラベル衝突回避）
│       └── lib/
│           ├── api.ts          # バックエンドAPIクライアント
│           ├── searchQuery.ts  # 検索条件 ⇄ URLクエリ（シード持ち回り）
│           └── useRailData.ts  # 駅・路線データ取得フック
└── docs/
    └── fare_calculation.md  # 運賃計算の設計判断と検証記録
```

---

## データモデル

### グラフ

路線網を**無向重み付きグラフ**として表現します。駅がノード、駅間がエッジです。

```python
# graph.py
Adjacency = dict[str, list[tuple[str, str, float, float]]]
#            駅ID -> [(隣接駅ID, 路線ID, 営業キロ, 所要分), ...]
```

`build_adjacency()` はエッジを両方向に登録します。同一駅ペアに複数路線が並行する場合（例: 大阪〜尼崎は JR神戸線 と JR宝塚線）は、路線IDの異なるエッジが複数本張られます。

### 路線ID

JR西日本公式の路線記号に準拠しています。**A と H は複数の愛称路線が同一IDを共有**します（A = JR京都線・琵琶湖線・JR神戸線・北陸本線、H = JR東西線・学研都市線）。

| ID | 路線 | ID | 路線 |
|---|---|---|---|
| O | 大阪環状線 | D | 奈良線 |
| A | JR京都線・琵琶湖線・JR神戸線・北陸本線 | B | 湖西線 |
| G | JR宝塚線 | C | 草津線 |
| H | JR東西線・学研都市線 | V | 関西本線（非電化） |
| Q | 大和路線 | E | 嵯峨野線 |
| F | おおさか東線 | U | 万葉まほろば線 |
| R | 阪和線 | T | 和歌山線 |
| S | 関西空港線 | HA | 羽衣支線 |
| I | 加古川線 | J | 播但線 |
| P | JRゆめ咲線 | W | 紀勢本線（和歌山〜和歌山市） |

路線IDは3か所で参照されるため、**変更する場合は必ず全部を更新**してください。

- `backend/generate_graph.py`（グラフ生成）
- `frontend/src/components/RouteMap.tsx` の `LINE_COLORS`（路線色）
- `frontend/src/lib/useRailData.ts` の `LINE_MAP_FALLBACK`（路線名フォールバック）

### エッジの重み

| 項目 | 由来 |
|---|---|
| `distance`（営業キロ） | 国土数値情報 N02 の線路形状から機械算出（`scripts/sync_geo_from_n02.py`） |
| `travelTime`（所要分） | `generate_graph.py` に駅間ごとに手入力した整数分 |

`travelTime` は**普通列車の標準的な駅間所要時間**で、待ち時間は含みません。ルート探索の時間上限フィルタと、実ダイヤが取れない区間の乗車時間推定に使われます。

### グラフの再生成

`graph.json` は生成物です。**直接編集せず**、次の手順で再生成します。

```powershell
# 1. generate_graph.py にデータを追加・修正
# 2. 座標と営業キロを N02 から同期（新路線は LINE_ID_TO_N02 への登録が必要）
python scripts/sync_geo_from_n02.py --write
# 3. graph.json を生成
cd backend
python generate_graph.py
```

---

## ロジック: 最短経路探索

`routing.py` の `shortest_route()` は素直な Dijkstra です。運賃計算の基準となる「実際の最短経路」を求めるために使います。

- **重み**: `OptimizeBy.distance`（営業キロ）または `OptimizeBy.time`（所要分）で切り替え
- **戻り値**: `(path, total_distance, total_time)`。`path` は `(駅ID, その駅に到達した路線ID)` の列で、**先頭要素の路線IDは空文字**（起点のため）
- 到達不能なら `None`

この「先頭の路線IDが空」という規約は `PathSegment` として API のレスポンスにもそのまま出ており、フロントの経路描画とレッグ分割が依存しています。

`omawari.py` にはもう1つ `_shortest_avoiding()` があり、こちらは**指定した駅集合を通らない**最短経路（時間ベース）を返します。ゴールデンループ方式で「すでに通った区間を避けて次のジャンクションへ向かう」ために使います。

---

## ロジック: 大回りルート探索

`omawari.py` が本アプリの中心です。最長経路問題は NP困難なので厳密解は狙わず、**性質の異なる3つの生成器を走らせ、結果を混ぜて上位を返す**構成にしています。

### 評価スコア

すべての生成器が共通のスコア関数でルートを評価します（`_Route.score()`）。

```python
score = 使用路線数 × 10.0        # 路線多様性（主）
      + 総走行距離 × 0.5         # 走行距離（副）
      + 駅数       × 2.0         # タイブレーク（補助）
```

距離を最優先にすると「同じエリアで長い路線を往復するだけ」のルートが上位に来てしまいます。**路線多様性を主軸に置く**ことで、広域を縦横断する「大回りらしい」ルートが高く評価されます。

### 3つの生成レイヤー

| レイヤー | 性質 | 役割 |
|---|---|---|
| ウェイポイント方式 | 決定論的 | 既知の優良ルートを確実に出す |
| ゴールデンループ方式 | 決定論的 | 近郊区間を一周する最大ループ |
| FSA ランダムウォーク | 確率的 | 多様性・意外性の確保 |

#### 1. ウェイポイント方式

`WAYPOINT_ROUTES` に「(出発駅名, 到着駅名) → 経由地リスト」を定義しておき、`start → 経由地[0] → 経由地[1] → ... → end` の順に Dijkstra をつないで1本のルートにします。区間ごとに既訪問駅を `blocked` として渡すため、同一駅の再訪は起きません。

手で見つけた良いルートを確実に結果へ含めるための仕組みです。

#### 2. ゴールデンループ方式

大阪近郊区間を一周する定型の大ループ（`GOLDEN_LOOP`: 和歌山→高田→奈良→久宝寺→放出→木津→加茂→柘植→草津→米原→近江塩津→京都→新大阪→鴫野→京橋→尼崎→大阪→西九条→天王寺→和歌山）をジャンクション列として持ち、次の手順でルート化します。

1. `_expand_junction_path()` で各ジャンクション間を**指定路線のエッジのみ**を使った Dijkstra で駅レベルに展開
2. 展開した閉路を**出発駅が先頭に来るよう回転**
3. 終着駅が指定されていればそこで打ち切り、指定がなければ末尾1駅をトリム（発着同一駅を避けるため）

派生として神戸方面の支ループ（`KOBE_LOOP`）と、**短絡路線**（`SHORTCUTS`: 京都〜木津を奈良線で直結し、米原・草津・柘植・加茂経由を省略）による縮約版も生成します。

出発駅がループ上にない場合は `_nearest_in_set()` でループ上の最寄り駅を探して接続します。

**縮退の除去**: 終着駅を指定したとき、ループをほとんど回らずに素通りしただけの経路が出ることがあります。直通距離の `MIN_DETOUR_RATIO`（= 3.0）倍を下回る候補は捨てます。

#### 3. FSA ランダムウォーク

多様性を担う主力です。**3状態の有限オートマトン**で、状態ごとに隣接駅の選択重みを切り替えながらランダムウォークします（`_random_walk_fsa()`）。

| 状態 | 目的 | 重み式 |
|---|---|---|
| `DEPART` | 目的地から離れる | `目的地からの距離 × 2.0 + 新路線係数 × 3.0 + 残余次数 × 0.3` |
| `EXPLORE` | 新路線を開拓しつつ直進 | `新路線係数 × 3.0 × 同一路線係数 + 辺距離 × 0.5 + 残余次数 × 0.3` |
| `RETURN` | 目的地へ帰る | `1/(1+目的地からの距離) × 10.0 + 残余次数 × 0.5` |

- **新路線係数**: まだ乗っていない路線なら 3.0、既出なら 1.0。スコア関数の路線多様性項と整合させています
- **同一路線係数**: 直前と同じ路線なら 5.0。**1次マルコフ連鎖による「慣性」**で、1駅ごとに乗り換えるような非現実的な経路を抑えます
- **残余次数**: その駅の未訪問隣接数。行き止まりに突っ込みにくくします

**マルチアトラクター**: 各試行の前に `_build_attractor_chain()` で「互いに遠い中継目標」を2〜4個生成し、順に目指させます。候補は出発駅からの距離が中央値超の駅から選び、上位10件からランダムに1つ取ります。最後のアトラクターだけは目的地からの距離でペナルティをかけ、帰還しやすくします。

Dijkstra の距離マップは試行をまたいで `global_dist_cache` で共有し、再計算を避けています。

### モード別の組み立て

| モード | 呼び出し | 動作 |
|---|---|---|
| 終着駅指定 | `/omawari?endStationId=...` | ウェイポイント + ゴールデンループ + FSA（`end` へ到達したもののみ収集） |
| 自由探索 | `/omawari`（`endStationId` なし） | ゴールデンループ + FSA（**出発駅に戻るループ**として探索し、末尾1駅をトリム） |
| 運賃指定 | `/omawari/by-fare` | ランダムウォーク + スナップショット収集（下記） |

**運賃指定モード**（`find_omawari_by_fare()`）は他と方式が異なります。

1. `_max_km_for_fare()` で指定運賃から到達可能な最大キロ程を逆算
2. 出発駅からその距離以内の駅集合を `eligible_ends` として求める
3. ランダムウォーク中、`eligible_ends` の駅を**通過するたびにその時点のルートをスナップショット保存**

1回のウォークから複数の有効ルートが取れるため、探索効率が上がります。最後に実際の運賃を再計算し、`maxFare` を超えるものを落とします。

### 結果の合成

`_merge_result_layers()` が3レイヤーを統合します。ゴールデンループは出発駅によらずほぼ同じ形になるため、そのまま並べると結果が「一番大きいループとその変種」だけで埋まります。

```
1. ウェイポイント由来（全件）
2. ゴールデンループ由来（numResults × GOLDEN_RESULT_RATIO = 1/3 まで）
3. FSA 由来
4. 枠が余ったら、あふれたゴールデンループで埋め直す
```

各段階で**駅ID列をシグネチャとした重複排除**を行います。

### 再現性

`seed` パラメータで乱数を固定できます。同じシードなら同じルート集合が返るため、フロントは検索結果ページと乗換案内ページの間でシードを持ち回り、**共有された URL でも同じルートを再現**できるようにしています。

---

## ロジック: 運賃計算

`fare.py` の `compute_fare()` が経路から片道普通運賃を算出します。データは `backend/data/fare_table.json`（2025-04-01 改定準拠）。

> 設計判断と検証の記録は [`docs/fare_calculation.md`](docs/fare_calculation.md) にあります。

### 運賃表の種類

| 表 | 対象 | 収録範囲 |
|---|---|---|
| `denshaku` | 電車特定区間（大阪近郊の主要区間・212駅） | 〜200km |
| `trunk` | 幹線 | 〜200km |
| `local` | 地方交通線（B表） | 〜100km |

各表は「上限キロ程 → 運賃」の帯（`FareBand`）の配列です。B表だけは帯の刻みが不規則（1-3 / 4-6 / 7-10 / 11-15 / 16-20 / 21-23 / 24-28 / ...）で、11km以上の運賃額は幹線表と同額のまま境界だけがずれます。

### 判定フロー

```
経路（駅列 + エッジ列）
  │
  ├─① 発着駅ペアが specificFares（特定運賃・341ペア）に一致？
  │     └─ YES → その運賃を返す（表引きより常に安いため最優先）
  │
  ├─② 全駅が電車特定区間内（denshakuStationIds）？
  │     └─ YES → denshaku 表を営業キロで引く
  │
  ├─③ 地方交通線を含まない？
  │     └─ YES → trunk 表を営業キロで引く
  │
  ├─④ 全区間が地方交通線？
  │     └─ YES → local 表（B表）を営業キロで引く
  │
  └─⑤ 幹線と地方交通線が混在
        ├─ 合計 10km 以下 → local 表を営業キロ合計で引く
        └─ 合計 10km 超   → trunk 表を「運賃計算キロ」で引く
                             運賃計算キロ = 幹線営業キロ + 地方交通線営業キロ × 1.1

  最後に、関西空港線の加算運賃を加える
```

現在 `localLineIds` に登録されている地方交通線は **加古川線 (I) と播但線 (J)** の2線です。

### キロ程の端数処理

```python
km_ceiled = math.ceil(round(km, 6) - 1e-9)
```

JR の規則どおり**1km未満を切り上げ**てから帯を走査します。`round(km, 6)` と `- 1e-9` は、営業キロを合算した際の浮動小数点誤差（`3.0000000001` が 4km に切り上がってしまう）を吸収するためのものです。

### 特定運賃

競合私鉄に対抗して設定されている区間運賃です。**発着駅ペアで決まり、キロ程による表引きより優先**されます（常に表引きより安い額が設定されているため）。2025-04 改定のプレスリリース別紙4から pypdf で機械抽出し、グラフ収録駅間の全341ペアを転記しています。

### 関西空港線の加算運賃

加算運賃は規則上、**乗車券の発着駅（O-D）ごとに1回だけ**定まります。日根野〜関西空港は220円であり、りんくうタウンを経由しても「日根野〜りんくうタウン160円 + りんくうタウン〜関西空港170円 = 330円」にはなりません。

`_airport_surcharge()` は、経路が加算運賃区間の駅群に触れた**最初と最後の駅**を実際の O-D とみなし、一致する加算運賃を1件だけ適用します。

### IC 運賃ときっぷ運賃

JR西日本は1円単位運賃を導入していないため、`fareIc` と `fareTicket` は**常に同額**を返します。

---

## ロジック: 時刻の算出

`timetable.py` が経路から区間別の発着時刻を組み立てます。**実ダイヤを引ける区間は実ダイヤ、引けない区間は推定**というハイブリッド構成です。

### 1. レッグ分割

`split_legs()` が経路を**同一路線が連続する区間（レッグ）**に切ります。乗り換えが発生する地点が境界です。

```
path:  大阪(-) → 塚本(A) → 尼崎(A) → 立花(A) …
                 └─ すべて路線A ─┘
→ Leg(line_id="A", station_ids=("大阪","塚本","尼崎","立花",...))
```

レッグの両端は必ず同一路線上の駅になるため、「その路線に乗ったまま移動する区間」として外部APIに問い合わせられます。

### 2. 実ダイヤの照会

レッグごとに transit.ls8h.com API の `/plan` を叩きます（`transit.py`）。駅IDの対応表は `transit_station_map.json`（`scripts/build_transit_station_map.py --write` で生成）。

**採用条件**（`_pick_direct()`）— 次をすべて満たす最速の旅程だけを採用します。

- `transferCount == 0`（乗換なし）
- `kind == "transit"` のレッグがちょうど1本
- 出発秒 ≤ 到着秒

乗換ありの旅程しか返らない場合は、**プランナーが別経路に迂回した**（＝こちらの大回り経路と一致しない）と判断して棄却し、推定にフォールバックします。徒歩のみの旅程も `kind` の条件で落ちます。

2レッグ目以降は、前レッグ到着から `TRANSFER_BUFFER_MIN`（2分）以降に出る列車を検索します。日付をまたいで API が翌日の時刻を返した場合は 86400秒を加算して補正します。

APIレスポンスは `(from, to, 時刻)` をキーに 300秒キャッシュし、エントリ数の上限は 512 です（期限切れ→古い順に削除）。

### 3. 推定へのフォールバック

駅マッピングが無い区間・API障害・直通旅程が取れなかった場合は、運転間隔ベースの推定に切り替えます。

```
待ち時間 = 運転間隔 ÷ 2 + (乗り換えなら 3分)
乗車時間 = グラフの travelTime の単純合算
```

「運転間隔 ÷ 2」は、**時刻表を見ずにホームへ着いたときの待ち時間の期待値**です（到着時刻が一様分布だと仮定した場合の平均）。

**日中の運転間隔（分）** — `HEADWAY_MIN`

| 路線 | 間隔 | 路線 | 間隔 | 路線 | 間隔 |
|---|---|---|---|---|---|
| O 大阪環状線 | 4 | D 奈良線 | 15 | HA 羽衣支線 | 15 |
| A 東海道・山陽・北陸 | 8 | B 湖西線 | 15 | I 加古川線 | 30 |
| G JR宝塚線 | 8 | C 草津線 | 30 | P JRゆめ咲線 | 10 |
| H 東西・学研都市線 | 8 | V 関西本線 | 60 | J 播但線 | 30 |
| Q 大和路線 | 10 | E 嵯峨野線 | 10 | W 紀勢本線 | 60 |
| F おおさか東線 | 15 | U 万葉まほろば線 | 30 | （未定義路線） | 20 |
| R 阪和線 | 8 | T 和歌山線 | 30 | | |

推定を使ったレッグは `source: "estimate"` を返し、フロントは「目安」バッジを表示します。旅程全体では `hasEstimate` フラグで判別できます。

### 実ダイヤが取れない区間

| 区間 | 理由 |
|---|---|
| 奈良線 (D) | transit API 未収録 |
| 関西空港線 (S) | transit API 未収録 |
| JR東西線区間（尼崎〜京橋の東西線経由駅） | transit API 未収録（H は学研都市線のみ収録） |
| 赤穂線 西相生・坂越・播州赤穂 | どのフィードにも存在しない |
| 紀勢本線 和歌山〜和歌山市 (W) | 駅マッピング済みだが API が徒歩旅程しか返さない |

外部APIへの依存は `transit.py` 1ファイルに閉じ込めてあり、差し替え・撤去はこのファイルとマッピング生成スクリプトだけで済みます。

---

## API リファレンス

ベースURL: `http://localhost:8000`（開発）。起動後 `/docs` で Swagger UI が開きます。

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/health` | ヘルスチェック |
| GET | `/stations` | 全駅リスト（ID順） |
| GET | `/lines` | 全路線リスト |
| GET | `/route` | 2駅間の最短経路 |
| GET | `/fare` | 2駅間の直通運賃 |
| GET | `/omawari` | 大回りルート候補 |
| GET | `/omawari/by-fare` | 運賃指定の大回りルート候補 |
| POST | `/timetable` | ルートの区間別発着時刻 |

JSON は camelCase、Python 側は snake_case で相互変換します（Pydantic の `populate_by_name=True`）。

### `GET /route`

| パラメータ | 型 | 既定 | 説明 |
|---|---|---|---|
| `startStationId` | str | 必須 | 出発駅ID |
| `endStationId` | str | 必須 | 到着駅ID |
| `by` | `distance` \| `time` | `time` | 最適化基準 |

### `GET /omawari`

| パラメータ | 型 | 既定 | 制約 |
|---|---|---|---|
| `startStationId` | str | 必須 | |
| `endStationId` | str \| null | null | 省略で自由探索モード |
| `maxTimeMin` | float | 480.0 | 1〜10000 |
| `maxStations` | int | 120 | 5〜200 |
| `numResults` | int | 5 | 1〜20 |
| `seed` | int \| null | null | 0〜2147483647 |

```bash
curl "http://localhost:8000/omawari?startStationId=osak&maxTimeMin=300&numResults=3"
```

レスポンス（`OmawariRoute[]`）:

```jsonc
[
  {
    "path": [
      { "stationId": "osak", "lineId": "" },      // 先頭の lineId は常に空
      { "stationId": "ssin", "lineId": "A" },     // 大阪 → 新大阪（JR京都線）
      { "stationId": "msut", "lineId": "F" }      // 新大阪 → 南吹田（おおさか東線）
      // ... 最後は天満（大阪環状線）
    ],
    "totalDistance": 133.8,   // 総走行キロ
    "totalTime": 231.0,       // 総乗車分（待ち時間を含まない）
    "stationCount": 69,
    "directKm": 1.7,          // 発着駅間の最短キロ程（大阪〜天満）
    "fareIc": 150             // 実際に必要な運賃
  }
]
```

### `GET /omawari/by-fare`

`endStationId` と `maxStations` の代わりに `maxFare`（int, 100〜5000, 必須）を取ります。他は `/omawari` と同じです。

### `POST /timetable`

```jsonc
// リクエスト（大阪 → 新大阪 → JR野江。長いルートの先頭6駅を抜粋）
{
  "path": [
    { "stationId": "osak", "lineId": "" },
    { "stationId": "ssin", "lineId": "A" },
    { "stationId": "msut", "lineId": "F" },
    { "stationId": "jlwj", "lineId": "F" },
    { "stationId": "kjhk", "lineId": "F" },
    { "stationId": "jrne", "lineId": "F" }
  ],
  "departTime": "09:30"   // ^([01]?\d|2[0-3]):[0-5]\d$
}
```

```jsonc
// レスポンス（同一路線の連続区間が1レッグにまとまる）
{
  "departTime": "09:30",
  "arrivalTime": "10:00",
  "totalMin": 30.0,
  "hasEstimate": false,      // 全レッグが実ダイヤなら false
  "legs": [
    {
      "lineId": "A",
      "fromStationId": "osak",
      "toStationId": "ssin",
      "departure": "09:30",
      "arrival": "09:34",
      "waitMin": 0.0,
      "rideMin": 4.0,
      "source": "timetable",   // または "estimate"
      "trainType": "新快速",
      "headsign": "新快速 近江塩津"
    },
    {
      "lineId": "F",
      "fromStationId": "ssin",
      "toStationId": "jrne",   // 中間3駅は同一路線なので1レッグに集約
      "departure": "09:50",
      "arrival": "10:00",
      "waitMin": 16.0,
      "rideMin": 10.0,
      "source": "timetable",
      "trainType": "普通",
      "headsign": "普通 久宝寺"
    }
  ]
}
```

**バリデーション** — 任意の駅ペアを受け付けると外部APIへの踏み台にできてしまうため、`_validate_timetable_path()` で次を検証します。

- 2駅以上、`MAX_TIMETABLE_PATH_SEGMENTS`（400）以下
- 全駅がグラフに実在する
- **連続する駅が指定路線の実エッジで結ばれている**
- レッグ数が `MAX_TIMETABLE_LEGS`（40）以下（＝外部API呼び出し回数の上限）

### レート制限

`/omawari`・`/omawari/by-fare`・`/timetable` に IP単位のスライディングウィンドウ制限（既定 30回/60秒）が掛かります。超過時は `429` を返します。リバースプロキシ配下では `X-Forwarded-For` の先頭を実クライアントとして扱います。

---

## セットアップ

### 前提

- Python 3.10 以上（3.12 以上を推奨）
- Node.js 20 以上
- パッケージ管理: pip（venv）/ npm

### バックエンド

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

chcp 65001                        # Windows で日本語出力の文字化けを防ぐ
uvicorn app.main:app --reload     # http://localhost:8000
```

`scripts/sync_geo_from_n02.py` を動かす場合のみ、追加で `shapely` が必要です（`requirements.txt` には含めていない開発時依存）。

### フロントエンド

```powershell
cd frontend
npm install
npm run dev      # http://localhost:3000
```

ローカルのバックエンドへ向けるには `frontend/.env.local` を作成します。

```
API_PROXY_TARGET=http://localhost:8000
```

設定しない場合、フロントの `/api` リライトは**本番の Railway** を向きます。

### 環境変数

| 変数 | 既定 | 説明 |
|---|---|---|
| `JR_ROUTE_DATA_PATH` | `data/graph.json` | グラフデータのパス |
| `JR_ROUTE_ALLOW_ALL_ORIGINS` | `false` | CORS 全開放 |
| `JR_ROUTE_ALLOWED_ORIGINS` | `["http://localhost:3000"]` | CORS 許可オリジン（JSON配列） |
| `JR_ROUTE_RATE_LIMIT_ENABLED` | `true` | レート制限の有効化 |
| `JR_ROUTE_RATE_LIMIT_MAX_REQUESTS` | `30` | ウィンドウあたりの許可回数 |
| `JR_ROUTE_RATE_LIMIT_WINDOW_SECS` | `60.0` | ウィンドウ秒数 |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | SSR時のAPI URL |
| `API_PROXY_TARGET` | 本番 Railway URL | `/api` リライトの向き先 |

本番は CORS を開けず、フロントの `/api` プロキシ（サーバー間通信）経由で API を呼びます。

---

## テスト

```powershell
cd backend
.\venv\Scripts\Activate.ps1
pytest tests -v

# 単一テスト
pytest tests/test_route.py::test_dijkstra_by_distance -v
```

| ファイル | 対象 |
|---|---|
| `test_route.py` | Dijkstra（距離基準・時間基準・同一駅・到達不能）、`/route` API |
| `test_fare.py` | 端数切り上げ・表超過・表選択・電特・B表の不規則帯・換算キロ・加算運賃・特定運賃 |
| `test_omawari.py` | 迂回付き最短経路・ウェイポイント・ゴールデンループの閉路性・時間上限の遵守・結果が最大ループだけで埋まらないこと |
| `test_timetable.py` | レッグ分割・乗換0旅程の選択・推定フォールバック |
| `test_transit_cache.py` | 外部APIキャッシュのTTLと件数上限 |
| `test_ratelimit.py` | スライディングウィンドウ制限・`X-Forwarded-For` の扱い |
| `test_api_validation.py` | パラメータ境界・`/timetable` のパス検証 |

フロントエンドの型チェックとビルド:

```powershell
cd frontend
npx tsc --noEmit
npm run build
```

---

## デプロイ

Railway（API）と Vercel（フロント）がどちらも `main` ブランチを追従します。開発は `master` で行い、デプロイ時に両方へ push します。

```powershell
git push origin master        # 作業ブランチを更新（デプロイされない）
git push origin master:main   # 本番デプロイ（反映まで1〜2分）
```

---

## 既知の制限

| 項目 | 内容 |
|---|---|
| 営業キロの誤差 | N02 の線路形状由来のため公式営業キロと差がある（概ね0.6km、最大1km超）。運賃帯の境界付近で1帯ずれる可能性がある |
| B表の最終帯 | 92〜100km = 1,880円 は構造から導かれる額と一致せず**要検証**。グラフ内の地方交通線はこの帯に到達しないため実害はない |
| 運賃表の収録範囲 | 幹線・電特は200km、B表は100kmまで。超過すると `ValueError` → HTTP 400 |
| 行き止まり駅の自由探索 | 姫路以西・播但線・紀勢支線のような枝の駅を出発点にすると `/omawari`（自由探索）は0件になる。「出発駅に戻るループ」方式のため。終着駅指定と運賃指定は正常に動作する |
| 実ダイヤ未対応区間 | [推定へのフォールバック](#3-推定へのフォールバック)を参照 |
| 路線色 J / W | 公式カラーコードの一次資料が見つからず、車体色からの近似値 |
| ダークモード | 実機での見え方は**未検証** |

---

## データ出典

| データ | 出典 |
|---|---|
| 駅座標・駅間キロ・路線形状 | [国土数値情報 N02（鉄道）](https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N02.html) 国土交通省 |
| 府県境界 | 国土数値情報 N03（行政区域） 国土交通省 |
| 運賃表 | [JR西日本 2025-04-01 運賃改定プレスリリース](https://www.westjr.co.jp/press/article/items/240515_00_press_keihanshin_unchin.pdf)。地方交通線B表は [jr-group.jp](https://jr-group.jp/nishinihon-fare/)（二次資料）＋実売運賃との突合で検証 |
| 実ダイヤ | [JRおでかけネット 駅時刻表](https://timetable.jr-odekake.net/)（[transit.ls8h.com API](https://api.transit.ls8h.com/) 経由） |

transit.ls8h.com は個人運営の無償・認証不要APIです。SLA も利用規約も明示されていないため、依存は `transit.py` に隔離しています。一次データ（GTFSフィード）のライセンスが最終ユーザーへのクレジット表示を求めているため、アプリのフッターに出典を明示しています。

**本サービスは個人開発によるものであり、西日本旅客鉄道株式会社とは関係ありません。** 表示される時刻・運賃は参考値です。実際の乗車にあたっては公式の時刻表・運賃をご確認ください。
