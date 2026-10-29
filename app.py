"""
Pecora.ai demo UI

    streamlit run app.py

Three modes:
  - Case files: load saved results from outputs/adversarial (no API calls,
    works offline, and is your backup if venue wifi fails)
  - Live run: runs the full pipeline against EDGAR
  - Numbers check: peer distributions from SEC XBRL (outputs/quant), no LLM
"""
import glob
import html
import json
import os

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()  # SEC_EMAIL and ANTHROPIC_API_KEY for the live modes

RESULTS_DIR = "outputs/adversarial"
QUANT_DIR = "outputs/quant"
BENEISH_CUTOFF = -1.78  # same as pecora.quant.metrics; not imported so the viewer stays light

st.set_page_config(page_title="Pecora.ai", page_icon="⚖️", layout="wide")

# Case-file aesthetic: paper, serif body, mono citations, red and blue ink
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:wght@400;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');
html, body, [class*="css"], .stMarkdown, p, li { font-family: 'Source Serif 4', Georgia, serif; }
h1, h2, h3 { font-family: 'Source Serif 4', Georgia, serif; font-weight: 700; letter-spacing: -0.01em; }
.case-head { border-top: 3px double currentColor; border-bottom: 1px solid rgba(128,128,128,.4);
             padding: .6rem 0; margin-bottom: 1rem; font-family: 'IBM Plex Mono', monospace;
             font-size: .8rem; text-transform: uppercase; letter-spacing: .08em; opacity: .8; }
.signal { font-size: 4.2rem; font-weight: 700; line-height: 1; }
.signal-label { font-family: 'IBM Plex Mono', monospace; font-size: .75rem; text-transform: uppercase;
                letter-spacing: .1em; opacity: .7; }
