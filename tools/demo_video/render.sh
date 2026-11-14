#!/usr/bin/env bash
# Re-record the 30-second demo video from the running website.
# Needs: the site running (cd web && npm run dev), the sample case built
# (python data/demo/build_sample_case.py), Playwright with Chromium, and ffmpeg.
#   pip install playwright && playwright install chromium
#   bash tools/demo_video/render.sh
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build
python record.py
python - <<'PY'
import asyncio, json
from playwright.async_api import async_playwright
d = json.load(open("build/frames/index.json")); fr = d["frames"]; end = d["marks"]["end"]
with open("build/list.txt", "w") as f:
    for (p, t), (_, t2) in zip(fr, fr[1:]):
        f.write(f"file '{p}'\nduration {max(t2 - t, 0.001):.4f}\n")
    f.write(f"file '{fr[-1][0]}'\nduration {max(end - fr[-1][1], 0.5):.4f}\nfile '{fr[-1][0]}'\n")
async def cards():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={"width": 1280, "height": 720})
        import os
        for k in ["title", "end"]:
            await pg.goto(f"file://{os.path.abspath('card.html')}?k={k}"); await pg.wait_for_timeout(700)
            await pg.screenshot(path=f"build/{k}.jpg", type="jpeg", quality=92)
        await b.close()
asyncio.run(cards())
PY
ENC="-c:v libx264 -crf 20 -preset medium -pix_fmt yuv420p -r 30"
ffmpeg -v error -y -f concat -safe 0 -i build/list.txt -vf "setpts=PTS/1.2,fps=30,scale=1280:720,format=yuv420p,fade=t=in:st=0:d=0.4:color=0xf6f2e9" $ENC build/main.mp4
ffmpeg -v error -y -framerate 30 -i build/title.jpg -vf "format=yuv420p,loop=-1:1,trim=duration=2.6,fade=t=in:st=0:d=0.3:color=0xf6f2e9,fade=t=out:st=2.2:d=0.4:color=0xf6f2e9" $ENC build/title.mp4
ffmpeg -v error -y -framerate 30 -i build/end.jpg -vf "format=yuv420p,loop=-1:1,trim=duration=3.2,fade=t=in:st=0:d=0.4:color=0xf6f2e9" $ENC build/end.mp4
printf "file 'title.mp4'\nfile 'main.mp4'\nfile 'end.mp4'\n" > build/parts.txt
ffmpeg -v error -y -f concat -safe 0 -i build/parts.txt -c copy -movflags +faststart build/pecora-demo.tmp.mp4
mv build/pecora-demo.tmp.mp4 ../../web/public/pecora-demo.mp4
echo "Saved web/public/pecora-demo.mp4"
