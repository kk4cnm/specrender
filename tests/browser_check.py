"""End-to-end check of the HTML player in headless Chromium (Playwright).

    python tests/browser_check.py PLAYER.html [SCREENSHOT.png|-] [OFFSET_PLAYER.html] [LABELS_ONLY.html ...]

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

LABEL_OVERLAP_JS = """(el) => {
  const spans = [...el.shadowRoot.querySelectorAll('.yaxis span')].map(s => s.getBoundingClientRect());
  let worst = Infinity;
  for (let i = 0; i < spans.length; i++) for (let j = i + 1; j < spans.length; j++) {
    const a = spans[i], b = spans[j];
    const gap = Math.max(a.top, b.top) - Math.min(a.bottom, b.bottom);   // < 0 means overlap
    worst = Math.min(worst, gap);
  }
  return {n: spans.length, worst};
}"""


def main(page_path: str, shot: str | None = None, offset_page: str | None = None, *label_pages: str) -> None:
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
        ov = page.locator("spectro-player").evaluate(LABEL_OVERLAP_JS)
        check(ov["worst"] >= 0, f"frequency labels don't overlap (closest gap {ov['worst']:.1f}px)")

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

        # the playhead now sits on the left edge: dragging that edge must resize, not scrub
        check(abs(t() - s["start"]) < 0.02, "playhead sits on the left edge")
        page.mouse.move(X(0.2), Y); page.mouse.down()
        page.mouse.move(X(0.17), Y); page.mouse.move(X(0.15), Y); page.mouse.up()
        s = sel()
        check(abs(s["start"] - dur * .15) < dur * .01 and abs(s["end"] - dur * .3) < dur * .01,
              f"left edge under the playhead resizes to {s['start']:.2f}-{s['end']:.2f}s")

        # ...while the playhead's handle (top strip) at that same spot still scrubs
        page.evaluate(f"{P}.currentTime = {P}.selection.start")      # playhead exactly on the left edge
        check(abs(t() - s["start"]) < 1e-3, "playhead placed on the left edge")
        top = box["y"] + 6
        page.mouse.move(X(0.15), top); page.mouse.down()
        page.mouse.move(X(0.2), top); page.mouse.move(X(0.25), top); page.mouse.up()
        s2 = sel()
        check(abs(t() - dur * 0.25) < dur * 0.01 and abs(s2["start"] - s["start"]) < 1e-6 and abs(s2["end"] - s["end"]) < 1e-6,
              f"handle at the top scrubs the overlapping playhead to {t():.2f}s, selection unchanged")

        page.evaluate(f"{P}.currentTime = {P}.selection.start")
        page.mouse.move(X(0.15), Y); page.mouse.down(); page.mouse.move(X(0.12), Y); page.mouse.move(X(0.1), Y); page.mouse.up()
        s3 = sel()
        check(abs(s3["start"] - dur * .1) < dur * .01, f"same spot lower down still resizes ({s3['start']:.2f}s)")
        page.evaluate(f"{P}.selection = {{start: {s['start']}, end: {s['end']}}}")
        s = sel()

        # the clear button keeps keyboard focus while playback re-renders every frame
        page.evaluate(f"{P}.shadowRoot.querySelector('.selclear').focus()")
        page.evaluate(f"{P}.play()"); time.sleep(0.4)
        focused = page.evaluate(f"{P}.shadowRoot.activeElement && {P}.shadowRoot.activeElement.className")
        page.evaluate(f"{P}.pause()")
        check(focused == "selclear", f"clear button keeps focus during playback ({focused})")
        page.evaluate(f"{P}.currentTime = {P}.selection.start")

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

        # background tab: browsers stop animation frames, but the loop must still hold
        page.evaluate(f"{P}.selection = {{start: {P}.duration*0.5, end: {P}.duration*0.5 + 0.8}}; {P}.loop = true")
        page.evaluate("window.__raf = window.requestAnimationFrame; window.requestAnimationFrame = () => 0; 0")
        page.evaluate(f"{P}.play()")
        s = sel(); seen, wrapped, last = [], False, None
        t_end = time.time() + 2.6
        while time.time() < t_end:
            now = t(); seen.append(now)
            wrapped |= last is not None and now < last - 0.05
            last = now; time.sleep(0.05)
        page.evaluate(f"{P}.pause(); window.requestAnimationFrame = window.__raf; 0")
        check(wrapped and max(seen) < s["end"] + 0.4,
              f"loop holds without animation frames (max {max(seen):.2f}s vs end {s['end']:.2f}s)")

        # compact player: the handle strip must not swallow the whole height
        page.evaluate(f"{P}.setAttribute('height', '24'); {P}._plot.style.height = '24px'; 0")
        small = page.evaluate(f"(() => {{ const r = {P}.shadowRoot.querySelector('.plot').getBoundingClientRect();"
                              " return {x: r.x, y: r.y, w: r.width, h: r.height}; })()")
        page.evaluate(f"{P}.selection = {{start: {P}.duration*0.4, end: {P}.duration*0.6}}; {P}.currentTime = {P}.duration*0.4")
        sx = small["x"] + 0.4 * small["w"]; low = small["y"] + small["h"] - 3
        page.mouse.move(sx, low); page.mouse.down()
        page.mouse.move(small["x"] + 0.35 * small["w"], low); page.mouse.move(small["x"] + 0.3 * small["w"], low); page.mouse.up()
        check(abs(sel()["start"] - dur * 0.3) < dur * 0.015, f"24 px tall player: edge still resizable ({sel()['start']:.2f}s)")

        check(not errors, f"no page errors during interaction {errors}")

        if offset_page:
            q = browser.new_page()
            q.goto(Path(offset_page).resolve().as_uri())
            q.wait_for_function(f"{P} && {P}.duration > 0 && {P}.shadowRoot.querySelector('audio').readyState >= 1")
            q.wait_for_timeout(300)
            ct = q.evaluate(f"{P}.currentTime")
            check(abs(ct) < 0.05, f"hosted audio with start offset begins at the view start ({ct:.2f})")
            ov = q.locator("spectro-player").evaluate(LABEL_OVERLAP_JS)
            check(ov["worst"] >= 0, f"second page: frequency labels don't overlap ({ov['n']} labels, closest gap {ov['worst']:.1f}px)")
            q.evaluate(f"{P}.play()"); q.wait_for_timeout(500)
            ft = q.evaluate(f"{P}.shadowRoot.querySelector('audio').currentTime")
            off = q.evaluate(f"JSON.parse({P}.querySelector('script').textContent).audio_offset")
            check(ft >= off, f"plays from file time {ft:.2f}s (offset {off}s), not before the view")
            q.close()
        if shot and shot != "-":
            page.mouse.move(X(0.25), Y); page.mouse.down(); page.mouse.move(X(0.45), Y); page.mouse.up()
            page.evaluate(f"{P}.currentTime = {P}.selection.start + 0.6*({P}.selection.end-{P}.selection.start)")
            page.mouse.move(X(0.38), box["y"] + box["h"] * 0.3)
            page.screenshot(path=shot, clip={"x": 0, "y": 0, "width": 1280,
                                             "height": box["y"] + box["h"] + 120})
        for extra in label_pages:                       # label-overlap check only
            q = browser.new_page()
            q.goto(Path(extra).resolve().as_uri())
            q.wait_for_function(f"{P} && {P}.duration > 0")
            ov = q.locator("spectro-player").evaluate(LABEL_OVERLAP_JS)
            check(ov["n"] >= 2 and ov["worst"] >= 0,
                  f"{Path(extra).name}: frequency labels don't overlap ({ov['n']} labels, closest gap {ov['worst']:.1f}px)")
            q.close()
        browser.close()
    print("ALL PLAYER CHECKS PASSED")


if __name__ == "__main__":
    main(*sys.argv[1:])
