"""Film the running app with Chrome screencast frames, adding a cursor and captions."""
import asyncio, base64, json, os, time
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "build", "frames")
URL = "http://127.0.0.1:8501"

OVERLAY = r"""
(() => {
  if (window.__pec) return; window.__pec = true;
  const st = document.createElement('style');
  st.textContent = `
  #cap{position:fixed;left:50%;top:18px;transform:translate(-50%,-8px);z-index:99999;opacity:0;
       background:#1d2a44;color:#fff;font:500 19px 'IBM Plex Sans',sans-serif;padding:10px 22px;border-radius:999px;
       box-shadow:0 6px 24px rgba(20,30,50,.25);transition:opacity .35s, transform .35s;white-space:nowrap}
  #cap.on{opacity:1;transform:translate(-50%,0)}
  #cur{position:fixed;left:640px;top:400px;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;
       background:rgba(36,64,110,.35);border:2px solid #24406E;z-index:99999;pointer-events:none;
       opacity:0;transition:left .7s cubic-bezier(.4,0,.2,1), top .7s cubic-bezier(.4,0,.2,1), transform .15s, opacity .3s}
  #cur.show{opacity:1}
  #cur.click{transform:scale(.7);background:rgba(36,64,110,.6)}`;
  document.head.appendChild(st);
  const c = document.createElement('div'); c.id='cap'; document.body.appendChild(c);
  const k = document.createElement('div'); k.id='cur'; document.body.appendChild(k);
  window.__cap = (t) => { c.classList.remove('on'); setTimeout(()=>{ if(t){c.textContent=t;c.classList.add('on');} }, t?220:0); };
  window.__move = (x,y) => { k.classList.add('show'); k.style.left=x+'px'; k.style.top=y+'px'; };
  window.__hide = () => k.classList.remove('show');
  window.__tap = () => { k.classList.add('click'); setTimeout(()=>k.classList.remove('click'),180); };
  window.__scroller = () => [...document.querySelectorAll('*')].find(e=>{const s=getComputedStyle(e);
      return (s.overflowY=='auto'||s.overflowY=='scroll') && e.scrollHeight>e.clientHeight+50}) || document.scrollingElement;
  window.__follow = false;
  setInterval(()=>{ if(!window.__follow) return; const s=window.__scroller();
      const target = s.scrollHeight - s.clientHeight; const cur = s.scrollTop;
      if (target - cur > 4) s.scrollTop = cur + Math.max(2, (target-cur)*0.08); }, 33);
})()
"""


async def main():
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        os.remove(os.path.join(OUT, f))
    frames = []

    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
        pg = await ctx.new_page()
        await pg.goto(URL)
        await pg.wait_for_selector("text=Which filing should we cross-examine?")
        await pg.wait_for_timeout(1500)
        await pg.evaluate(OVERLAY)

        cdp = await ctx.new_cdp_session(pg)

        def on_frame(ev):
            idx = len(frames)
            path = os.path.join(OUT, f"f{idx:05d}.jpg")
            with open(path, "wb") as fh:
                fh.write(base64.b64decode(ev["data"]))
            frames.append((path, ev["metadata"]["timestamp"]))
            asyncio.ensure_future(cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]}))

        cdp.on("Page.screencastFrame", on_frame)
        await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92,
                                                 "maxWidth": 1280, "maxHeight": 720, "everyNthFrame": 1})
        marks = {}

        async def mark(name):
            marks[name] = time.time()

        async def click(locator, caption=None):
            box = await locator.bounding_box()
            x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            await pg.evaluate(f"__move({x},{y})")
            await pg.wait_for_timeout(850)
            await pg.evaluate("__tap()")
            await locator.click()
            await pg.wait_for_timeout(250)
            await pg.evaluate("__hide()")

        # Scene: home
        await mark("home")
        await pg.evaluate("__cap('Pick a filing, or play the demo trial')")
        await pg.wait_for_timeout(1400)
        await click(pg.get_by_role("button", name="Play the demo trial"))

        # Scene: the trial streams in
        await pg.wait_for_selector("text=Finding 1 of 3", timeout=20000)
        await pg.evaluate("__cap('The company is hidden. Only the words are judged.')")
        await pg.wait_for_timeout(1700)
        await pg.evaluate("__follow = true")
        await pg.wait_for_selector("text=Auditor, making the case")
        await pg.evaluate("__cap('The Auditor makes the case, quoting the filing')")
        await pg.wait_for_selector("text=Defender, giving the company")
        await pg.evaluate("__cap('The Defender answers with the same evidence')")
        await pg.wait_for_selector("text=Adjudicator, ruling")
        await pg.evaluate("__cap('The Adjudicator rules and scores its confidence')")
        await pg.wait_for_timeout(2600)

        # Let the remaining trials finish, following along
        await pg.evaluate("__cap('Each red flag gets its own trial')")
        await pg.wait_for_selector("text=Why was the revenue finding upheld?", timeout=30000)
        await pg.wait_for_timeout(700)
        await pg.evaluate("__follow = false; __cap('')")

        # Scene: a quote that is not in the filing
        await pg.evaluate("""(() => { const el=[...document.querySelectorAll('.q-meta .no')][0];
             const s=__scroller(); const r=el.getBoundingClientRect();
             s.scrollTo({top: s.scrollTop + r.top - 360, behavior:'smooth'}); })()""")
        await pg.wait_for_timeout(1100)
        await pg.evaluate("__cap('Every quote is checked. Altered ones get caught.')")
        await pg.evaluate("""(() => { const el=[...document.querySelectorAll('.q-meta .no')][0].getBoundingClientRect();
             __move(el.right+22, el.top+8); })()""")
        await pg.wait_for_timeout(3000)
        await pg.evaluate("__hide(); __cap('')")
        btn = pg.get_by_role("button", name="Why was the revenue finding upheld?")
        await pg.evaluate("""(() => { const s=__scroller(); s.scrollTo({top:s.scrollHeight, behavior:'smooth'}); })()""")
        await pg.wait_for_timeout(1000)
        await pg.evaluate("__cap('Ask follow-up questions in plain English')")
        await pg.wait_for_timeout(700)
        await click(btn)
        await pg.wait_for_selector("text=Because the filing itself says", timeout=20000)
        await pg.wait_for_timeout(400)
        await pg.evaluate("""(() => { const s=__scroller(); s.scrollTo({top:s.scrollHeight, behavior:'smooth'}); })()""")
        await pg.evaluate("__cap('Answers cite the filing, and the quotes are verified too')")
        await pg.wait_for_timeout(3200)
        await mark("end")

        await cdp.send("Page.stopScreencast")
        await pg.wait_for_timeout(300)
        await b.close()

    with open(os.path.join(OUT, "index.json"), "w") as fh:
        json.dump({"frames": frames, "marks": marks}, fh)
    print(f"{len(frames)} frames over {frames[-1][1] - frames[0][1]:.1f}s")


asyncio.run(main())
