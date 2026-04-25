(function () {
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function formatDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    const dd = String(d.getDate()).padStart(2, "0");
    return `${d.getFullYear()} · ${MONTHS[d.getMonth()]} ${dd}`;
  }

  function formatTags(tags) {
    if (!Array.isArray(tags) || tags.length === 0) return "";
    return tags.map(t => `· ${t}`).join(" ");
  }

  function readPages() {
    const node = document.getElementById("flubpub-pages");
    if (!node) return [];
    try {
      const data = JSON.parse(node.textContent || "[]");
      return Array.isArray(data) ? data : [];
    } catch (e) {
      return [];
    }
  }

  function makeEntry(page) {
    const li = document.createElement("li");
    li.className = "entry";
    const accent = page.tile && page.tile.accent;
    if (accent) li.dataset.accent = accent;

    const line = document.createElement("div");
    line.className = "entry-line";

    const date = document.createElement("span");
    date.className = "entry-date";
    date.textContent = formatDate(page.created_at);

    const a = document.createElement("a");
    a.className = "entry-title";
    a.href = page.url || `/${page.slug}/`;
    a.textContent = page.title || page.slug || "untitled";

    line.appendChild(date);
    line.appendChild(a);

    const tagText = formatTags(page.tags);
    if (tagText) {
      const tags = document.createElement("span");
      tags.className = "entry-tags";
      tags.textContent = tagText;
      line.appendChild(tags);
    }

    li.appendChild(line);

    if (page.excerpt) {
      const ex = document.createElement("span");
      ex.className = "entry-excerpt";
      ex.textContent = page.excerpt;
      li.appendChild(ex);
    }

    return li;
  }

  function render() {
    const list = document.querySelector(".entries");
    if (!list) return;
    const pages = readPages();

    if (pages.length === 0) {
      const li = document.createElement("li");
      li.className = "empty";
      li.textContent = "No entries.";
      list.appendChild(li);
      return;
    }

    const frag = document.createDocumentFragment();
    for (const page of pages) frag.appendChild(makeEntry(page));
    list.appendChild(frag);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", render);
  } else {
    render();
  }
})();
