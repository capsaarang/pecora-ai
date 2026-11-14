"""Film the website's sample trial with Chrome screencast frames, adding a cursor and captions.

Needs the site running (cd web && npm run dev) and the sample case built
(python data/demo/build_sample_case.py). Run through render.sh.
"""
import asyncio, base64, json, os, time
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "build", "frames")
URL = os.environ.get("PECORA_URL", "http://127.0.0.1:3000")

OVERLAY = r"""
(() => {
  if (window.__pec) return; window.__pec = true;
  const st = document.createElement('style');
  st.textContent = `
  nextjs-portal{display:none!important}
  #cap{position:fixed;left:50%;bottom:26px;transform:translate(-50%,8px);z-index:99999;opacity:0;
       background:#1f1c16;color:#f6f2e9;font:500 21px ui-sans-serif,system-ui,sans-serif;padding:11px 24px;border-radius:6px;
       box-shadow:0 8px 28px rgba(31,28,22,.3);transition:opacity .35s, transform .35s;white-space:nowrap}
  #cap.on{opacity:1;transform:translate(-50%,0)}
  #cur{position:fixed;left:640px;top:400px;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;
       background:rgba(31,28,22,.25);border:2px solid #1f1c16;z-index:99999;pointer-events:none;
       opacity:0;transition:left .7s cubic-bezier(.4,0,.2,1), top .7s cubic-bezier(.4,0,.2,1), transform .15s, opacity .3s}
  #cur.show{opacity:1}
  #cur.click{transform:scale(.7);background:rgba(31,28,22,.5)}`;
  document.head.appendChild(st);
  const c = document.createElement('div'); c.id='cap'; document.body.appendChild(c);
  const k = document.createElement('div'); k.id='cur'; document.body.appendChild(k);
  window.__cap = (t) => { c.classList.remove('on'); setTimeout(()=>{ if(t){c.textContent=t;c.classList.add('on');} }, t?220:0); };
  window.__move = (x,y) => { k.classList.add('show'); k.style.left=x+'px'; k.style.top=y+'px'; };
  window.__hide = () => k.classList.remove('show');
  window.__tap = () => { k.classList.add('click'); setTimeout(()=>k.classList.remove('click'),180); };
})()
"""


async def main():
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        os.remove(os.path.join(OUT, f))
    frames, marks = [], {}

    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
        pg = await ctx.new_page()
        await pg.goto(URL + "/")
        await pg.wait_for_selector("text=AI findings you can argue with.")
        await pg.evaluate(OVERLAY)
        await pg.wait_for_timeout(800)

        cdp = await ctx.new_cdp_session(pg)

        def on_frame(ev):
            path = os.path.join(OUT, f"f{len(frames):05d}.jpg")
            with open(path, "wb") as fh:
                fh.write(base64.b64decode(ev["data"]))
            frames.append((path, ev["metadata"]["timestamp"]))
            asyncio.ensure_future(cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]}))

        cdp.on("Page.screencastFrame", on_frame)
        await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92,
                                                 "maxWidth": 1280, "maxHeight": 720, "everyNthFrame": 1})

        async def point(locator):
            await locator.scroll_into_view_if_needed()
            box = await locator.bounding_box()
            await pg.evaluate(f"__move({box['x'] + min(box['width'] / 2, 160)},{box['y'] + box['height'] / 2})")
            await pg.wait_for_timeout(800)

        async def click(locator):
            await point(locator)
            await pg.evaluate("__tap()")
            await locator.click()
            await pg.wait_for_timeout(250)
            await pg.evaluate("__hide()")

        async def scroll_to(selector_js, offset=120):
            await pg.evaluate(f"""(() => {{ const el = {selector_js};
                window.scrollTo({{top: window.scrollY + el.getBoundingClientRect().top - {offset}, behavior: 'smooth'}}); }})()""")
            await pg.wait_for_timeout(900)

        marks["start"] = time.time()
        await pg.evaluate("__cap('Every red flag in a 10-K goes on trial')")
        await pg.wait_for_timeout(1300)
        await click(pg.get_by_role("link", name="Try the sample trial"))

        # The case file: blind by default
        await pg.wait_for_selector("text=Adversarial signal / 100")
        await pg.evaluate(OVERLAY)
        await pg.evaluate("window.scrollTo(0, 0)")
        await pg.evaluate("__cap('The company is hidden. Only the words are judged.')")
        await pg.wait_for_timeout(2200)

        # Trial 1: Auditor vs Defender, quote shown in the filing
        await scroll_to("[...document.querySelectorAll('h4')].find(h => h.textContent.includes('Auditor'))", 90)
        await pg.evaluate("__cap('The Auditor makes the case. The Defender answers it.')")
        await pg.wait_for_timeout(1600)
        await click(pg.get_by_role("button", name="the final ten days of the quarter").first)
        await pg.evaluate("__cap('Click any quote to see it in the filing')")
        await pg.wait_for_timeout(2000)

        await scroll_to("[...document.querySelectorAll('h4')].find(h => h.textContent.includes('Adjudication'))", 200)
        await pg.evaluate("__cap('The Adjudicator rules and scores its confidence')")
        await pg.wait_for_timeout(2200)

        # Trial 2: the altered quote
        await click(pg.get_by_role("button", name="Inventory build includes goods"))
        await pg.wait_for_timeout(300)
        alt = pg.get_by_text("quote says '86.4', filing says '96.4'")
        await alt.evaluate("el => window.scrollTo({top: window.scrollY + el.getBoundingClientRect().top - 380, behavior: 'smooth'})")
        await pg.wait_for_timeout(900)
        await pg.evaluate("__cap('Every quote is checked. A changed number gets caught.')")
        box = await alt.bounding_box()
        await pg.evaluate(f"__move({box['x'] + box['width'] + 24},{box['y'] + box['height'] / 2})")
        await pg.wait_for_timeout(2600)
        await pg.evaluate("__hide()")

        # Follow-up questions
        await scroll_to("document.getElementById('ask')", 80)
        await pg.evaluate("__cap('Ask follow-up questions in plain English')")
        await pg.wait_for_timeout(500)
        await click(pg.get_by_role("button", name="Why was the revenue finding upheld?"))
        await pg.wait_for_selector("text=Because the filing itself says")
        await pg.wait_for_timeout(600)
        await scroll_to("document.getElementById('ask')", 80)
        await click(pg.get_by_role("button", name="cut-off procedures for shipments"))
        await pg.evaluate("__cap('Answers cite the filing, and those quotes are checked too')")
        await pg.wait_for_timeout(2800)
        marks["end"] = time.time()

        await cdp.send("Page.stopScreencast")
        await pg.wait_for_timeout(300)
        await b.close()

    with open(os.path.join(OUT, "index.json"), "w") as fh:
        json.dump({"frames": frames, "marks": marks}, fh)
    print(f"{len(frames)} frames over {frames[-1][1] - frames[0][1]:.1f}s")


asyncio.run(main())
