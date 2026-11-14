"""
Pecora.ai: chat-style app for adversarial review of SEC 10-K filings.

    streamlit run app.py

Type a ticker and year (for example SMCI 2016) to run a live review, open a saved
case from the sidebar, or play the built-in sample trial, which needs no API key.
"""

import contextlib
import html
import io
import os
import re
import time

import streamlit as st
from dotenv import load_dotenv

from pecora.demo import (DEMO_ID, RESULTS_DIR, VIDEO_PATH, find_demo_answer, list_cases, load_case,
                         parse_run_command)

load_dotenv()

st.set_page_config(page_title="Pecora.ai", page_icon=":material/balance:", layout="centered",
                   initial_sidebar_state="auto")

MODELS = {"Claude Haiku 5.5 (testing)": "claude-haiku-5-5", "Claude Sonnet 5.5 (final runs)": "claude-sonnet-5-5"}
AGENTS = {
    "pecora": ("Pecora", ":material/balance:"),
    "auditor": ("Auditor", ":material/search:"),
    "defender": ("Defender", ":material/shield:"),
    "judge": ("Adjudicator", ":material/gavel:"),
}
VERDICT_COPY = {
    "UPHELD": ("Upheld", "Worth escalating for deeper review"),
    "DISMISSED": ("Dismissed", "Not a red flag on this evidence"),
    "INCONCLUSIVE": ("Inconclusive", "The evidence cuts both ways"),
    "ERROR": ("Not ruled", "This trial did not finish"),
}

