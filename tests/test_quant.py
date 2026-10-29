"""Offline tests for the XBRL peer statistics (no network)."""

import numpy as np
import pytest

from pecora.quant.metrics import BENEISH_INTERCEPT, beneish_components, beneish_m, compute_all, dso
from pecora.quant.peers import benjamini_hochberg, position
from pecora.quant.xbrl import calendar_year

# MiMedx FY2016 as originally filed (10-K accession 0001376339-17-000042)
T = {"revenue": 245_015_000, "cogs": 32_407_000, "receivables": 67_151_000, "inventory": 17_814_000,
     "net_income": 11_974_000, "cfo": 25_828_000, "total_assets": 193_263_000,
     "current_assets": 126_538_000, "ppe": 13_786_000, "depreciation": 3_333_000,
     "sga": 179_997_000, "current_liabilities": 50_732_000}
T1 = {"revenue": 187_296_000, "cogs": 20_202_000, "receivables": 53_755_000, "inventory": 7_460_000,
      "net_income": 29_446_000, "cfo": 18_807_000, "total_assets": 135_913_000,
      "current_assets": 96_310_000, "ppe": 9_475_000, "depreciation": 1_799_000,
      "sga": 133_384_000, "current_liabilities": 26_777_000}


def test_dso_matches_hand_calculation():
    assert dso(T, T1) == pytest.approx(67_151_000 / 245_015_000 * 365)


def test_beneish_components_match_definitions():
    c = beneish_components(T, T1)
    assert c["DSRI"] == pytest.approx((67_151 / 245_015) / (53_755 / 187_296))
    assert c["SGI"] == pytest.approx(245_015 / 187_296)
    assert c["TATA"] == pytest.approx((11_974 - 25_828) / 193_263)


def test_beneish_imputes_optional_components_as_neutral():
    t = {k: v for k, v in T.items() if k != "sga"}
    m, comps, imputed = beneish_m(t, T1)
    assert imputed == ["SGAI"] and comps["SGAI"] is None and m is not None


def test_beneish_requires_core_components():
    t = {k: v for k, v in T.items() if k != "receivables"}
    assert beneish_m(t, T1)[0] is None


def test_beneish_all_neutral_inputs():
    # Every index at 1 and zero accruals gives the intercept plus the index coefficients
    v = {"revenue": 100, "cogs": 50, "receivables": 10, "current_assets": 40, "ppe": 20,
         "total_assets": 100, "net_income": 5, "cfo": 5, "depreciation": 2, "sga": 10,
         "current_liabilities": 30}
    m, _, _ = beneish_m(v, dict(v))
    assert m == pytest.approx(BENEISH_INTERCEPT + 0.920 + 0.528 + 0.404 + 0.892 + 0.115 - 0.172 - 0.327)


def test_missing_inputs_give_none_not_errors():
    vals = compute_all({"revenue": 100}, {})
    assert all(v is None for k, v in vals.items())


def test_benjamini_hochberg_known_values():
    q = benjamini_hochberg({"a": 0.01, "b": 0.04, "c": 0.03, "d": 0.5})
    assert q["a"] == pytest.approx(0.04)
    assert q["c"] == pytest.approx(0.04 * 4 / 3) and q["b"] == pytest.approx(0.04 * 4 / 3)
    assert q["d"] == pytest.approx(0.5)


def test_benjamini_hochberg_is_monotone():
    p = {str(i): v for i, v in enumerate([0.001, 0.2, 0.03, 0.04, 0.9, 0.01])}
    q = benjamini_hochberg(p)
    by_p = sorted(p, key=p.get)
    assert all(q[a] <= q[b] for a, b in zip(by_p, by_p[1:]))
    assert all(q[k] >= p[k] for k in p)


def test_position_extreme_high_value():
    peers = np.arange(1, 100, dtype=float)
    r = position(1000.0, peers, "high")
    assert r["percentile"] == 100.0 and r["p_value"] == pytest.approx(1 / 100)


def test_position_direction_low():
    peers = np.arange(1, 100, dtype=float)
    assert position(0.0, peers, "low")["p_value"] == pytest.approx(1 / 100)
    assert position(0.0, peers, "high")["p_value"] == pytest.approx(1.0)


def test_position_median_value_is_unremarkable():
    peers = np.arange(1, 100, dtype=float)
    r = position(50.0, peers, "high")
    assert r["percentile"] == pytest.approx(50.0, abs=1) and r["robust_z"] == 0


def test_calendar_year_rule():
    assert calendar_year("2016-01-01", "2016-12-31") == 2016
    assert calendar_year("2015-04-25", "2016-04-29") == 2015   # mostly 2015
    assert calendar_year("2015-02-01", "2016-01-30") == 2015
