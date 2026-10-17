"""End-to-end check of the HTML player in headless Chromium (Playwright).

    python tests/browser_check.py PLAYER.html [SCREENSHOT.png]

Exercises: load, click-to-seek, playhead scrub, drag-select, edge resize,
loop playback inside the selection, stop-at-end without loop, keyboard,
volume, and clearing the selection. Exits non-zero on the first failure.
Not collected by pytest (needs a browser); run it by hand or in CI.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


def main(page_path: str, shot: str | None = None) -> None:
    url = Path(page_path).resolve().as_uri()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and errors.append(m.text))
        page.goto(url)

        P = "document.querySelector('spectro-player')"
        page.wait_for_function(f"{P} && {P}.duration > 0")
        page.wait_for_function(f"{P}.shadowRoot.querySelector('audio').readyState >= 1", timeout=15000)
        page.wait_for_function(f"{P}.shadowRoot.querySelector('img').complete && "
                               f"{P}.shadowRoot.querySelector('img').naturalWidth > 0")
        dur = page.evaluate(f"{P}.duration")
        box = page.evaluate(f"(() => {{ const r = {P}.shadowRoot.querySelector('.plot').getBoundingClientRect();"
                            " return {x: r.x, y: r.y, w: r.width, h: r.height}; })()")
        X = lambda f: box["x"] + f * box["w"]          # noqa: E731
        Y = box["y"] + box["h"] / 2
        t = lambda: page.evaluate(f"{P}.currentTime")  # noqa: E731
        sel = lambda: page.evaluate(f"{P}.selection")  # noqa: E731

        def check(cond, msg):
            if not cond:
                raise SystemExit(f"FAIL: {msg}")
            print(f"ok   {msg}")

        check(not errors, f"no page errors on load {errors}")
        n_ticks = page.evaluate(f"{P}.shadowRoot.querySelectorAll('.xaxis span').length")
        n_yt = page.evaluate(f"{P}.shadowRoot.querySelectorAll('.yaxis span').length")
        check(n_ticks >= 3 and n_yt >= 2, f"axes drawn ({n_ticks} time ticks, {n_yt} freq labels)")

        # click to seek
        page.mouse.click(X(0.5), Y)
        check(abs(t() - dur * 0.5) < dur * 0.01, f"click at 50% seeks to {t():.2f}s of {dur:.2f}s")

        # scrub the playhead from 50% to 75%
        page.mouse.move(X(0.5), Y); page.mouse.down()
        for f in (0.55, 0.62, 0.7, 0.75):
            page.mouse.move(X(f), Y)
        page.mouse.up()
        check(abs(t() - dur * 0.75) < dur * 0.01 and sel() is None, f"drag playhead scrubs to {t():.2f}s, no selection")

        # drag-select 20%..40%
        page.mouse.move(X(0.2), Y); page.mouse.down()
        for f in (0.25, 0.3, 0.35, 0.4):
            page.mouse.move(X(f), Y)
        page.mouse.up()
        s = sel()
        check(s and abs(s["start"] - dur * .2) < dur * .01 and abs(s["end"] - dur * .4) < dur * .01,
              f"drag selects {s['start']:.2f}-{s['end']:.2f}s")
        check(abs(t() - s["start"]) < 0.02, "playhead moves to selection start")

        # resize the right edge 40% -> 30%
        page.mouse.move(X(0.4), Y); page.mouse.down()
        page.mouse.move(X(0.35), Y); page.mouse.move(X(0.3), Y); page.mouse.up()
        s = sel()
        check(abs(s["end"] - dur * .3) < dur * .01 and abs(s["start"] - dur * .2) < dur * .01,
              f"edge drag resizes to {s['start']:.2f}-{s['end']:.2f}s")

        # loop playback within the selection
        a, b = s["start"], s["end"]
        page.evaluate(f"{P}.play()")
        seen, wrapped, last = [], False, None
        t_end = time.time() + (b - a) * 2.6 + 1
        while time.time() < t_end:
            now = t(); seen.append(now)
            if last is not None and now < last - 0.05:
                wrapped = True
            last = now
            time.sleep(0.05)
        playing = not page.evaluate(f"{P}.shadowRoot.querySelector('audio').paused")
        inside = all(a - 0.03 <= v <= b + 0.08 for v in seen[2:])
        check(playing and wrapped and inside,
              f"loops inside selection (range seen {min(seen):.2f}-{max(seen):.2f}s, wrapped={wrapped})")

        # turn loop off with the L key: should stop at selection end
        page.evaluate(f"{P}.shadowRoot.querySelector('.plot').focus()")
        page.keyboard.press("l")
        check(page.evaluate(f"{P}.loop") is False, "L toggles loop off")
        time.sleep((b - a) + 0.6)
        paused = page.evaluate(f"{P}.shadowRoot.querySelector('audio').paused")
        check(paused and abs(t() - b) < 0.1, f"without loop, stops at selection end ({t():.2f}s)")

        # keyboard: Esc clears, arrows seek, space plays/pauses
        page.keyboard.press("Escape")
        check(sel() is None, "Esc clears selection")
        before = t(); page.keyboard.press("ArrowRight")
        check(abs(t() - min(dur, before + 1)) < 0.05, "→ seeks +1 s")
        page.keyboard.press("Shift+ArrowLeft")
        check(abs(t() - max(0, before + 1 - 5)) < 0.05, "Shift+← seeks −5 s")
        page.keyboard.press(" "); time.sleep(0.4)
        check(not page.evaluate(f"{P}.shadowRoot.querySelector('audio').paused"), "Space plays")
        page.keyboard.press(" ")
        check(page.evaluate(f"{P}.shadowRoot.querySelector('audio').paused"), "Space pauses")

        # volume slider + mute
        page.evaluate(f"""(() => {{ const v = {P}.shadowRoot.querySelector('.volume');
            v.value = '0.3'; v.dispatchEvent(new Event('input')); }})()""")
        check(abs(page.evaluate(f"{P}.shadowRoot.querySelector('audio').volume") - 0.3) < 1e-6, "volume slider sets volume")
        page.evaluate(f"{P}.shadowRoot.querySelector('.mutebtn').click()")
        check(page.evaluate(f"{P}.shadowRoot.querySelector('audio').muted"), "mute button mutes")

        # play from the end restarts at 0
        page.evaluate(f"{P}.shadowRoot.querySelector('.mutebtn').click()")
        page.evaluate(f"{P}.currentTime = {P}.duration")
        page.evaluate(f"{P}.play()"); time.sleep(0.3)
        check(t() < 1.0, f"play at end restarts from the beginning ({t():.2f}s)")
        page.evaluate(f"{P}.pause()")

        # double-click clears a selection
        page.mouse.move(X(0.6), Y); page.mouse.down(); page.mouse.move(X(0.7), Y); page.mouse.up()
        page.mouse.dblclick(X(0.65), Y)
        check(sel() is None, "double-click clears selection")

        check(not errors, f"no page errors during interaction {errors}")
        if shot:
            page.mouse.move(X(0.25), Y); page.mouse.down(); page.mouse.move(X(0.45), Y); page.mouse.up()
            page.evaluate(f"{P}.currentTime = {P}.selection.start + 0.6*({P}.selection.end-{P}.selection.start)")
            page.mouse.move(X(0.38), box["y"] + box["h"] * 0.3)
            page.screenshot(path=shot, clip={"x": 0, "y": 0, "width": 1280,
                                             "height": box["y"] + box["h"] + 120})
        browser.close()
    print("ALL PLAYER CHECKS PASSED")


if __name__ == "__main__":
    main(*sys.argv[1:3])