# ---------------------------------------------------------------------------
# Style. Colors carry meaning: crimson argues the case, steel blue defends,
# brass is the bench. Fills are translucent so they work in light and dark mode.
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@font-face { font-family:'IBM Plex Sans'; font-style:normal; font-weight:400; font-display:swap; src:url('app/static/fonts/ibm-plex-sans-latin-400-normal.woff2') format('woff2'); }
@font-face { font-family:'IBM Plex Sans'; font-style:normal; font-weight:500; font-display:swap; src:url('app/static/fonts/ibm-plex-sans-latin-500-normal.woff2') format('woff2'); }
@font-face { font-family:'IBM Plex Sans'; font-style:normal; font-weight:600; font-display:swap; src:url('app/static/fonts/ibm-plex-sans-latin-600-normal.woff2') format('woff2'); }
@font-face { font-family:'IBM Plex Serif'; font-style:normal; font-weight:400; font-display:swap; src:url('app/static/fonts/ibm-plex-serif-latin-400-normal.woff2') format('woff2'); }
@font-face { font-family:'IBM Plex Serif'; font-style:normal; font-weight:500; font-display:swap; src:url('app/static/fonts/ibm-plex-serif-latin-500-normal.woff2') format('woff2'); }
@font-face { font-family:'IBM Plex Serif'; font-style:italic; font-weight:400; font-display:swap; src:url('app/static/fonts/ibm-plex-serif-latin-400-italic.woff2') format('woff2'); }
:root { --crimson:#B03A41; --steel:#3A6EA5; --brass:#A07C22; --found:#2E8550; --miss:#C0392B; }
html, body, .stApp, .stMarkdown, input, textarea { font-family:'IBM Plex Sans', system-ui, sans-serif; }
h1, h2, h3 { font-family:'IBM Plex Sans', sans-serif !important; font-weight:600 !important; letter-spacing:-0.01em; }
.block-container { padding-top:2.2rem; padding-bottom:7rem; }

.brand { font-weight:600; font-size:1.35rem; letter-spacing:-0.02em; }
.brand span { opacity:.55; font-weight:400; }
.brand-sub { font-size:.82rem; opacity:.7; margin:-.2rem 0 .6rem; }

.hero h1 { font-size:2.15rem; line-height:1.15; margin:3.2rem 0 .7rem; }
.hero p { font-size:1.05rem; line-height:1.6; opacity:.82; max-width:36rem; }
.cast { display:flex; gap:.5rem; flex-wrap:wrap; margin:1.1rem 0 1.6rem; font-size:.86rem; }
.cast div { border-radius:999px; padding:.28rem .75rem; border:1px solid; }
.cast .a { border-color:var(--crimson); color:var(--crimson); }
.cast .d { border-color:var(--steel); color:var(--steel); }
.cast .j { border-color:var(--brass); color:var(--brass); }

[class*="st-key-chips"] button, [class*="st-key-asks"] button { border-radius:999px !important; font-size:.88rem; }

[class*="st-key-auditor"] [data-testid="stChatMessage"] { border-left:3px solid var(--crimson); background:rgba(176,58,65,.05); border-radius:0 .6rem .6rem 0; }
[class*="st-key-defender"] [data-testid="stChatMessage"] { border-left:3px solid var(--steel); background:rgba(58,110,165,.06); border-radius:0 .6rem .6rem 0; }
[class*="st-key-judge"] [data-testid="stChatMessage"] { border-left:3px solid var(--brass); background:rgba(160,124,34,.06); border-radius:0 .6rem .6rem 0; }
.who { font-size:.8rem; font-weight:600; margin-bottom:.15rem; }
.who.a { color:var(--crimson); } .who.d { color:var(--steel); } .who.j { color:var(--brass); } .who.p { opacity:.7; }

.finding { margin:2rem 0 .6rem; padding:.9rem 1rem; border:1px solid rgba(128,128,128,.28); border-radius:.6rem; }
.finding .n { font-size:.8rem; opacity:.65; }
.finding .t { font-weight:600; font-size:1.05rem; margin:.15rem 0 .3rem; }
.finding .d { font-size:.92rem; opacity:.82; line-height:1.5; }
.sev { display:inline-block; font-size:.74rem; font-weight:600; padding:.05rem .5rem; border-radius:999px; margin-right:.4rem; }
.sev.HIGH { background:rgba(176,58,65,.14); color:var(--crimson); }
.sev.MEDIUM { background:rgba(160,124,34,.16); color:var(--brass); }
.sev.LOW { background:rgba(128,128,128,.16); }

.q { font-family:'IBM Plex Serif', Georgia, serif; font-size:.95rem; line-height:1.55; margin:.35rem 0 .2rem;
     padding:.45rem .75rem; border-radius:.35rem; background:rgba(128,128,128,.08); }
.q-meta { font-size:.78rem; margin:0 0 .7rem .2rem; }
.q-meta .ok { color:var(--found); font-weight:600; } .q-meta .no { color:var(--miss); font-weight:600; }
.point { margin:.6rem 0 0; }

.ruling { border:1.5px solid var(--brass); border-radius:.6rem; padding:.85rem 1rem; margin:.3rem 0 .8rem; }
.ruling .top { display:flex; justify-content:space-between; align-items:baseline; gap:1rem; }
.ruling .word { font-size:1.45rem; font-weight:600; letter-spacing:-0.01em; }
.ruling.UPHELD .word { color:var(--crimson); } .ruling.DISMISSED .word { color:var(--found); }
.ruling.INCONCLUSIVE .word { color:var(--brass); }
.ruling .conf { font-size:.9rem; font-weight:500; }
.meter { height:6px; border-radius:6px; background:rgba(128,128,128,.2); margin:.55rem 0 .45rem; overflow:hidden; }
.meter span { display:block; height:100%; background:var(--brass); }
.ruling.UPHELD .meter span { background:var(--crimson); } .ruling.DISMISSED .meter span { background:var(--found); }
.ruling .note { font-size:.86rem; opacity:.8; }
mark.hit { background:rgba(160,124,34,.28); color:inherit; padding:0 .1rem; border-radius:.15rem; }
.passage { font-family:'IBM Plex Serif', Georgia, serif; font-size:.9rem; line-height:1.55; }

.sample { font-size:.86rem; padding:.55rem .8rem; border-radius:.5rem; background:rgba(160,124,34,.12); margin-bottom:1rem; }
.casehead { font-size:1.6rem; font-weight:600; line-height:1.25; letter-spacing:-0.01em; }
.casesub { font-size:.9rem; opacity:.7; margin:.25rem 0 .6rem; }
[class*="st-key-footer"] { margin-top:3rem; padding-top:1rem; border-top:1px solid rgba(128,128,128,.22); }
.foot { font-size:.8rem; opacity:.6; padding-top:.5rem; }
@media (prefers-reduced-motion: reduce) { * { transition:none !important; animation:none !important; } }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
def init_state():
    ss = st.session_state
    ss.setdefault("case_id", None)
    ss.setdefault("chats", {})          # case_id -> follow-up messages
    ss.setdefault("home", [])           # messages on the home screen
    ss.setdefault("animate", None)      # case_id to play as a live trial once
    ss.setdefault("reveal", {})
    ss.setdefault("model_label", next(iter(MODELS)))
    ss.setdefault("max_findings", 3)
    ss.setdefault("pending", None)      # chip clicks waiting to be handled


init_state()
ss = st.session_state


def esc(s) -> str:
    return html.escape(str(s or ""))


def md(s) -> str:
    """Plain text for st.markdown: escape $ so dollar amounts are not read as math."""
    return str(s or "").replace("$", r"\$")


def slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", s)[-32:] or "x"


def highlight(passage: str, quotes: list[str]) -> str:
    out = esc(passage)
    for q in quotes:
        q = (q or "").strip()
        if len(q) < 8:
            continue
        i = out.lower().find(esc(q).lower())
        if i >= 0:
            j = i + len(esc(q))
            out = f'{out[:i]}<mark class="hit">{out[i:j]}</mark>{out[j:]}'
    return out


def quote_block(quote: str, pid: str, check: dict | None) -> str:
    if check is None:
        status = ""
    elif check.get("verified"):
        status = '<span class="ok">✓ Found in the filing</span>'
    else:
        status = '<span class="no">✗ Not found in the filing</span>'
    return (f'<div class="q">“{esc(quote)}”</div>'
            f'<div class="q-meta">Passage {esc(pid)} &nbsp; {status}</div>')


def type_out(text: str, animate: bool):
    if not animate:
        st.markdown(md(text))
        return

    def words():
        for w in md(text).split(" "):
            yield w + " "
            time.sleep(0.014)
    st.write_stream(words())


def pause(animate: bool, secs: float = 0.5):
    if animate:
        time.sleep(secs)


def evidence_popover(evidence: list[dict], quotes: dict, key: str):
    with st.popover("View filing passages", icon=":material/description:", key=key):
        for p in evidence:
            st.markdown(f"**{esc(p['id'])}** &nbsp; {esc(p.get('section', ''))}", unsafe_allow_html=True)
            st.markdown(f'<div class="passage">{highlight(p["text"], quotes.get(p["id"], []))}</div>',
                        unsafe_allow_html=True)
            st.write("")


# ---------------------------------------------------------------------------
# Case view
# ---------------------------------------------------------------------------
def agent_message(kind: str, key: str):
    name, avatar = AGENTS[kind]
    box = st.container(key=f"{kind}-{key}")
    return box.chat_message(name, avatar=avatar)


def render_debate(d: dict, i: int, n: int, ckey: str, animate: bool):
    f = d.get("finding", {})
    st.markdown(f"""<div class="finding"><div class="n">Finding {i} of {n}</div>
<div class="t">{esc(f.get('title', 'Untitled finding'))}</div>
<div class="d"><span class="sev {esc(f.get('severity', ''))}">{esc(f.get('severity', '').title())}</span>
{esc(f.get('section', ''))}. {esc(f.get('detail', ''))}</div></div>""", unsafe_allow_html=True)
    pause(animate, 0.6)

    if d.get("error"):
        with agent_message("pecora", f"{ckey}-err{i}"):
            st.error(f"This trial did not finish: {d['error']}")
        return

    checks = d.get("citations", {}).get("checks", [])
    by = {(c["agent"], c["index"]): c for c in checks}
    quotes: dict[str, list[str]] = {}

    a = d.get("auditor", {})
    with agent_message("auditor", f"{ckey}-{i}"):
        st.markdown('<div class="who a">Auditor, making the case</div>', unsafe_allow_html=True)
        type_out(a.get("argument", ""), animate)
        for k, kp in enumerate(a.get("key_points", []) or [], 1):
            quotes.setdefault(kp.get("passage_id"), []).append(kp.get("quote", ""))
            st.markdown(f'<div class="point"><b>{k}.</b> {esc(kp.get("point"))}</div>'
                        + quote_block(kp.get("quote"), kp.get("passage_id"), by.get(("auditor", k))),
                        unsafe_allow_html=True)
    pause(animate)

    df = d.get("defender", {})
    with agent_message("defender", f"{ckey}-{i}"):
        st.markdown('<div class="who d">Defender, giving the company\'s side</div>', unsafe_allow_html=True)
        type_out(df.get("argument", ""), animate)
        for k, rb in enumerate(df.get("rebuttals", []) or [], 1):
            quotes.setdefault(rb.get("passage_id"), []).append(rb.get("quote", ""))
            st.markdown(f'<div class="point"><b>On point {esc(rb.get("responds_to"))}:</b> {esc(rb.get("point"))}</div>'
                        + quote_block(rb.get("quote"), rb.get("passage_id"), by.get(("defender", k))),
                        unsafe_allow_html=True)
        for c in df.get("concessions", []) or []:
            st.markdown(f"**Concedes:** {md(c)}")
    pause(animate)

    adj = d.get("adjudication", {})
    verdict = d.get("verdict", "ERROR")
    word, note = VERDICT_COPY.get(verdict, VERDICT_COPY["ERROR"])
    conf, raw = int(d.get("final_confidence", 0)), int(d.get("raw_confidence", 0))
    penalty = (f" Confidence cut from {raw}% because the decisive quote was not found in the filing."
               if conf != raw else "")
    quotes.setdefault(adj.get("decisive_passage_id"), []).append(adj.get("decisive_quote", ""))
    with agent_message("judge", f"{ckey}-{i}"):
        st.markdown('<div class="who j">Adjudicator, ruling</div>', unsafe_allow_html=True)
        st.markdown(f"""<div class="ruling {esc(verdict)}"><div class="top"><span class="word">{word}</span>
<span class="conf">{conf}% confidence</span></div><div class="meter"><span style="width:{max(0, min(conf, 100))}%"></span></div>
<div class="note">{note}.{esc(penalty)}</div></div>""", unsafe_allow_html=True)
        type_out(adj.get("reasoning", ""), animate)
        st.markdown(quote_block(adj.get("decisive_quote"), adj.get("decisive_passage_id"),
                                by.get(("adjudicator", 1))), unsafe_allow_html=True)
        if adj.get("what_would_change_my_mind"):
            st.markdown(f"**What would change my mind:** {md(adj['what_would_change_my_mind'])}")
        for flag in d.get("flags", []):
            st.caption(f":material/warning: {flag}")
        evidence_popover(d.get("evidence", []), quotes, key=f"ev-{ckey}-{i}")
    pause(animate, 0.8)


def render_reply(msg: dict, key: str):
    if msg["role"] == "user":
        with st.chat_message("user"):
            st.markdown(md(msg["content"]))
        return
    with agent_message("pecora", key):
        st.markdown(md(msg["content"]))
        for c in msg.get("citations", []):
            st.markdown(quote_block(c["quote"], c["passage_id"], {"verified": c.get("verified")}),
                        unsafe_allow_html=True)
        if msg.get("error"):
            st.caption(f"Details: {msg['error']}")


def follow_up_suggestions(case: dict) -> list[str]:
    if case.get("demo_qa"):
        return [q["question"] for q in case["demo_qa"]]
    return ["Which quotes could not be verified?", "Summarize the strongest red flag in plain English."]


def render_case(case: dict):
    meta, s = case.get("meta", {}), case.get("summary", {})
    cid = case["id"]
    ckey = slug(cid)
    animate = ss.animate == cid
    ss.animate = None

    if meta.get("sample"):
        st.markdown('<div class="sample">Sample data. This is a fictional company and filing, built to show how '
                    'Pecora.ai works. The verification and scoring are computed by the real pipeline.</div>',
                    unsafe_allow_html=True)

    revealed = ss.reveal.get(cid, False)
    blind = meta.get("anonymized", True)
    name = meta.get("company_name") or meta.get("ticker", "Company")
    title = name if (revealed or not blind) else "[COMPANY]"
    fy = f"FY{meta['fiscal_year']}" if meta.get("fiscal_year") else ""
    st.markdown(f'<div class="casehead">{esc(title)} {esc(fy)} 10-K</div>', unsafe_allow_html=True)
    sub = "Company hidden from the AI during review." if blind else "Company name was visible to the AI."
    if meta.get("filing_date"):
        sub += f" Filed {meta['filing_date']}."
    st.markdown(f'<div class="casesub">{esc(sub)}</div>', unsafe_allow_html=True)
    if blind and name:
        ss.reveal[cid] = st.toggle("Reveal company", value=revealed, key=f"rev-{ckey}")

    v = s.get("verdicts", {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Signal score", f"{s.get('signal_score', 0)}/100",
              help="Severity-weighted share of findings upheld at trial, scaled by confidence.")
    tried = s.get("reviewed", len(case.get("debates", [])))
    c2.metric("Went to trial", f"{tried} of {meta['screened']}" if meta.get("screened") else str(tried),
              help="Flagged by the first-pass screen, and how many were tried.")
    c3.metric("Upheld", v.get("UPHELD", 0))
    ci = s.get("citation_integrity")
    c4.metric("Quotes verified", f"{ci * 100:.0f}%" if ci is not None else "n/a",
              help="Share of all quotes found word for word in the filing.")

    debates = case.get("debates", [])
    flagged = f"flagged {meta['screened']} possible problems and " if meta.get("screened") else ""
    with agent_message("pecora", f"{ckey}-intro"):
        type_out(f"I read the filing with the company's name hidden, {flagged}sent the {len(debates)} most serious "
                 "to trial. For each one, the Auditor makes the case, the Defender answers, and the Adjudicator "
                 "rules. Every quote is checked against the filing.", animate)
    pause(animate)

    for i, d in enumerate(debates, 1):
        render_debate(d, i, len(debates), ckey, animate)

    chat = ss.chats.setdefault(cid, [])
    for k, m in enumerate(chat):
        render_reply(m, f"{ckey}-r{k}")

    if not chat:
        st.write("")
        with st.container(key=f"asks-{ckey}"):
            cols = st.columns(len(follow_up_suggestions(case)))
            for col, q in zip(cols, follow_up_suggestions(case)):
                if col.button(q, key=f"ask-{ckey}-{slug(q)}", use_container_width=True):
                    ss.pending = ("ask", q)
                    st.rerun()


def render_backtest(item: dict):
    b = item["data"]
    st.markdown('<div class="casehead">Backtest</div>', unsafe_allow_html=True)
    st.markdown('<div class="casesub">Companies that later restated, compared with clean peers, '
                'under identical settings.</div>', unsafe_allow_html=True)
    st.metric("Signal gap", f"{b.get('signal_gap', 0):+}", help="Average target signal minus average control signal.")
    st.dataframe([{"Role": r["role"].title(), "Company": r["ticker"], "Year": r["fiscal_year"],
                   "Signal": r["signal_score"], "Upheld": r["upheld"], "Dismissed": r["dismissed"],
                   "Quotes verified": (f"{r['citation_integrity'] * 100:.0f}%"
                                       if r.get("citation_integrity") is not None else "n/a")}
                  for r in b.get("rows", [])], hide_index=True, use_container_width=True)
    for r in b.get("rows", []):
        if r.get("result_file") and os.path.exists(r["result_file"]):
            if st.button(f"Open {r['ticker']} {r['fiscal_year']} trial", key=f"bt-{slug(r['result_file'])}"):
                ss.case_id = r["result_file"]
                st.rerun()


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------
HOW_IT_WORKS = """Here's what happens when you give me a filing:

1. **Fetch the original 10-K** from SEC EDGAR, the version investors saw before any correction.
2. **Hide the company.** Names, ticker and executives are masked, so the AI judges the words, not the headlines.
3. **Flag candidates.** A first-pass screen reads the sections where problems usually hide: revenue, risks, lawsuits, insiders.
4. **Hold a trial.** The Auditor argues each flag, the Defender gives the company's side, and the Adjudicator rules with a confidence score.
5. **Check every quote.** Plain code matches each quote against the filing. A ruling built on a quote that isn't there loses half its confidence.
6. **Score the filing.** Only the flags that survive the trial count.

Try the demo trial to see it, or type a ticker and year, like **SMCI 2016**."""


def render_home():
    if not ss.home:
        st.markdown("""<div class="hero"><h1>Which filing should we cross-examine?</h1>
<p>Pecora.ai reads a company's annual report like a skeptical investigator. Every red flag goes on trial,
every quote is checked against the filing, and only the problems that hold up are kept.</p></div>
<div class="cast"><div class="a">Auditor makes the case</div><div class="d">Defender answers it</div>
<div class="j">Adjudicator rules</div></div>""", unsafe_allow_html=True)
        with st.container(key="chips"):
            c1, c2, c3 = st.columns(3)
            if c1.button("Play the demo trial", icon=":material/play_arrow:", use_container_width=True, type="primary"):
                ss.pending = ("demo", None)
                st.rerun()
            if c2.button("How does it work?", icon=":material/help:", use_container_width=True):
                ss.pending = ("how", None)
                st.rerun()
            if c3.button("Analyze SMCI 2016", icon=":material/bolt:", use_container_width=True,
                         help="Live run. Uses your Anthropic API key and credit."):
                ss.pending = ("run", ("SMCI", 2016))
                st.rerun()
    for k, m in enumerate(ss.home):
        render_reply(m, f"home-{k}")


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------
def friendly_error(e: Exception) -> str:
    text = str(e)
    if "credit balance" in text:
        return "Your Anthropic account has no API credit. Add credit at console.anthropic.com under Billing, then try again."
    if "x-api-key" in text or "ANTHROPIC_API_KEY" in text:
        return "The Anthropic API key is missing or invalid. Check ANTHROPIC_API_KEY in your .env file."
    if "SEC_EMAIL" in text:
        return "SEC_EMAIL is not set. Add your email to the .env file; SEC requires it."
    if "No original 10-K" in text:
        return text
    return f"{type(e).__name__}: {text}"


class StatusFeed(io.TextIOBase):
    """Turns the pipeline's printed progress into lines inside a status box."""
    STEPS = {"[1/5]": "Fetching the original filing from SEC EDGAR", "[2/5]": "Hiding the company's identity",
             "[3/5]": "Reading and indexing the filing", "[4/5]": "Screening for red flags",
             "[5/5]": "Holding the trials"}

    def __init__(self, status):
        self.status, self.buf = status, ""

    def write(self, s):
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            line = line.strip()
            for tag, label in self.STEPS.items():
                if line.startswith(tag):
                    self.status.update(label=label + "...")
                    self.status.write(label)
            if line.startswith("[Screener] Focus area"):
                self.status.caption(line.replace("[Screener] ", ""))
            elif "sent to adversarial review" in line:
                self.status.caption(line)
        return len(s)


def run_live(ticker: str, year: int):
    import pecora.screen as screen
    from pecora.adversarial.llm import ClaudeLLM
    from pecora.adversarial.run import run_adversarial

    model = MODELS[ss.model_label]
    with st.chat_message("user"):
        st.markdown(f"Analyze {ticker} FY{year}")
    with st.status(f"Cross-examining {ticker} FY{year}", expanded=True) as status:
        try:
            screen.MODEL = model
            llm = ClaudeLLM(model=model)
            with contextlib.redirect_stdout(StatusFeed(status)):
                result = run_adversarial(ticker=ticker, year=year, max_findings=ss.max_findings,
                                         llm=llm, output_dir=RESULTS_DIR)
        except Exception as e:  # show a readable reason instead of a traceback
            status.update(label="The run stopped", state="error")
            st.error(friendly_error(e))
            return
        status.update(label="Trials complete", state="complete")
    ss.case_id = result["path"]
    st.rerun()


def answer(case: dict, question: str):
    chat = ss.chats.setdefault(case["id"], [])
    chat.append({"role": "user", "content": question})
    reply = find_demo_answer(case, question) if case.get("demo_qa") else None
    if reply is None and case.get("meta", {}).get("sample"):
        reply = {"answer": "This sample case answers its suggested questions offline. For your own questions, "
                           "open a real case you've run.", "citations": [], "error": ""}
    if reply is None:
        from pecora.adversarial.llm import ClaudeLLM
        from pecora.ask import answer_question
        try:
            with st.spinner("Checking the filing..."):
                reply = answer_question(question, case, ClaudeLLM(model=MODELS[ss.model_label], max_tokens=1200),
                                        history=chat[:-1])
        except Exception as e:
            reply = {"answer": friendly_error(e), "citations": [], "error": ""}
    chat.append({"role": "assistant", "content": reply["answer"], "citations": reply.get("citations", []),
                 "error": reply.get("error", "")})


@st.dialog("Pecora.ai in 30 seconds", width="large")
def demo_video():
    if os.path.exists(VIDEO_PATH):
        st.video(VIDEO_PATH, autoplay=True, muted=True)
    else:
        st.info("The demo video isn't in this copy of the project yet.")
    c1, c2 = st.columns(2)
    if c1.button("Skip", use_container_width=True):
        st.rerun()
    if c2.button("Try the demo trial", type="primary", use_container_width=True):
        ss.case_id, ss.animate = DEMO_ID, DEMO_ID
        st.rerun()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown('<div class="brand">Pecora<span>.ai</span></div>'
                '<div class="brand-sub">AI findings you can argue with</div>', unsafe_allow_html=True)
    if st.button("New analysis", icon=":material/add:", use_container_width=True):
        ss.case_id = None
        ss.home = []
        st.rerun()

    st.caption("Demo")
    if st.button("Sample trial (fictional company)", icon=":material/science:", use_container_width=True,
                 type="primary" if ss.case_id == DEMO_ID else "secondary"):
        ss.case_id = DEMO_ID
        st.rerun()

    saved = list_cases()
    st.caption("Your cases" if saved else "Your cases will appear here")
    for item in saved:
        icon = ":material/query_stats:" if item["kind"] == "backtest" else ":material/description:"
        if st.button(item["label"], icon=icon, key=f"open-{slug(item['id'])}", use_container_width=True,
                     type="primary" if ss.case_id == item["id"] else "secondary"):
            ss.case_id = item["id"]
            st.rerun()

    st.write("")
    with st.expander("Settings", icon=":material/tune:"):
        ss.model_label = st.selectbox("Model for live runs", list(MODELS),
                                      index=list(MODELS).index(ss.model_label))
        ss.max_findings = st.slider("Findings to put on trial", 1, 8, ss.max_findings,
                                    help="Each finding costs three model calls.")
    if st.button("Watch the 30-second demo", icon=":material/play_circle:", use_container_width=True,
                 key="side-demo"):
        demo_video()


# ---------------------------------------------------------------------------
# Handle chip clicks from the previous run, then draw the page
# ---------------------------------------------------------------------------
pending, ss.pending = ss.pending, None
if pending:
    kind, arg = pending
    if kind == "demo":
        ss.case_id, ss.animate = DEMO_ID, DEMO_ID
    elif kind == "how":
        ss.home += [{"role": "user", "content": "How does it work?"},
                    {"role": "assistant", "content": HOW_IT_WORKS}]
    elif kind == "run":
        ss.case_id = None
        run_live(*arg)
    elif kind == "ask" and ss.case_id:
        case = load_case(ss.case_id)
        if case:
            answer(case, arg)

backtest_item = next((i for i in list_cases() if i["id"] == ss.case_id and i["kind"] == "backtest"), None)
if backtest_item:
    render_backtest(backtest_item)
elif ss.case_id:
    case = load_case(ss.case_id)
    if case:
        render_case(case)
    else:
        st.warning("That case file could not be opened. It may have been moved or deleted.")
        ss.case_id = None
else:
    render_home()

with st.container(key="footer"):
    c1, c2 = st.columns([1, 1.4])
    if c1.button("Watch the 30-second demo", icon=":material/play_circle:", key="foot-demo"):
        demo_video()
    c2.markdown('<div class="foot">Pecora.ai, built at Data Mad 2026, UW-Madison. '
                'Not investment or legal advice.</div>', unsafe_allow_html=True)

prompt = st.chat_input("Type a ticker and year, like SMCI 2016, or ask about this case")
if prompt:
    cmd = parse_run_command(prompt)
    if cmd:
        ss.case_id = None
        run_live(*cmd)
    elif ss.case_id and not backtest_item:
        case = load_case(ss.case_id)
        if case:
            answer(case, prompt)
            st.rerun()
    else:
        ss.home += [{"role": "user", "content": prompt},
                    {"role": "assistant", "content": "To start a review, type a ticker and a fiscal year, like "
                                                     "**SMCI 2016**. Or play the demo trial to see how it works."}]
        st.rerun()
