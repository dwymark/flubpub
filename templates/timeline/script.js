/* flubpub timeline — render posts pinned at proportional time positions. */

(function () {
  const ACCENTS = {
    rust: '#b86b4a', teal: '#3d8a8a', sand: '#c9a96e',
    ink:  '#5a6b8c', moss: '#6b8a5a', plum: '#8a5a7a',
  };

  const root = document.querySelector('.timeline');
  if (!root) return;

  const entriesEl = root.querySelector('.entries');
  const yearsEl   = root.querySelector('.years');
  const bandsEl   = root.querySelector('.bands');

  let posts = [];
  try {
    const raw = document.getElementById('flubpub-pages').textContent.trim();
    posts = JSON.parse(raw || '[]');
  } catch (e) { posts = []; }

  posts = posts.filter(p => p && p.title && p.url && p.created_at);

  if (posts.length === 0) {
    root.classList.add('is-empty');
    return;
  }

  posts.forEach(p => { p._date = new Date(p.created_at); });
  posts.sort((a, b) => b._date - a._date);

  const tMin = posts[posts.length - 1]._date.getTime();
  const tMax = posts[0]._date.getTime();
  const span = Math.max(tMax - tMin, 1);

  const TOP_PAD = 80;
  const BOT_PAD = 120;
  const height = Math.max(window.innerHeight * 1.5, posts.length * 80, 1200);
  const usable = height - TOP_PAD - BOT_PAD;
  const pixelsPerMs = usable / span;

  const tForDate = d => TOP_PAD + (tMax - d.getTime()) * pixelsPerMs;

  root.style.height = height + 'px';

  const fmtDate = d => {
    const m = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return `${d.getFullYear()} ${m[d.getMonth()]} ${String(d.getDate()).padStart(2,'0')}`;
  };

  posts.forEach((p, i) => {
    const top = tForDate(p._date);
    const side = (i % 2 === 0) ? 'right' : 'left';
    const accent = ACCENTS[(p.tile && p.tile.accent) || ''] || '#888';

    const el = document.createElement('div');
    el.className = `entry ${side}`;
    el.style.top = top + 'px';
    el.style.setProperty('--accent', accent);
    el.innerHTML = `
      <div class="stem"><span class="bullet"></span></div>
      <div class="body">
        <div class="date">${fmtDate(p._date)}</div>
        <a class="title" href="${p.url}">${escapeHtml(p.title)}</a>
      </div>`;
    entriesEl.appendChild(el);
  });

  const yMin = new Date(tMin).getFullYear();
  const yMax = new Date(tMax).getFullYear();

  for (let y = yMin; y <= yMax; y++) {
    const jan1 = new Date(y, 0, 1);
    const t = jan1.getTime();
    if (t < tMin || t > tMax) continue;
    const top = tForDate(jan1);
    const m = document.createElement('div');
    m.className = 'year-marker';
    m.style.top = top + 'px';
    m.textContent = y;
    yearsEl.appendChild(m);
  }

  const bandStarts = [];
  for (let y = yMin; y <= yMax + 1; y++) {
    bandStarts.push(new Date(y, 0, 1).getTime());
  }
  for (let i = 0; i < bandStarts.length - 1; i++) {
    const a = Math.max(bandStarts[i], tMin);
    const b = Math.min(bandStarts[i + 1], tMax);
    if (b <= a) continue;
    const top = tForDate(new Date(b));
    const bot = tForDate(new Date(a));
    const band = document.createElement('div');
    band.className = 'band';
    band.style.top = top + 'px';
    band.style.height = (bot - top) + 'px';
    band.style.background = (i % 2 === 0)
      ? 'rgba(232, 226, 211, 0.04)'
      : 'rgba(232, 226, 211, 0.02)';
    bandsEl.appendChild(band);
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[c]));
  }
})();
