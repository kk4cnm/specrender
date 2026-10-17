/*!
 * specrender player: <spectro-player> web component
 * Spectrogram + audio player with playhead, click-to-seek, drag-to-scrub,
 * drag-to-select and loop. No dependencies. MIT License.
 *
 * Usage (files written by specrender.export_player):
 *   <script src="specrender-player.js"></script>
 *   <spectro-player meta="clip.json"></spectro-player>
 *
 * Or with the config inline:
 *   <spectro-player><script type="application/json">{...}</script></spectro-player>
 *
 * Mouse:    click = jump · drag the playhead = scrub · drag elsewhere = select
 *           drag a selection edge = resize · double-click = clear selection
 * Keyboard: Space play/pause · ←/→ 1 s (Shift 5 s) · Home start · L loop · Esc clear
 *
 * Events (bubbling, composed): "spectro-selection" {start, end} | null,
 *                              "spectro-time" {time}
 */
(() => {
  "use strict";
  if (customElements.get("spectro-player")) return;

  const ICONS = {
    play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l11-6.5z" fill="currentColor"/></svg>',
    pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" fill="currentColor"/></svg>',
    loop: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7h9.2l-2.1-2.1L15.5 3.5 20 8l-4.5 4.5-1.4-1.4L16.2 9H7a2 2 0 0 0-2 2v1H3v-1a4 4 0 0 1 4-4zm10 10H7.8l2.1 2.1-1.4 1.4L4 16l4.5-4.5 1.4 1.4L7.8 15H17a2 2 0 0 0 2-2v-1h2v1a4 4 0 0 1-4 4z" fill="currentColor"/></svg>',
    vol: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9h4l5-4v14l-5-4H4zM16 8.5a5 5 0 0 1 0 7M18.5 6a8.5 8.5 0 0 1 0 12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M4 9h4l5-4v14l-5-4H4z" fill="currentColor"/></svg>',
    mute: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9h4l5-4v14l-5-4H4z" fill="currentColor"/><path d="M16.5 9.5l5 5m0-5l-5 5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  };

  const CSS = `
:host{display:block;--bg:#121214;--panel:#1c1c20;--fg:#e4e4e7;--muted:#8b8b93;--line:#2c2c32;
  --accent:#5cc8ff;--on-accent:#06121a;--sel:rgba(92,200,255,.20);--sel-edge:#5cc8ff;--head:#ffffff;
  font:13px/1.35 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:var(--fg)}
:host([theme=light]){--bg:#ffffff;--panel:#f2f2f4;--fg:#1d1d20;--muted:#62626a;--line:#dcdce0;
  --accent:#0b6bcb;--on-accent:#ffffff;--sel:rgba(11,107,203,.16);--sel-edge:#0b6bcb;--head:#111}
*{box-sizing:border-box}
.wrap{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:10px 12px 10px 4px}
.title{margin:0 0 6px 52px;font-weight:600;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.grid{display:grid;grid-template-columns:48px 1fr;column-gap:4px}
.yaxis{position:relative;font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}
.yaxis span{position:absolute;right:4px;transform:translateY(-50%);white-space:nowrap}
.yaxis span.edge-top{transform:none}.yaxis span.edge-bottom{transform:translateY(-100%)}
.plot{position:relative;overflow:hidden;border-radius:4px;cursor:crosshair;touch-action:none;
  background:#000;outline:none;user-select:none;-webkit-user-select:none}
.plot:focus-visible{box-shadow:0 0 0 2px var(--accent)}
.plot.grab{cursor:ew-resize}
.plot img{position:absolute;inset:0;width:100%;height:100%;display:block;pointer-events:none;-webkit-user-drag:none}
.dim{position:absolute;top:0;bottom:0;background:rgba(0,0,0,.38);pointer-events:none;display:none}
.sel{position:absolute;top:0;bottom:0;background:var(--sel);border-left:1px solid var(--sel-edge);
  border-right:1px solid var(--sel-edge);pointer-events:none;display:none}
.head{position:absolute;top:0;bottom:0;left:0;width:2px;margin-left:-1px;background:var(--head);
  box-shadow:0 0 0 1px rgba(0,0,0,.45);pointer-events:none;will-change:transform}
.head::before{content:"";position:absolute;top:0;left:-5px;border:6px solid transparent;border-top:7px solid var(--head);border-bottom:0}
.hover{position:absolute;top:0;bottom:0;left:0;border-left:1px dashed rgba(255,255,255,.45);pointer-events:none;display:none}
.tip{position:absolute;top:6px;left:0;padding:2px 6px;border-radius:4px;background:rgba(0,0,0,.72);color:#fff;
  font-size:11px;white-space:nowrap;pointer-events:none;display:none;font-variant-numeric:tabular-nums}
.xaxis{grid-column:2;position:relative;height:18px;font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}
.xaxis span{position:absolute;top:3px;transform:translateX(-50%);white-space:nowrap}
.xaxis span::before{content:"";position:absolute;left:50%;top:-4px;height:3px;border-left:1px solid var(--line)}
.controls{display:flex;align-items:center;gap:8px 12px;flex-wrap:wrap;margin:6px 0 0 52px}
button{display:inline-flex;align-items:center;justify-content:center;gap:6px;height:30px;min-width:30px;padding:0 8px;
  border:1px solid var(--line);border-radius:6px;background:var(--panel);color:var(--fg);font:inherit;cursor:pointer}
button:hover{border-color:var(--muted)}
button:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
button svg{width:18px;height:18px}
button.play{width:36px;height:36px;padding:0;border-radius:50%;border:none;background:var(--accent);color:var(--on-accent)}
button.play svg{width:20px;height:20px}
button[aria-pressed=true]{border-color:var(--accent);color:var(--accent)}
.time{font-variant-numeric:tabular-nums;min-width:9.5em}
.time b{font-weight:600}
.selinfo{color:var(--muted);font-variant-numeric:tabular-nums;min-width:12em}
.selinfo button{height:22px;min-width:22px;padding:0 6px;margin-left:6px;font-size:12px}
.selinfo button[hidden]{display:none}
.spacer{flex:1}
select{height:30px;border:1px solid var(--line);border-radius:6px;background:var(--panel);color:var(--fg);font:inherit;padding:0 4px}
.vol{display:inline-flex;align-items:center;gap:4px}
.vol button{border:none;background:none;padding:0 4px}
input[type=range]{width:96px;accent-color:var(--accent)}
.err{margin:8px 0 0 52px;color:#ff7a7a}
@media (max-width:560px){.time{min-width:0}.selinfo{min-width:0;flex-basis:100%}}
`;

  // ------------------------------------------------------------------ helpers
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

  function fmtTime(t, dec = 1) {
    if (!isFinite(t)) t = 0;
    const neg = t < 0; t = Math.abs(t);
    const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60);
    let s = (t % 60).toFixed(dec);
    if (parseFloat(s) >= 60) s = (0).toFixed(dec);
    const ss = s.padStart(dec ? 3 + dec : 2, "0");
    return (neg ? "-" : "") + (h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`);
  }

  function fmtHz(f) {
    if (f >= 1000) { const k = f / 1000; return (k >= 10 ? k.toFixed(1) : k.toFixed(2)).replace(/\.?0+$/, "") + " kHz"; }
    return Math.round(f) + " Hz";
  }

  const SCALE = {
    linear: [f => f, v => v],
    log: [f => Math.log(Math.max(f, 1e-9)), v => Math.exp(v)],
    mel: [f => 2595 * Math.log10(1 + f / 700), v => 700 * (Math.pow(10, v / 2595) - 1)],
  };

  const TIME_STEPS = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200];

  const players = new Set();

  // ------------------------------------------------------------------ element
  class SpectroPlayer extends HTMLElement {
    static get observedAttributes() { return ["meta"]; }

    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._sel = null;          // [a, b] in view seconds
      this._loop = true;
      this._drag = null;
      this._raf = 0;
      this._cfg = null;
    }

    // ---- public API
    get currentTime() { return this._audio ? this._audio.currentTime - this._off : 0; }
    set currentTime(t) { this._seek(t); }
    get duration() { return this._cfg ? this._cfg.duration : 0; }
    get selection() { return this._sel ? { start: this._sel[0], end: this._sel[1] } : null; }
    set selection(v) { this._setSel(v ? [v.start, v.end] : null); }
    get loop() { return this._loop; }
    set loop(v) { this._loop = !!v; this._syncLoopBtn(); }
    play() { return this._play(); }
    pause() { this._audio && this._audio.pause(); }

    connectedCallback() {
      players.add(this);
      if (!this._built) { this._build(); this._built = true; this._load(); }
      this._ro.observe(this._plot);
    }
    disconnectedCallback() {
      players.delete(this);
      cancelAnimationFrame(this._raf);
      this._ro && this._ro.disconnect();
      this._audio && this._audio.pause();
    }
    attributeChangedCallback(name, oldV, newV) {
      if (name === "meta" && this._built && oldV !== newV) this._load();
    }

    // ---- setup
    _build() {
      const r = this.shadowRoot;
      r.innerHTML = `<style>${CSS}</style>
<div class="wrap" part="container">
  <div class="title" part="title" hidden></div>
  <div class="grid">
    <div class="yaxis" aria-hidden="true"></div>
    <div class="plot" tabindex="0" role="slider" aria-label="Playback position" aria-valuemin="0">
      <img alt="" draggable="false">
      <div class="dim l"></div><div class="dim r"></div>
      <div class="sel"></div><div class="hover"></div><div class="head"></div><div class="tip"></div>
    </div>
    <div class="xaxis" aria-hidden="true"></div>
  </div>
  <div class="controls">
    <button class="play" type="button" aria-label="Play">${ICONS.play}</button>
    <span class="time"><b class="cur">0:00.0</b> / <span class="dur">0:00.0</span></span>
    <button class="loopbtn" type="button" aria-pressed="true" title="Loop selection (L)">${ICONS.loop}<span>Loop selection</span></button>
    <span class="selinfo"><span class="seltext" aria-live="polite"></span><button class="selclear" type="button" title="Clear selection (Esc)" aria-label="Clear selection" hidden>✕</button></span>
    <span class="spacer"></span>
    <label title="Playback speed"><select class="rate" aria-label="Playback speed">
      <option value="0.5">0.5×</option><option value="0.75">0.75×</option><option value="1" selected>1×</option>
      <option value="1.25">1.25×</option><option value="1.5">1.5×</option><option value="2">2×</option></select></label>
    <span class="vol"><button class="mutebtn" type="button" aria-label="Mute">${ICONS.vol}</button>
      <input class="volume" type="range" min="0" max="1" step="0.01" value="1" aria-label="Volume"></span>
  </div>
  <div class="err" hidden></div>
  <audio preload="auto"></audio>
</div>`;
      const $ = s => r.querySelector(s);
      Object.assign(this, {
        _title: $(".title"), _yaxis: $(".yaxis"), _plot: $(".plot"), _img: $(".plot img"),
        _selEl: $(".sel"), _dimL: $(".dim.l"), _dimR: $(".dim.r"), _head: $(".head"), _hover: $(".hover"),
        _tip: $(".tip"), _xaxis: $(".xaxis"), _playBtn: $(".play"), _cur: $(".cur"), _dur: $(".dur"),
        _loopBtn: $(".loopbtn"), _selText: $(".seltext"), _selClear: $(".selclear"), _rate: $(".rate"), _muteBtn: $(".mutebtn"),
        _vol: $(".volume"), _err: $(".err"), _audio: $("audio"),
      });

      try {
        const v = parseFloat(localStorage.getItem("spectro-player:volume"));
        if (isFinite(v)) { this._vol.value = v; }
      } catch (e) { /* storage unavailable */ }

      const a = this._audio;
      a.volume = parseFloat(this._vol.value);
      a.addEventListener("play", () => { this._onPlayState(); this._tick(); });
      a.addEventListener("pause", () => this._onPlayState());
      a.addEventListener("ended", () => this._onEnded());
      a.addEventListener("timeupdate", () => { if (a.paused) this._render(); else this._enforce(); });
      a.addEventListener("loadedmetadata", () => {     // hosted audio with an offset: start at the view
        if (this._off && a.currentTime < this._off) this._seek(0);
      });
      a.addEventListener("seeked", () => this._render());
      a.addEventListener("error", () => {
        const type = this._cfg && this._cfg.audio_type;
        this._showErr("Couldn't load the audio" + (type ? ` (${type}). This browser may not support that format.` : "."));
      });

      this._playBtn.addEventListener("click", () => (a.paused ? this._play() : a.pause()));
      this._loopBtn.addEventListener("click", () => { this.loop = !this._loop; });
      this._selClear.addEventListener("click", () => { this._setSel(null); this._plot.focus({ preventScroll: true }); });
      this._rate.addEventListener("change", () => { a.playbackRate = parseFloat(this._rate.value); });
      this._vol.addEventListener("input", () => {
        a.volume = parseFloat(this._vol.value); a.muted = false; this._syncVol();
        try { localStorage.setItem("spectro-player:volume", this._vol.value); } catch (e) { /* ignore */ }
      });
      this._muteBtn.addEventListener("click", () => { a.muted = !a.muted; this._syncVol(); });

      const p = this._plot;
      p.addEventListener("pointerdown", e => this._down(e));
      p.addEventListener("pointermove", e => this._move(e));
      p.addEventListener("pointerup", e => this._up(e));
      p.addEventListener("pointercancel", () => { this._drag = null; });
      p.addEventListener("pointerleave", () => { this._hover.style.display = this._tip.style.display = "none"; });
      p.addEventListener("dblclick", () => this._setSel(null));
      p.addEventListener("keydown", e => this._key(e));

      this._ro = new ResizeObserver(() => { this._xTicks(); this._render(); });
    }

    async _load() {
      this._err.hidden = true;
      let cfg, base = document.baseURI;
      try {
        const inline = this.querySelector('script[type="application/json"]');
        if (inline) cfg = JSON.parse(inline.textContent);
        else if (this.getAttribute("meta")) {
          const url = new URL(this.getAttribute("meta"), document.baseURI);
          const res = await fetch(url);
          if (!res.ok) throw new Error(`HTTP ${res.status} loading ${url}`);
          cfg = await res.json(); base = url.href;
        } else return;
      } catch (e) { this._showErr("Couldn't load player data: " + e.message); return; }
      const abs = u => (u ? new URL(u, base).href : u);
      cfg.image = abs(this.getAttribute("image") || cfg.image);
      cfg.audio = abs(this.getAttribute("src") || cfg.audio);
      this._apply(cfg);
    }

    _apply(cfg) {
      this._cfg = cfg;
      this._off = cfg.audio_offset || 0;      // audio-file seconds at the left edge
      this._label = cfg.time_offset || 0;     // added to displayed times
      if (cfg.title) { this._title.textContent = cfg.title; this._title.hidden = false; }
      if (cfg.theme && !this.hasAttribute("theme")) this.setAttribute("theme", cfg.theme);
      const h = parseInt(this.getAttribute("height"), 10) || cfg.height || 300;
      this._plot.style.height = this._yaxis.style.height = h + "px";
      this._img.src = cfg.image;
      this._setAudio(cfg.audio);
      this._dur.textContent = fmtTime(this._label + cfg.duration);
      this._plot.setAttribute("aria-valuemax", String(cfg.duration));
      this._yTicks();
      this._xTicks();
      this._setSel(null);
      this._render();
    }

    async _setAudio(url) {
      if (this._blobUrl) { URL.revokeObjectURL(this._blobUrl); this._blobUrl = null; }
      if (url && url.startsWith("data:")) {
        // Blob URLs seek more reliably than long data: URIs in some browsers
        try { this._blobUrl = URL.createObjectURL(await (await fetch(url)).blob()); url = this._blobUrl; }
        catch (e) { /* fall back to the data: URI */ }
      }
      this._audio.src = url;
    }

    _showErr(msg) { this._err.textContent = msg; this._err.hidden = false; }

    // ---- axes
    _yTicks() {
      const c = this._cfg, y = this._yaxis;
      y.textContent = "";
      for (const band of c.channels || [{ top: 0, height: 1 }]) {
        for (const t of c.yticks || []) {
          const s = document.createElement("span");
          const frac = band.top + band.height * (1 - t.pos);   // from top of plot
          s.style.top = (frac * 100) + "%";
          if (t.pos >= 0.995) s.className = "edge-top";
          else if (t.pos <= 0.005) s.className = "edge-bottom";
          s.textContent = t.label;
          y.appendChild(s);
        }
      }
    }

    _xTicks() {
      const c = this._cfg; if (!c) return;
      const w = this._plot.clientWidth || 600, d = c.duration;
      const want = d / Math.max(2, w / 90);
      const step = TIME_STEPS.find(s => s >= want) || TIME_STEPS[TIME_STEPS.length - 1];
      const dec = step < 0.1 ? 2 : step < 1 ? 1 : 0;
      const x = this._xaxis; x.textContent = "";
      const first = Math.ceil(this._label / step - 1e-9) * step - this._label;
      for (let t = first; t <= d + 1e-9; t += step) {
        const s = document.createElement("span");
        s.style.left = (t / d * 100) + "%";
        s.textContent = fmtTime(t + this._label, dec);
        const frac = t / d;
        if (frac < 0.02) s.style.transform = "none";
        else if (frac > 0.98) s.style.transform = "translateX(-100%)";
        x.appendChild(s);
      }
    }

    // ---- coordinates
    _tAt(clientX) {
      const r = this._plot.getBoundingClientRect();
      return clamp((clientX - r.left) / r.width, 0, 1) * this.duration;
    }
    _xOf(t) { return t / this.duration * this._plot.clientWidth; }
    _hzAt(clientY) {
      const c = this._cfg, r = this._plot.getBoundingClientRect();
      const fy = (clientY - r.top) / r.height;
      for (const b of c.channels || [{ top: 0, height: 1 }]) {
        if (fy >= b.top && fy <= b.top + b.height) {
          const [to, from] = SCALE[c.scale] || SCALE.linear;
          const lo = to(c.fmin), hi = to(c.fmax);
          return from(lo + (1 - (fy - b.top) / b.height) * (hi - lo));
        }
      }
      return null;
    }

    // ---- playback
    async _play() {
      const a = this._audio, s = this._sel, t = this.currentTime;
      if (s && (t < s[0] || t >= s[1] - 0.005)) this._seek(s[0]);
      else if (!s && (t < 0 || t >= this.duration - 0.005)) this._seek(0);
      for (const p of players) if (p !== this) p.pause();
      try { await a.play(); } catch (e) { if (e.name !== "AbortError") this._showErr("Playback failed: " + e.message); }
    }
    _seek(t) {
      t = clamp(t, 0, this.duration);
      if (this._audio) this._audio.currentTime = t + this._off;
      this._render();
      this.dispatchEvent(new CustomEvent("spectro-time", { detail: { time: t + this._label }, bubbles: true, composed: true }));
    }
    _onEnded() {
      const s = this._sel;
      if (s && this._loop) { this._seek(s[0]); this._audio.play(); }
      else this._onPlayState();
    }
    _onPlayState() {
      const playing = !this._audio.paused;
      this._playBtn.innerHTML = playing ? ICONS.pause : ICONS.play;
      this._playBtn.setAttribute("aria-label", playing ? "Pause" : "Play");
      this._render();
    }
    _tick() {
      cancelAnimationFrame(this._raf);
      const step = () => {
        if (this._audio.paused) return;
        this._enforce();
        this._render();
        this._raf = requestAnimationFrame(step);
      };
      this._raf = requestAnimationFrame(step);
    }

    // Keep playback inside the selection / view. Runs every animation frame and
    // on "timeupdate" (which keeps firing in background tabs, where rAF stops).
    _enforce() {
      const a = this._audio;
      if (a.paused) return;
      const t = this.currentTime, s = this._sel;
      if (s && t >= s[1]) {
        if (this._loop) this._seek(s[0]); else { a.pause(); this._seek(s[1]); }
      } else if (t >= this.duration) {            // view window ends before the audio file does
        a.pause(); this._seek(this.duration);
      } else if (t < 0) {                         // hosted audio playing before the view starts
        this._seek(0);
      }
    }

    // ---- selection
    _setSel(sel) {
      if (sel) {
        let [a, b] = sel; if (b < a) [a, b] = [b, a];
        a = clamp(a, 0, this.duration); b = clamp(b, 0, this.duration);
        this._sel = b - a > 1e-3 ? [a, b] : null;
      } else this._sel = null;
      this._render();
      const s = this.selection;
      this.dispatchEvent(new CustomEvent("spectro-selection", {
        detail: s && { start: s.start + this._label, end: s.end + this._label }, bubbles: true, composed: true }));
    }

    // ---- pointer
    _hit(clientX, pointerType) {
      const r = this._plot.getBoundingClientRect(), x = clientX - r.left;
      const tol = pointerType === "touch" ? 16 : 7;
      // Selection edges win over the playhead: after selecting, the playhead sits on
      // the left edge, and the edge must stay resizable. Click inside to move the head.
      if (this._sel) {
        if (Math.abs(x - this._xOf(this._sel[0])) <= tol) return "a";
        if (Math.abs(x - this._xOf(this._sel[1])) <= tol) return "b";
      }
      if (Math.abs(x - this._xOf(this.currentTime)) <= tol) return "head";
      return null;
    }
    _down(e) {
      if (e.button !== 0 || !this._cfg) return;
      this._plot.focus({ preventScroll: true });
      this._plot.setPointerCapture(e.pointerId);
      const t = this._tAt(e.clientX), hit = this._hit(e.clientX, e.pointerType);
      this._drag = { mode: hit || "pending", x0: e.clientX, t0: t, fixed: hit === "a" ? this._sel[1] : hit === "b" ? this._sel[0] : null };
      if (hit === "head") this._seek(t);
      e.preventDefault();
    }
    _move(e) {
      if (!this._cfg) return;
      const t = this._tAt(e.clientX), d = this._drag;
      // hover readout
      const r = this._plot.getBoundingClientRect(), x = e.clientX - r.left;
      this._hover.style.display = this._tip.style.display = "block";
      this._hover.style.transform = `translateX(${x}px)`;
      const hz = this._hzAt(e.clientY);
      this._tip.textContent = fmtTime(t + this._label, 2) + (hz != null ? "  ·  " + fmtHz(hz) : "");
      const tw = this._tip.offsetWidth;
      this._tip.style.transform = `translateX(${clamp(x + 10, 0, r.width - tw - 2)}px)`;

      if (!d) { this._plot.classList.toggle("grab", !!this._hit(e.clientX)); return; }
      if (d.mode === "head") this._seek(t);
      else if (d.mode === "a" || d.mode === "b") this._setSel([d.fixed, t]);
      else if (d.mode === "pending" && Math.abs(e.clientX - d.x0) > 4) d.mode = "select";
      if (d.mode === "select") this._setSel([d.t0, t]);
    }
    _up(e) {
      const d = this._drag; this._drag = null;
      if (!d) return;
      try { this._plot.releasePointerCapture(e.pointerId); } catch (err) { /* already released */ }
      if (d.mode === "pending") {                 // plain click: jump there
        if (this._sel && (d.t0 < this._sel[0] || d.t0 > this._sel[1])) this._setSel(null);
        this._seek(d.t0);
      } else if (d.mode === "select" || d.mode === "a" || d.mode === "b") {
        if (this._sel) {
          const t = this.currentTime;
          if (d.mode === "select" || t < this._sel[0] || t > this._sel[1]) this._seek(this._sel[0]);
        }
      }
    }

    // ---- keyboard
    _key(e) {
      const k = e.key, big = e.shiftKey ? 5 : 1;
      if (k === " " || k === "k") { e.preventDefault(); this._audio.paused ? this._play() : this._audio.pause(); }
      else if (k === "ArrowLeft") { e.preventDefault(); this._seek(this.currentTime - big); }
      else if (k === "ArrowRight") { e.preventDefault(); this._seek(this.currentTime + big); }
      else if (k === "Home") { e.preventDefault(); this._seek(this._sel ? this._sel[0] : 0); }
      else if (k === "End") { e.preventDefault(); this._seek(this._sel ? this._sel[1] : this.duration); }
      else if (k === "l" || k === "L") { this.loop = !this._loop; }
      else if (k === "Escape") { this._setSel(null); }
    }

    // ---- drawing
    _syncLoopBtn() { this._loopBtn.setAttribute("aria-pressed", String(this._loop)); this._render(); }
    _syncVol() {
      const a = this._audio, m = a.muted || a.volume === 0;
      this._muteBtn.innerHTML = m ? ICONS.mute : ICONS.vol;
      this._muteBtn.setAttribute("aria-label", m ? "Unmute" : "Mute");
    }
    _setText(txt) { if (this._selText.textContent !== txt) this._selText.textContent = txt; }

    _render() {
      if (!this._cfg) return;
      const w = this._plot.clientWidth, t = this.currentTime;
      this._head.style.transform = `translateX(${clamp(this._xOf(t), 1, w - 1)}px)`;
      this._cur.textContent = fmtTime(t + this._label);
      this._plot.setAttribute("aria-valuenow", t.toFixed(2));
      this._plot.setAttribute("aria-valuetext", fmtTime(t + this._label));
      const s = this._sel;
      if (s) {
        const xa = this._xOf(s[0]), xb = this._xOf(s[1]);
        Object.assign(this._selEl.style, { display: "block", left: xa + "px", width: Math.max(1, xb - xa) + "px" });
        Object.assign(this._dimL.style, { display: "block", left: "0", width: xa + "px" });
        Object.assign(this._dimR.style, { display: "block", left: xb + "px", width: Math.max(0, w - xb) + "px" });
        const len = s[1] - s[0];
        this._setText(`${this._loop ? "Looping" : "Selection"} ${fmtTime(s[0] + this._label, 2)} – ` +
          `${fmtTime(s[1] + this._label, 2)} (${len < 60 ? len.toFixed(2) + " s" : fmtTime(len)})`);
        this._selClear.hidden = false;
      } else {
        this._selEl.style.display = this._dimL.style.display = this._dimR.style.display = "none";
        this._setText("Drag across the spectrogram to select a region");
        this._selClear.hidden = true;
      }
    }
  }

  customElements.define("spectro-player", SpectroPlayer);
})();