.brief { border-left: 4px solid; padding: .4rem 0 .4rem 1rem; margin: .4rem 0 1rem; }
.brief.auditor { border-color: #b3261e; }
.brief.defender { border-color: #1f4e8c; }
.brief h4 { margin: 0 0 .3rem; font-size: .8rem; font-family: 'IBM Plex Mono', monospace;
            text-transform: uppercase; letter-spacing: .1em; }
.auditor h4 { color: #b3261e; } .defender h4 { color: #1f4e8c; }
.cite { font-family: 'IBM Plex Mono', monospace; font-size: .8rem; background: rgba(128,128,128,.12);
        padding: .35rem .5rem; margin: .3rem 0; border-radius: 2px; }
.stamp { display: inline-block; font-family: 'IBM Plex Mono', monospace; font-weight: 500;
         font-size: 1.05rem; letter-spacing: .15em; padding: .3rem .8rem; border: 2px solid;
         transform: rotate(-2deg); }
.UPHELD { color: #b3261e; } .DISMISSED { color: #2e7d32; } .INCONCLUSIVE { color: #9a6700; }
.ERROR { color: gray; }
.ok { color: #2e7d32; } .bad { color: #b3261e; }
</style>
""", unsafe_allow_html=True)


def esc(s) -> str:
    return html.escape(str(s or ""))


def md(s) -> str:
    """Model text for st.write/st.caption: escape $ so dollar amounts don't render as LaTeX."""
    return str(s or "").replace("$", "\\$")


def load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def cite_line(quote: str, pid: str, check: dict | None) -> str:
    mark = ""
    if check is not None:
        status = check.get("status")
        if check.get("verified"):
            mark = '<span class="ok">✓ verified</span>'
        elif status == "altered":
            mark = f'<span class="bad">✗ altered: {esc("; ".join(check.get("changes", [])))}</span>'
        elif status == "wrong_passage":
            mark = f'<span class="bad">✗ quote is from {esc(check.get("found_in"))}, not {esc(pid)}</span>'
        else:
            mark = f'<span class="bad">✗ not found ({check.get("score", 0):.2f})</span>'
    return f'<div class="cite">[{esc(pid)}] “{esc(quote)}” &nbsp; {mark}</div>'


def render_debate(d: dict, n: int):
    f, adj = d["finding"], d.get("adjudication", {})
    checks = d.get("citations", {}).get("checks", [])
    by_agent = {(c["agent"], c["index"]): c for c in checks}

    title = f"{n}. {f.get('title', 'Untitled')}  ·  {d['verdict']}  ·  {d['final_confidence']}%"
    with st.expander(title, expanded=(n == 1)):
        st.caption(md(f"{f.get('severity', '')} · {f.get('section', '')} · focus: {f.get('focus_area', '')}"))
        if d.get("error"):
            st.error(d["error"])
            return

        left, right = st.columns(2)
        with left:
            a = d.get("auditor", {})
            body = f'<div class="brief auditor"><h4>Auditor · the case against</h4>{esc(a.get("argument"))}'
            for i, kp in enumerate(a.get("key_points", []) or []):
                body += f"<p><b>{i + 1}.</b> {esc(kp.get('point'))}</p>"
                body += cite_line(kp.get("quote"), kp.get("passage_id"), by_agent.get(("auditor", i + 1)))
            st.markdown(body + "</div>", unsafe_allow_html=True)
        with right:
            df = d.get("defender", {})
            body = f'<div class="brief defender"><h4>Defender · the company\'s side</h4>{esc(df.get("argument"))}'
            for i, rb in enumerate(df.get("rebuttals", []) or []):
                body += f"<p><b>re {esc(rb.get('responds_to'))}.</b> {esc(rb.get('point'))}</p>"
                body += cite_line(rb.get("quote"), rb.get("passage_id"), by_agent.get(("defender", i + 1)))
            for c in df.get("concessions", []) or []:
                body += f"<p><i>Concedes:</i> {esc(c)}</p>"
            st.markdown(body + "</div>", unsafe_allow_html=True)

        st.markdown("#### Adjudication")
        c1, c2 = st.columns([1, 3])
        with c1:
            st.markdown(f'<span class="stamp {d["verdict"]}">{d["verdict"]}</span>', unsafe_allow_html=True)
            st.metric("Confidence", f"{d['final_confidence']}%",
                      delta=(f"{d['final_confidence'] - d['raw_confidence']} citation penalty"
                             if d["final_confidence"] != d["raw_confidence"] else None))
        with c2:
            st.write(md(adj.get("reasoning")))
            st.markdown(cite_line(adj.get("decisive_quote"), adj.get("decisive_passage_id"),
                                  by_agent.get(("adjudicator", 1))), unsafe_allow_html=True)
            st.caption(f"Would change my mind: {md(adj.get('what_would_change_my_mind'))}")
        for flag in d.get("flags", []):
            st.warning(flag)

        with st.popover("Evidence passages"):
            for p in d.get("evidence", []):
                st.markdown(f"**{p['id']}** · {p['section']}")
                st.text(p["text"])


def render_result(r: dict):
    m, s = r["meta"], r["summary"]
    st.markdown(f'<div class="case-head">Case file · {esc(m.get("ticker"))} · FY{esc(m.get("fiscal_year"))}'
                f' · {"anonymized" if m.get("anonymized") else "NOT anonymized"}'
                f' · filed {esc(m.get("filing_date", "n/a"))}</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    signal = "n/a" if s["signal_score"] is None else s["signal_score"]
    c1.markdown(f'<div class="signal">{signal}</div>'
                f'<div class="signal-label">Adversarial signal / 100</div>', unsafe_allow_html=True)
    c2.metric("Upheld", s["verdicts"].get("UPHELD", 0))
    c3.metric("Dismissed", s["verdicts"].get("DISMISSED", 0))
    ci = s.get("citation_integrity")
    c4.metric("Citations verified", f"{ci * 100:.0f}%" if ci is not None else "n/a")
    st.divider()
    for i, d in enumerate(r["debates"], 1):
        render_debate(d, i)


def render_backtest(b: dict):
    st.markdown('<div class="case-head">Backtest · target vs control</div>', unsafe_allow_html=True)
    gap = "n/a" if b["signal_gap"] is None else f"{b['signal_gap']:+}"
    st.markdown(f'<div class="signal">{gap}</div>'
                f'<div class="signal-label">Signal gap: target minus control</div>', unsafe_allow_html=True)
    st.bar_chart({f"{r['ticker']} FY{r['fiscal_year']} ({r['role']})": r["signal_score"]
                  for r in b["rows"] if r["signal_score"] is not None}, horizontal=True)
    st.dataframe([{k: v for k, v in r.items() if k != "result_file"} for r in b["rows"]],
                 hide_index=True, width="stretch")
    # Streamlit cannot nest expanders, so pick a case file to open below
    rows = [r for r in b["rows"] if os.path.exists(r["result_file"])]
    if rows:
        st.divider()
        pick = st.selectbox("Open case file", rows,
                            format_func=lambda r: f"{r['ticker']} FY{r['fiscal_year']} ({r['role']})")
        render_result(load_json(pick["result_file"]))


def peer_range(dist: np.ndarray, value: float) -> tuple[float, float]:
    """Axis range: 3 IQRs beyond the quartiles (ratio metrics have huge outliers), always showing the company."""
    q1, q3 = np.percentile(dist, [25, 75])
    lo, hi = max(dist.min(), q1 - 3 * (q3 - q1)), min(dist.max(), q3 + 3 * (q3 - q1))
    return min(lo, value), max(hi, value)


def peer_chart(row: dict) -> alt.Chart:
    """Peer histogram with the company (solid) and peer median (dashed) marked."""
    dist = np.array(row["distribution"])
    lo, hi = peer_range(dist, row["value"])
    shown = pd.DataFrame({"value": dist[(dist >= lo) & (dist <= hi)]})
    ink = "#b3261e" if row["flagged"] else "#1f4e8c"
    bars = alt.Chart(shown).mark_bar(opacity=.55, color="gray").encode(
        x=alt.X("value:Q", bin=alt.Bin(maxbins=30, extent=[lo, hi]), title=None),
        y=alt.Y("count():Q", title="peers"))
    median = alt.Chart(pd.DataFrame({"x": [row["peer_median"]]})).mark_rule(
        strokeDash=[4, 3], color="gray").encode(x="x:Q")
    company = alt.Chart(pd.DataFrame({"x": [row["value"]]})).mark_rule(size=3, color=ink).encode(x="x:Q")
    layers = bars + median + company
    if row["name"] == "beneish_m" and lo <= BENEISH_CUTOFF <= hi:
        layers += alt.Chart(pd.DataFrame({"x": [BENEISH_CUTOFF]})).mark_rule(
            strokeDash=[1, 2], size=2, color="#9a6700").encode(x="x:Q")
    return layers.properties(height=170)


def render_peers(r: dict):
    m, b = r["meta"], r["beneish"]
    st.markdown(f'<div class="case-head">Numbers check · {esc(m["name"])} · FY{m["fiscal_year"]}'
                f' · peers: {esc(m["peer_group"])}, n={m["peers"]} · frames CY{m["calendar_year"]}'
                f' · original 10-K {esc(m["accession"])}</div>', unsafe_allow_html=True)
    flagged = [x for x in r["metrics"] if x["flagged"]]
    c1, c2, c3 = st.columns([2, 1, 1])
    c1.markdown(f'<div class="signal">{len(flagged)}</div><div class="signal-label">'
                f'metrics unusual vs peers (BH q ≤ {m["flag_q"]})</div>', unsafe_allow_html=True)
    c2.metric("Beneish M-score", "n/a" if b["m"] is None else f"{b['m']:.2f}",
              delta=None if b["m"] is None else f"{b['m'] - b['cutoff']:+.2f} vs {b['cutoff']} cutoff",
              delta_color="inverse")
    c3.metric("Peers", m["peers"])

    st.dataframe(pd.DataFrame([{
        "metric": x["label"], "company": x["value"], "peer median": x.get("peer_median"),
        "percentile": x.get("percentile"), "robust z": x.get("robust_z"), "p": x.get("p_value"),
        "q (BH)": x["q_value"], "flagged": x["flagged"], "peers n": x["peer_n"]} for x in r["metrics"]]),
        hide_index=True, width="stretch")

    charts = [x for x in r["metrics"] if x["value"] is not None and x.get("peer_median") is not None]
    for i in range(0, len(charts), 2):
        cols = st.columns(2)
        for col, x in zip(cols, charts[i:i + 2]):
            with col:
                dist = np.array(x["distribution"])
                lo, hi = peer_range(dist, x["value"])
                off = int(np.sum((dist < lo) | (dist > hi)))
                off_note = f" · {off} peer{'s' if off > 1 else ''} off-scale" if off else ""
                st.markdown(f"**{x['label']}** · {x['percentile']:.0f}th percentile"
                            f"{' · flagged' if x['flagged'] else ''}{off_note}")
                st.altair_chart(peer_chart(x), width="stretch")
    st.caption("Solid line: this company. Dashed: peer median. Dotted amber: Beneish -1.78 cutoff. "
               "Company numbers are from its original 10-K; "
               "peer numbers are SEC frames (latest filed). p is one-sided in the red-flag direction; "
               f"q is Benjamini-Hochberg across all metrics. Beneish components imputed as 1.0: "
               f"{', '.join(b['imputed']) or 'none'}.")


st.title("Pecora.ai")
st.caption("AI findings you can argue with. Every red flag is prosecuted, defended, and judged, and every citation is checked against the filing.")

mode = st.sidebar.radio("Mode", ["Case files", "Live run", "Numbers check"])

if mode == "Numbers check":
    files = sorted(glob.glob(os.path.join(QUANT_DIR, "*.json")), key=os.path.getmtime, reverse=True)
    ticker = st.sidebar.text_input("Ticker", "MDXG", key="q_ticker")
    year = st.sidebar.number_input("Fiscal year", 2010, 2030, 2016, key="q_year")
    if st.sidebar.button("Compute vs peers", type="primary"):
        from pecora.quant.peers import analyze
        with st.spinner("Pulling XBRL facts and peer frames from EDGAR..."):
            try:
                st.session_state["peers"] = analyze(ticker.upper(), int(year))
            except Exception as e:
                st.error(f"{type(e).__name__}: {e}")
    if files:
        choice = st.sidebar.selectbox("Saved", files, format_func=os.path.basename)
        if st.sidebar.button("Open saved"):
            st.session_state["peers"] = load_json(choice)
    if "peers" in st.session_state:
        render_peers(st.session_state["peers"])
    else:
        st.info("Compute a filing vs its peers, or open a saved result from outputs/quant/.")
elif mode == "Case files":
    files = sorted(glob.glob(os.path.join(RESULTS_DIR, "*.json")), key=os.path.getmtime, reverse=True)
    if not files:
        st.info(f"No saved results in {RESULTS_DIR}/ yet. Run the CLI or switch to Live run.")
    else:
        choice = st.sidebar.selectbox("Result", files, format_func=os.path.basename)
        data = load_json(choice)
        render_backtest(data) if "rows" in data else render_result(data)
else:
    ticker = st.sidebar.text_input("Ticker", "SMCI")
    year = st.sidebar.number_input("Fiscal year", 1994, 2030, 2016)
    anon = st.sidebar.checkbox("Anonymize (recommended)", True)
    max_f = st.sidebar.slider("Findings to debate", 1, 8, 3)
    if st.sidebar.button("Run review", type="primary"):
        from pecora.adversarial.run import run_adversarial
        with st.spinner("Pulling filing, screening, and running the debate. This takes a few minutes."):
            try:
                r = run_adversarial(ticker=ticker, year=int(year), anonymize=anon, max_findings=max_f)
                render_result(r)
            except Exception as e:
                st.error(f"{type(e).__name__}: {e}")
