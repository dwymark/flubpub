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
    const article = document.createElement("article");
    article.className = "entry";
    const accent = page.tile && page.tile.accent;
    if (accent) article.dataset.accent = accent;

    const aside = document.createElement("aside");
    aside.className = "margin";

    const titleLink = document.createElement("a");
    titleLink.className = "margin-title";
    titleLink.href = page.url || `/${page.slug}/`;
    titleLink.textContent = page.title || page.slug || "untitled";
    aside.appendChild(titleLink);

    const dateText = formatDate(page.created_at);
    if (dateText) {
      const date = document.createElement("span");
      date.className = "margin-date";
      date.textContent = dateText;
      aside.appendChild(date);
    }

    const body = document.createElement("div");
    body.className = "body";

    const p = document.createElement("p");
    const excerpt = (page.excerpt || "").trim();

    if (excerpt) {
      const first = excerpt.charAt(0);
      const rest = excerpt.slice(1);
      const cap = document.createElement("span");
      cap.className = "dropcap";
      cap.textContent = first;
      p.appendChild(cap);
      p.appendChild(document.createTextNode(rest + " "));
    } else {
      const placeholder = document.createElement("span");
      placeholder.className = "placeholder";
      placeholder.textContent = "(no excerpt) ";
      p.appendChild(placeholder);
    }

    const aster = document.createElement("a");
    aster.className = "asterisk";
    aster.href = page.url || `/${page.slug}/`;
    aster.textContent = "*";
    aster.setAttribute("aria-label", "read full post");
    p.appendChild(aster);

    body.appendChild(p);

    article.appendChild(aside);
    article.appendChild(body);
    return article;
  }

  function render() {
    const root = document.querySelector(".entries");
    if (!root) return;
    const pages = readPages();

    if (pages.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "Nothing to read.";
      root.appendChild(empty);
      return;
    }

    const frag = document.createDocumentFragment();
    for (const page of pages) frag.appendChild(makeEntry(page));
    root.appendChild(frag);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", render);
  } else {
    render();
  }
})();
