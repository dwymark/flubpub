/* Gallery tile renderer.
 *
 * Consumes the <script id="flubpub-pages"> payload that flubpub's server
 * writes at every rebuild and renders one tile per published page.
 *
 * Optional per-page tile metadata lives on each page entry as:
 *
 *   tile: {
 *     accent: "rust" | "teal" | "sand" | "ink" | "moss" | "plum",
 *     svg:    "<svg viewBox=\"0 0 160 160\">…</svg>",
 *     kicker: "Essay",
 *     tags:   "recursion · geography · 8 min"
 *   }
 *
 * When fields are absent, sensible defaults derived from the page's slug and
 * theme stand in. The card-construction skill (separate build) writes the
 * real metadata into each page once a concept is approved.
 */

(function () {
  const ACCENTS = {
    rust: '#c44a2a', teal: '#3a6e6e', sand: '#b08a55',
    ink:  '#2b2b2e', moss: '#5b6b3a', plum: '#6b3a5b',
  };
  const ACCENT_KEYS = Object.keys(ACCENTS);

  function hash(str) {
    let h = 0;
    for (let i = 0; i < str.length; i++) {
      h = ((h * 31) + str.charCodeAt(i)) | 0;
    }
    return Math.abs(h);
  }

  function fmtDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d)) return '';
    return d.toLocaleDateString('en-US', {
      year: 'numeric', month: 'short', day: 'numeric',
    });
  }

  function escapeHTML(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  function resolveAccent(page) {
    const requested = page.tile && page.tile.accent;
    if (requested && ACCENTS[requested]) return requested;
    return ACCENT_KEYS[hash(page.slug || page.title || '') % ACCENT_KEYS.length];
  }

  function resolveKicker(page) {
    if (page.tile && page.tile.kicker) return page.tile.kicker;
    if (page.theme) return page.theme.charAt(0).toUpperCase() + page.theme.slice(1);
    return 'Page';
  }

  /* Default visual: an oversized italic monogram on a quiet frame. Keeps
     the pipeline uniform — SVG only, scales inside .visual — while leaving
     each card recognizably distinct until the skill replaces it. */
  function defaultSVG(page, accentKey) {
    const color = ACCENTS[accentKey];
    const source = page.title || page.slug || '?';
    const letter = source.trim().charAt(0).toUpperCase() || '?';
    return `
      <svg viewBox="0 0 160 160" preserveAspectRatio="xMidYMid meet">
        <rect x="12" y="12" width="136" height="136"
              fill="none" stroke="${color}" stroke-width="0.6" opacity="0.55"/>
        <text x="80" y="112" text-anchor="middle"
              font-family="Cormorant Garamond, Georgia, serif"
              font-size="96" font-style="italic" font-weight="500"
              fill="${color}" opacity="0.78">${escapeHTML(letter)}</text>
      </svg>
    `;
  }

  function tileHTML(page) {
    const accent = resolveAccent(page);
    const kicker = resolveKicker(page);
    const date   = fmtDate(page.created_at);
    const visual = (page.tile && page.tile.svg) || defaultSVG(page, accent);
    const tags   = (page.tile && page.tile.tags) || '';

    return `
      <a class="tile" data-accent="${escapeHTML(accent)}" href="${escapeHTML(page.url || '#')}">
        <div class="kicker">
          <span><span class="swatch"></span>${escapeHTML(kicker)}</span>
          <span>${escapeHTML(date)}</span>
        </div>
        <div class="visual">${visual}</div>
        <h2 class="title">${escapeHTML(page.title || page.slug || 'Untitled')}</h2>
        ${tags ? `<div class="tag-row">${escapeHTML(tags)}</div>` : ''}
      </a>
    `;
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

  function render() {
    const grid = document.querySelector('.grid');
    if (!grid) return;
    const pages = loadPages();
    if (pages.length === 0) {
      grid.innerHTML = '<div class="empty">No pages yet.</div>';
      return;
    }
    grid.innerHTML = pages.map(tileHTML).join('');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', render);
  } else {
    render();
  }
})();
