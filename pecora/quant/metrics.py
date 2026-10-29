"""
Accounting red-flag metrics from two years of line items (t = this year, t1 = prior year).

Every function takes plain dicts and returns a float or None (missing data), so the same
code scores the company and each of its peers.

Beneish M-score (Beneish 1999, 8-variable model):
  M = -4.84 + 0.920 DSRI + 0.528 GMI + 0.404 AQI + 0.892 SGI + 0.115 DEPI
      - 0.172 SGAI + 4.679 TATA - 0.327 LVGI
  M above -1.78 is the commonly used manipulation cutoff. DEPI, SGAI and LVGI are set to
  1 (neutral) when their inputs are missing; DSRI, GMI, AQI, SGI and TATA are required.
"""

BENEISH_COEF = {"DSRI": 0.920, "GMI": 0.528, "AQI": 0.404, "SGI": 0.892, "DEPI": 0.115,
                "SGAI": -0.172, "TATA": 4.679, "LVGI": -0.327}
BENEISH_INTERCEPT = -4.84
BENEISH_CUTOFF = -1.78
BENEISH_REQUIRED = {"DSRI", "GMI", "AQI", "SGI", "TATA"}


def _div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def _gross_margin(v: dict):
    if "revenue" not in v or "cogs" not in v:
        return None
    return _div(v["revenue"] - v["cogs"], v["revenue"])


def _soft_assets(v: dict):
    """1 - (current assets + net PP&E) / total assets: the share of assets that are hardest to verify."""
    if not all(k in v for k in ("current_assets", "ppe", "total_assets")):
        return None
    return 1 - _div(v["current_assets"] + v["ppe"], v["total_assets"])


def beneish_components(t: dict, t1: dict) -> dict:
    dsri = _div(_div(t.get("receivables"), t.get("revenue")), _div(t1.get("receivables"), t1.get("revenue")))
    gmi = _div(_gross_margin(t1), _gross_margin(t))
    aqi = _div(_soft_assets(t), _soft_assets(t1))
    sgi = _div(t.get("revenue"), t1.get("revenue"))

    def dep_rate(v):
        return _div(v.get("depreciation"), (v["depreciation"] + v["ppe"]) if "depreciation" in v and "ppe" in v else None)
    depi = _div(dep_rate(t1), dep_rate(t))
    sgai = _div(_div(t.get("sga"), t.get("revenue")), _div(t1.get("sga"), t1.get("revenue")))

    def leverage(v):
        if "current_liabilities" not in v:
            return None
        return _div(v["current_liabilities"] + v.get("long_term_debt", 0), v.get("total_assets"))
    lvgi = _div(leverage(t), leverage(t1))

    tata = None
    if "net_income" in t and "cfo" in t:
        tata = _div(t["net_income"] - t["cfo"], t.get("total_assets"))
    return {"DSRI": dsri, "GMI": gmi, "AQI": aqi, "SGI": sgi, "DEPI": depi,
            "SGAI": sgai, "TATA": tata, "LVGI": lvgi}


def beneish_m(t: dict, t1: dict) -> tuple[float | None, dict, list[str]]:
    """(M-score or None, components, names of components imputed as neutral 1.0)."""
    comps = beneish_components(t, t1)
    if any(comps[k] is None for k in BENEISH_REQUIRED):
        return None, comps, []
    imputed = [k for k, v in comps.items() if v is None]
    used = {k: (1.0 if v is None else v) for k, v in comps.items()}
    m = BENEISH_INTERCEPT + sum(BENEISH_COEF[k] * used[k] for k in used)
    return m, comps, imputed


def dso(t: dict, t1: dict):
    ratio = _div(t.get("receivables"), t.get("revenue"))
    return None if ratio is None else ratio * 365


def _growth(t, t1, item):
    return _div(t.get(item), t1.get(item))


def inventory_vs_sales_growth(t: dict, t1: dict):
    inv, rev = _growth(t, t1, "inventory"), _growth(t, t1, "revenue")
    return None if inv is None or rev is None else inv - rev


def deferred_revenue_index(t: dict, t1: dict):
    """(deferred revenue / sales) this year over last year. Below 1: less revenue left in reserve."""
    return _div(_div(t.get("deferred_revenue"), t.get("revenue")),
                _div(t1.get("deferred_revenue"), t1.get("revenue")))


# name -> (label, function(t, t1), direction): "high" means a high value is the red flag
METRICS = {
    "dso": ("Days sales outstanding", dso, "high"),
    "dsri": ("Receivables vs sales index (DSRI)", lambda t, t1: beneish_components(t, t1)["DSRI"], "high"),
    "tata": ("Accruals to assets (TATA)", lambda t, t1: beneish_components(t, t1)["TATA"], "high"),
    "inventory_vs_sales": ("Inventory growth minus sales growth", inventory_vs_sales_growth, "high"),
    "gmi": ("Gross margin index (GMI)", lambda t, t1: beneish_components(t, t1)["GMI"], "high"),
    "sgi": ("Sales growth index (SGI)", lambda t, t1: beneish_components(t, t1)["SGI"], "high"),
    "deferred_revenue": ("Deferred revenue to sales index", deferred_revenue_index, "low"),
    "beneish_m": ("Beneish M-score", lambda t, t1: beneish_m(t, t1)[0], "high"),
}


def compute_all(t: dict, t1: dict) -> dict:
    return {name: fn(t, t1) for name, (_, fn, _) in METRICS.items()}
