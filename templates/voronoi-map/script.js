/* Voronoi Map renderer.
 *
 * Reads the <script id="flubpub-pages"> payload, places each post at a
 * deterministic (x, y) derived from a slug hash, and draws Voronoi cells
 * via d3-delaunay (loaded as a UMD global as `d3`).
 */

(function () {
  const ACCENTS = {
    rust: '#c44a2a', teal: '#3a6e6e', sand: '#b08a55',
    ink:  '#2b2b2e', moss: '#5b6b3a', plum: '#6b3a5b',
  };
  const ACCENT_KEYS = Object.keys(ACCENTS);
  const DEFAULT_ACCENT = '#888';
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const XLINK_NS = 'http://www.w3.org/1999/xlink';
  const LLOYD_STEPS = 8;

  function fnv(s, salt) {
    let h = (0x811c9dc5 ^ salt) >>> 0;
    for (let i = 0; i < s.length; i++) {
      h = Math.imul(h ^ s.charCodeAt(i), 0x01000193);
    }
    return ((h >>> 0) / 0xffffffff);
  }

  function djb(str) {
    let h = 5381;
    for (let i = 0; i < str.length; i++) h = ((h << 5) + h + str.charCodeAt(i)) | 0;
    return Math.abs(h);
  }

  function resolveAccent(page) {
    const key = page.tile && page.tile.accent;
    if (key && ACCENTS[key]) return ACCENTS[key];
    const slug = page.slug || page.title || '';
    if (!slug) return DEFAULT_ACCENT;
    return ACCENTS[ACCENT_KEYS[djb(slug) % ACCENT_KEYS.length]];
  }

  function loadPages() {
    const el = document.getElementById('flubpub-pages');
    if (!el) return [];
    const raw = (el.textContent || '').trim();
    if (!raw) return [];
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      console.error('Could not parse flubpub pages payload:', err);
      return [];
    }
  }

  function viewportSize() {
    const map = document.querySelector('.map');
    const r = map ? map.getBoundingClientRect() : null;
    const w = r && r.width  ? Math.max(320, r.width)  : Math.max(320, window.innerWidth - 80);
    const h = r && r.height ? Math.max(240, r.height) : Math.max(240, window.innerHeight - 200);
    return { width: w, height: h };
  }

  /* Average vertex of polygon (good-enough centroid for label placement
     and Lloyd relaxation). */
  function polygonCentroid(poly) {
    let sx = 0, sy = 0, n = poly.length;
    for (let i = 0; i < n; i++) { sx += poly[i][0]; sy += poly[i][1]; }
    return [sx / n, sy / n];
  }

  function buildVoronoi(sites, width, height) {
    const d3 = window.d3;
    if (!d3 || !d3.Delaunay) return null;
    const delaunay = d3.Delaunay.from(sites);
    return delaunay.voronoi([0, 0, width, height]);
  }

  function lloydStep(sites, width, height) {
    const v = buildVoronoi(sites, width, height);
    if (!v) return sites;
    return sites.map((s, i) => {
      const poly = v.cellPolygon(i);
      if (!poly) return s;
      const [cx, cy] = polygonCentroid(poly);
      return [s[0] + (cx - s[0]) * 0.5, s[1] + (cy - s[1]) * 0.5];
    });
  }

  function clearChildren(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function renderEmpty(svg) {
    clearChildren(svg);
    const map = document.querySelector('.map');
    if (!map) return;
    let empty = map.querySelector('.empty');
    if (!empty) {
      empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = 'No pages yet.';
      map.appendChild(empty);
    }
    svg.style.display = 'none';
  }

  function renderCells(svg, pages, sites, width, height) {
    const v = buildVoronoi(sites, width, height);
    if (!v) {
      console.error('voronoi-map: d3-delaunay unavailable');
      return;
    }

    clearChildren(svg);
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    svg.classList.remove('has-hover');

    pages.forEach((page, i) => {
      const poly = v.cellPolygon(i);
      if (!poly) return;
      const accent = resolveAccent(page);
      const [cx, cy] = polygonCentroid(poly);
      const points = poly.map(p => `${p[0].toFixed(2)},${p[1].toFixed(2)}`).join(' ');
      const title = page.title || page.slug || 'Untitled';

      const a = document.createElementNS(SVG_NS, 'a');
      a.setAttribute('class', 'cell-link');
      a.setAttribute('href', page.url || '#');
      a.setAttributeNS(XLINK_NS, 'xlink:href', page.url || '#');
      a.style.setProperty('--cell-accent', accent);

      const polygon = document.createElementNS(SVG_NS, 'polygon');
      polygon.setAttribute('class', 'cell');
      polygon.setAttribute('points', points);

      const text = document.createElementNS(SVG_NS, 'text');
      text.setAttribute('class', 'label');
      text.setAttribute('x', cx.toFixed(2));
      text.setAttribute('y', cy.toFixed(2));
      text.textContent = title;

      const titleEl = document.createElementNS(SVG_NS, 'title');
      titleEl.textContent = title;
      a.appendChild(titleEl);

      a.appendChild(polygon);
      a.appendChild(text);

      a.addEventListener('mouseenter', () => svg.classList.add('has-hover'));
      a.addEventListener('mouseleave', () => svg.classList.remove('has-hover'));

      svg.appendChild(a);
    });
  }

  function animateLloyd(svg, pages, initialSites, width, height) {
    let sites = initialSites.slice();
    let step = 0;
    function tick() {
      sites = lloydStep(sites, width, height);
      renderCells(svg, pages, sites, width, height);
      step++;
      if (step < LLOYD_STEPS) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  let lastRender = { pages: [], sites: [] };

  function render() {
    const svg = document.getElementById('voronoi');
    if (!svg) return;
    const pages = loadPages();
    if (pages.length === 0) { renderEmpty(svg); return; }

    /* Existing empty-state node from a prior render, if any. */
    const map = document.querySelector('.map');
    if (map) {
      const empty = map.querySelector('.empty');
      if (empty) empty.remove();
    }
    svg.style.display = '';

    const { width, height } = viewportSize();

    /* Hash-positioned sites, with a small inset so cells aren't pinned to
       the absolute boundary. */
    const inset = 12;
    const sites = pages.map(p => {
      const slug = p.slug || p.title || '';
      const x = inset + fnv(slug, 1) * (width  - 2 * inset);
      const y = inset + fnv(slug, 2) * (height - 2 * inset);
      return [x, y];
    });

    const reduced = window.matchMedia &&
                    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (reduced || pages.length < 2) {
      renderCells(svg, pages, sites, width, height);
      lastRender = { pages, sites };
    } else {
      /* Show initial frame immediately so users aren't staring at blank
         space while the relaxation animates. */
      renderCells(svg, pages, sites, width, height);
      animateLloyd(svg, pages, sites, width, height);
      lastRender = { pages, sites };
    }
  }

  function rerenderForResize() {
    const svg = document.getElementById('voronoi');
    if (!svg) return;
    const pages = lastRender.pages;
    if (!pages || pages.length === 0) return;
    const { width, height } = viewportSize();
    /* Re-derive sites at the new dimensions; resize doesn't replay Lloyd. */
    const inset = 12;
    const sites = pages.map(p => {
      const slug = p.slug || p.title || '';
      const x = inset + fnv(slug, 1) * (width  - 2 * inset);
      const y = inset + fnv(slug, 2) * (height - 2 * inset);
      return [x, y];
    });
    renderCells(svg, pages, sites, width, height);
    lastRender.sites = sites;
  }

  let resizeTimer = null;
  window.addEventListener('resize', () => {
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = setTimeout(rerenderForResize, 120);
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', render);
  } else {
    render();
  }
})();
