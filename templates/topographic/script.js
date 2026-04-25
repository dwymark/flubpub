(function () {
  const SVG_NS = "http://www.w3.org/2000/svg";
  const CELLS_X = 200;
  const CELLS_Y = 120;
  const FBM_SCALE = 7.0;
  const ISO_VALUES = [0.2, 0.275, 0.35, 0.425, 0.5, 0.575, 0.65, 0.8];
  const DRIFT_PX_PER_SEC = 5;
  const DRIFT_WRAP = 80;

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function fnv(s, salt) {
    let h = (0x811c9dc5 ^ salt) >>> 0;
    for (let i = 0; i < s.length; i++) {
      h = Math.imul(h ^ s.charCodeAt(i), 0x01000193);
    }
    return (h >>> 0) / 0xffffffff;
  }

  function rand(x, y) {
    const h = Math.sin(x * 12.9898 + y * 78.233) * 43758.5453123;
    return h - Math.floor(h);
  }

  function smoothNoise(x, y) {
    const ix = Math.floor(x), iy = Math.floor(y);
    const fx = x - ix, fy = y - iy;
    const a = rand(ix, iy);
    const b = rand(ix + 1, iy);
    const c = rand(ix, iy + 1);
    const d = rand(ix + 1, iy + 1);
    const ux = fx * fx * (3 - 2 * fx);
    const uy = fy * fy * (3 - 2 * fy);
    return a * (1 - ux) * (1 - uy)
         + b * ux * (1 - uy)
         + c * (1 - ux) * uy
         + d * ux * uy;
  }

  function fbm(x, y) {
    let v = 0, amp = 0.5, fx = x * 1.4, fy = y * 1.4;
    for (let i = 0; i < 5; i++) {
      v += amp * smoothNoise(fx, fy);
      fx *= 2; fy *= 2; amp *= 0.5;
    }
    return v;
  }

  function loadPages() {
    const tag = document.getElementById("flubpub-pages");
    if (!tag) return [];
    try { return JSON.parse(tag.textContent || "[]"); } catch (_) { return []; }
  }

  // Marching squares. Build a CELLS_X * CELLS_Y grid of fBm values, then for
  // each cell consult the 4-corner classification vs threshold and emit
  // segments. Edges are interpolated; segments are concatenated as one big
  // SVG path string per isovalue.
  function buildField() {
    const f = new Float32Array((CELLS_X + 1) * (CELLS_Y + 1));
    for (let j = 0; j <= CELLS_Y; j++) {
      const fy = (j / CELLS_Y) * FBM_SCALE;
      for (let i = 0; i <= CELLS_X; i++) {
        const fx = (i / CELLS_X) * FBM_SCALE;
        f[j * (CELLS_X + 1) + i] = fbm(fx, fy);
      }
    }
    return f;
  }

  // Linear interpolation along a cell edge between corner values v1, v2 to
  // find the fractional position where the threshold is crossed.
  function interp(v1, v2, t) {
    const d = v2 - v1;
    if (Math.abs(d) < 1e-9) return 0.5;
    return (t - v1) / d;
  }

  function contoursForLevel(field, t, w, h) {
    const cw = w / CELLS_X;
    const ch = h / CELLS_Y;
    const stride = CELLS_X + 1;
    let d = "";
    for (let j = 0; j < CELLS_Y; j++) {
      for (let i = 0; i < CELLS_X; i++) {
        const tl = field[j * stride + i];
        const tr = field[j * stride + i + 1];
        const br = field[(j + 1) * stride + i + 1];
        const bl = field[(j + 1) * stride + i];
        let code = 0;
        if (tl > t) code |= 8;
        if (tr > t) code |= 4;
        if (br > t) code |= 2;
        if (bl > t) code |= 1;
        if (code === 0 || code === 15) continue;

        const x0 = i * cw, y0 = j * ch;
        // Edge midpoints, interpolated:
        // top:    (x0 + cw*interp(tl,tr,t),  y0)
        // right:  (x0 + cw,                  y0 + ch*interp(tr,br,t))
        // bottom: (x0 + cw*interp(bl,br,t),  y0 + ch)
        // left:   (x0,                       y0 + ch*interp(tl,bl,t))
        const top    = [x0 + cw * interp(tl, tr, t), y0];
        const right  = [x0 + cw,                     y0 + ch * interp(tr, br, t)];
        const bottom = [x0 + cw * interp(bl, br, t), y0 + ch];
        const left   = [x0,                          y0 + ch * interp(tl, bl, t)];

        let segs = null;
        switch (code) {
          case 1:  case 14: segs = [[left, bottom]]; break;
          case 2:  case 13: segs = [[bottom, right]]; break;
          case 3:  case 12: segs = [[left, right]]; break;
          case 4:  case 11: segs = [[top, right]]; break;
          case 6:  case 9:  segs = [[top, bottom]]; break;
          case 7:  case 8:  segs = [[left, top]]; break;
          // Saddle cases — emit both diagonals; no need to disambiguate
          // since visual reading is the same.
          case 5:  segs = [[left, top], [bottom, right]]; break;
          case 10: segs = [[left, bottom], [top, right]]; break;
        }
        if (!segs) continue;
        for (const [p, q] of segs) {
          d += `M${p[0].toFixed(1)},${p[1].toFixed(1)}L${q[0].toFixed(1)},${q[1].toFixed(1)} `;
        }
      }
    }
    return d;
  }

  function renderContours(svg, w, h) {
    const field = buildField();
    for (const t of ISO_VALUES) {
      const d = contoursForLevel(field, t, w, h);
      if (!d) continue;
      const path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("d", d);
      svg.appendChild(path);
    }
  }

  function renderMarkers(svg, pages, w, h) {
    pages.forEach(p => {
      const slug = p.slug || "";
      const x = fnv(slug, 1) * w;
      const y = fnv(slug, 2) * (h - 100) + 50;

      // Sample fBm at the marker's normalized location.
      const fx = (x / w) * FBM_SCALE;
      const fy = (y / h) * FBM_SCALE;
      const elev = Math.floor(fbm(fx, fy) * 100);

      const a = document.createElementNS(SVG_NS, "a");
      a.setAttribute("class", "marker");
      a.setAttribute("href", p.url || ("/" + slug + "/"));
      a.setAttribute("aria-label", p.title || slug);

      const glyph = document.createElementNS(SVG_NS, "text");
      glyph.setAttribute("class", "glyph");
      glyph.setAttribute("x", x);
      glyph.setAttribute("y", y);
      glyph.setAttribute("text-anchor", "middle");
      glyph.setAttribute("dominant-baseline", "central");
      glyph.textContent = "▲";
      a.appendChild(glyph);

      const label = document.createElementNS(SVG_NS, "text");
      label.setAttribute("class", "label");
      label.setAttribute("x", x + 2);
      label.setAttribute("y", y - 4);
      label.textContent = p.title || slug;
      a.appendChild(label);

      const elevText = document.createElementNS(SVG_NS, "text");
      elevText.setAttribute("class", "elev");
      // Sit beside the title; the label is left-anchored, so place this
      // a measured offset to its right.
      const labelOffset = (p.title || slug).length * 5.5 + 8;
      elevText.setAttribute("x", x + 2 + labelOffset);
      elevText.setAttribute("y", y - 4);
      elevText.textContent = "↑" + elev;
      a.appendChild(elevText);

      svg.appendChild(a);
    });
  }

  function startDrift(svg) {
    if (reduced) return;
    let vx = 0, vy = 0;
    let last = performance.now();
    function tick(now) {
      let dt = (now - last) / 1000;
      last = now;
      if (dt > 0.05) dt = 0.05;
      // Diagonal drift: ~5 px/sec total speed.
      const inv = 1 / Math.SQRT2;
      vx = (vx + DRIFT_PX_PER_SEC * inv * dt) % DRIFT_WRAP;
      vy = (vy + DRIFT_PX_PER_SEC * inv * dt) % DRIFT_WRAP;
      svg.style.transform = `translate(${vx.toFixed(2)}px, ${vy.toFixed(2)}px)`;
      requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  function build() {
    const contours = document.getElementById("contours");
    const markers = document.getElementById("markers");
    if (!contours || !markers) return;

    const pages = loadPages();
    const w = contours.clientWidth || window.innerWidth;
    const h = Math.round(window.innerHeight * 1.5);

    // Make the contour layer slightly larger so the drift translation
    // never reveals an unfilled edge.
    const cw = w + DRIFT_WRAP * 2;
    const ch = h + DRIFT_WRAP * 2;
    contours.setAttribute("width", cw);
    contours.setAttribute("height", ch);
    contours.setAttribute("viewBox", `0 0 ${cw} ${ch}`);
    contours.style.left = `-${DRIFT_WRAP}px`;
    contours.style.top = `-${DRIFT_WRAP}px`;
    contours.style.width = `${cw}px`;

    markers.setAttribute("width", w);
    markers.setAttribute("height", h);
    markers.setAttribute("viewBox", `0 0 ${w} ${h}`);

    renderContours(contours, cw, ch);
    renderMarkers(markers, pages, w, h);
    startDrift(contours);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", build);
  } else {
    build();
  }
})();
