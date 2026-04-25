(function () {
  const SVG_NS = "http://www.w3.org/2000/svg";
  const MAX_EDGES = 50;
  const REPULSE_PAD = 8;
  const BG_STAR_COUNT = 30;

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function fnv(s, salt) {
    let h = (0x811c9dc5 ^ salt) >>> 0;
    for (let i = 0; i < s.length; i++) {
      h = Math.imul(h ^ s.charCodeAt(i), 0x01000193);
    }
    return (h >>> 0) / 0xffffffff;
  }

  function daysSince(iso) {
    if (!iso) return 9999;
    const t = Date.parse(iso);
    if (isNaN(t)) return 9999;
    return Math.max(0, (Date.now() - t) / 86400000);
  }

  function radiusFor(days) {
    if (days < 30) return 4;
    if (days < 365) return 2.6;
    return 1.6;
  }

  function brightnessFor(days) {
    if (days < 30) return 1.0;
    if (days < 365) return 0.78;
    return 0.55;
  }

  function loadPages() {
    const tag = document.getElementById("flubpub-pages");
    if (!tag) return [];
    try { return JSON.parse(tag.textContent || "[]"); } catch (_) { return []; }
  }

  function relax(stars) {
    for (let i = 0; i < stars.length; i++) {
      for (let j = i + 1; j < stars.length; j++) {
        const a = stars[i], b = stars[j];
        const dx = b.x - a.x, dy = b.y - a.y;
        const d = Math.sqrt(dx * dx + dy * dy) || 0.0001;
        const min = a.r + b.r + REPULSE_PAD;
        if (d < min) {
          const overlap = (min - d) / 2;
          const ux = dx / d, uy = dy / d;
          a.x -= ux * overlap; a.y -= uy * overlap;
          b.x += ux * overlap; b.y += uy * overlap;
        }
      }
    }
  }

  function renderEdges(svg, stars) {
    let drawn = 0;
    for (let i = 0; i < stars.length && drawn < MAX_EDGES; i++) {
      const a = stars[i];
      if (!a.tags || !a.tags.length) continue;
      for (let j = i + 1; j < stars.length && drawn < MAX_EDGES; j++) {
        const b = stars[j];
        if (!b.tags || !b.tags.length) continue;
        if (!a.tags.some(t => b.tags.indexOf(t) !== -1)) continue;
        const line = document.createElementNS(SVG_NS, "line");
        line.setAttribute("class", "edge");
        line.setAttribute("x1", a.x); line.setAttribute("y1", a.y);
        line.setAttribute("x2", b.x); line.setAttribute("y2", b.y);
        svg.appendChild(line);
        drawn++;
      }
    }
  }

  function renderStars(svg, stars) {
    stars.forEach(s => {
      const g = document.createElementNS(SVG_NS, "a");
      g.setAttribute("class", "star");
      g.setAttribute("href", s.url);
      g.setAttribute("aria-label", s.title);

      const c = document.createElementNS(SVG_NS, "circle");
      c.setAttribute("cx", s.x);
      c.setAttribute("cy", s.y);
      c.setAttribute("r", s.r);
      c.setAttribute("fill", `rgba(255,255,255,${s.brightness})`);
      g.appendChild(c);

      const t = document.createElementNS(SVG_NS, "text");
      t.setAttribute("x", s.x + s.r + 6);
      t.setAttribute("y", s.y + 3);
      t.textContent = s.title;
      g.appendChild(t);

      svg.appendChild(g);
    });
  }

  function renderBgStars(svg, w, h) {
    for (let i = 0; i < BG_STAR_COUNT; i++) {
      const seed = "bg-" + i;
      const x = fnv(seed, 7) * w;
      const y = fnv(seed, 11) * h;
      const c = document.createElementNS(SVG_NS, "circle");
      c.setAttribute("cx", x); c.setAttribute("cy", y);
      c.setAttribute("r", 0.7);
      c.setAttribute("fill", "rgba(255,255,255,0.25)");
      svg.appendChild(c);
    }
  }

  function build() {
    const svg = document.getElementById("constellation");
    const bg = document.getElementById("bg-stars");
    if (!svg) return;
    const pages = loadPages();

    const w = svg.clientWidth || window.innerWidth;
    const h = Math.round(window.innerHeight * 1.5);
    svg.setAttribute("height", h);
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    if (bg) {
      bg.setAttribute("height", h);
      bg.setAttribute("viewBox", `0 0 ${w} ${h}`);
      renderBgStars(bg, w, h);
    }

    const margin = 24;
    const stars = pages.map(p => {
      const days = daysSince(p.created_at);
      const r = radiusFor(days);
      return {
        title: p.title || p.slug,
        url: p.url || ("/" + p.slug + "/"),
        tags: p.tags || [],
        x: margin + fnv(p.slug || "", 1) * (w - margin * 2),
        y: margin + fnv(p.slug || "", 2) * (h - margin * 2),
        r,
        brightness: brightnessFor(days),
      };
    });

    relax(stars);
    renderEdges(svg, stars);
    renderStars(svg, stars);

    if (!reduced) {
      window.addEventListener("scroll", () => {
        const y = window.scrollY;
        svg.style.transform = `translateY(${y * -0.15}px)`;
        if (bg) bg.style.transform = `translateY(${y * -0.95}px)`;
      }, { passive: true });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", build);
  } else {
    build();
  }
})();
