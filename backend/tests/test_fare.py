from pathlib import Path

import pytest

from app.fare import _lookup_fare, calc_direct_fare, compute_fare, load_fare_table
from app.graph import build_adjacency, load_graph_data
from app.models import FareBand

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GRAPH_PATH = DATA_DIR / "graph.json"


@pytest.fixture(scope="module")
def table():
    return load_fare_table()


@pytest.fixture(scope="module")
def adj():
    data = load_graph_data(GRAPH_PATH)
    return build_adjacency(data.edges)


# ------------------------------------------------------------------
# 帯境界（切り上げ）の回帰テスト: 3.5km などの端数が最終帯（最高額）に
# 落ちてしまっていた旧実装のバグの再発防止。
# ------------------------------------------------------------------

def test_lookup_fare_rounds_up_fractional_km():
    bands = [
        FareBand(to_km=3, fare=150),
        FareBand(to_km=6, fare=190),
        FareBand(to_km=10, fare=200),
    ]
    assert _lookup_fare(3.0, bands) == 150
    assert _lookup_fare(3.01, bands) == 190
    assert _lookup_fare(3.5, bands) == 190
    assert _lookup_fare(4.0, bands) == 190
    assert _lookup_fare(6.0, bands) == 190
    assert _lookup_fare(6.01, bands) == 200
    assert _lookup_fare(10.0, bands) == 200


def test_lookup_fare_raises_when_table_exceeded():
    bands = [FareBand(to_km=3, fare=150), FareBand(to_km=6, fare=190)]
    with pytest.raises(ValueError):
        _lookup_fare(6.01, bands)


# ------------------------------------------------------------------
# 電車特定区間(denshaku)表が使われること
# ------------------------------------------------------------------

def test_denshaku_table_used_within_area(adj, table):
    # 大阪 → 天王寺: 大阪環状線内、電車特定区間の中心部。
    km, ic, ticket = calc_direct_fare(adj, "osak", "tenn", table)
    assert km == pytest.approx(10.3, abs=0.05)
    assert ic == 240  # denshaku 11-15km帯
    assert ticket == ic  # ICOCA運賃=きっぷ運賃（JR西日本は1円単位運賃を未導入）


def test_trunk_table_used_outside_area(adj, table):
    # 大阪 → 米原: 琵琶湖線で電車特定区間の端(野洲)を越えるため幹線表。
    km, ic, ticket = calc_direct_fare(adj, "osak", "maib", table)
    assert km == pytest.approx(110.5, abs=1.0)
    assert ic == 1980  # 幹線 101-120km帯
    assert ticket == ic


def test_denshaku_extends_to_wakayama(adj, table):
    # 阪和線は改定前から和歌山まで電車特定区間
    # （改定前境界: 京都・西明石・和歌山・奈良・長尾）。
    # 大阪 → 和歌山 (約71km) は電特表 71-80km帯。
    km, ic, ticket = calc_direct_fare(adj, "osak", "waka", table)
    assert km == pytest.approx(71.0, abs=0.5)
    assert ic == 1300  # denshaku 71-80km帯
    assert ticket == ic


# ------------------------------------------------------------------
# 特定運賃（競合私鉄対抗の特定区間運賃、2025-04改定後も存続）
# ------------------------------------------------------------------

def test_specific_fare_osaka_kyoto(adj, table):
    # 大阪 → 京都: 表引きなら denshaku 41-45km帯(750円)だが特定運賃580円。
    km, ic, ticket = calc_direct_fare(adj, "osak", "kyot", table)
    assert km == pytest.approx(42.8, abs=0.5)
    assert ic == 580
    assert ticket == ic


def test_specific_fare_is_bidirectional(adj, table):
    _, ic_fwd, _ = calc_direct_fare(adj, "tenn", "waka", table)
    _, ic_rev, _ = calc_direct_fare(adj, "waka", "tenn", table)
    assert ic_fwd == ic_rev == 900


# ------------------------------------------------------------------
# 地方交通線（加古川線, line I）を含む経路で換算キロ(×1.1)が効くこと
# ------------------------------------------------------------------

def test_local_line_conversion_applied_for_long_local_only_trip(adj, table):
    # 加古川 → 西脇市: 加古川線のみ、営業キロ30.8km。
    # 換算キロ = 30.8 * 1.1 = 33.88 -> 切り上げ34km -> 幹線表31-35km帯(590円)。
    km, ic, ticket = calc_direct_fare(adj, "kkok", "nisi", table)
    assert km == pytest.approx(30.8, abs=0.1)
    assert ic == 590
    assert ticket == ic


def test_local_line_short_trip_uses_raw_km_fallback(adj, table):
    # 加古川 → 厄神: 加古川線のみ、営業キロ7.3km。
    # 幹線+地方交通線合計が10km以内のため、専用の地方交通線表(B表)が
    # 未確認である旨を踏まえ、営業キロそのままで幹線表を引く近似実装。
    km, ic, ticket = calc_direct_fare(adj, "kkok", "yakj", table)
    assert km == pytest.approx(7.3, abs=0.1)
    assert ic == 200  # 幹線 7-10km帯
    assert ticket == ic


# ------------------------------------------------------------------
# 関西空港線の加算運賃
# ------------------------------------------------------------------

def test_airport_surcharge_direct(adj, table):
    # 日根野 → 関西空港: りんくうタウン経由でも加算運賃は220円のみ（二重加算しない）。
    km, ic, ticket = calc_direct_fare(adj, "hine", "kixap", table)
    assert ic == 240 + 220  # denshaku(11-15km帯:240) + 加算運賃220
    assert ticket == ic


def test_airport_surcharge_rinkuu_leg(adj, table):
    km, ic, ticket = calc_direct_fare(adj, "hine", "rinkuu", table)
    assert ic == 180 + 160  # denshaku(4-6km帯:180) + 加算運賃160
    assert ticket == ic


# ------------------------------------------------------------------
# その他
# ------------------------------------------------------------------

def test_same_station_returns_zero(adj, table):
    from app.routing import shortest_route
    from app.models import OptimizeBy

    result = shortest_route(adj, "osak", "osak", OptimizeBy.distance)
    assert result is not None
    path, _total_km, _total_time = result
    assert compute_fare(adj, path, table) == 0


def test_unreachable_pair_returns_zero(adj, table):
    km, ic, ticket = calc_direct_fare(adj, "osak", "nonexistent-station", table)
    assert (km, ic, ticket) == (0.0, 0, 0)
