(function () {
  const SVG_NS = "http://www.w3.org/2000/svg";
  const ROOT_R = 180;
  const LEVEL_STEP = 140;

  function fnv(s) {
    let h = 0x811c9dc5 >>> 0;
    for (let i = 0; i < s.length; i++) {
      h = Math.imul(h ^ s.charCodeAt(i), 0x01000193);
    }
    return (h >>> 0) / 0xffffffff;
  }

  function loadPages() {
    const tag = document.getElementById("flubpub-pages");
    if (!tag) return [];
    try { return JSON.parse(tag.textContent || "[]"); } catch (_) { return []; }
  }

  function buildTree(pages, rootTitle) {
    const map = new Map();
    pages.forEach(p => { if (p.slug) map.set(p.slug, p); });

    const root = { slug: "", title: rootTitle, url: null, children: [], parent: null, depth: 0 };
    const nodes = new Map();
    nodes.set("", root);

    pages.forEach(p => {
      if (!p.slug) return;
      nodes.set(p.slug, {
        slug: p.slug,
        title: p.title || p.slug,
        url: p.url || ("/" + p.slug + "/"),
        accent: p.tile && p.tile.accent || null,
        children: [],
        parent: null,
        depth: 0,
      });
    });

    // Resolve parent link, breaking back-edges to keep the graph a tree.
    function ancestorChain(slug) {
      const chain = [];
      const seen = new Set();
      let cur = slug;
      while (cur && map.has(cur) && !seen.has(cur)) {
        chain.push(cur);
        seen.add(cur);
        const p = map.get(cur);
        cur = p && p.parent ? p.parent : null;
      }
      return chain;
    }
    nodes.forEach((node, slug) => {
      if (slug === "") return;
      const raw = map.get(slug);
      const declared = raw && raw.parent;
      let parentSlug = "";
      if (declared && nodes.has(declared)) {
        // Check for a cycle: declared parent must not have `slug` in its own ancestor chain.
        const chain = ancestorChain(declared);
        parentSlug = chain.indexOf(slug) === -1 ? declared : "";
      }
      const parent = nodes.get(parentSlug) || root;
      node.parent = parent;
      parent.children.push(node);
    });

    function setDepth(n, d) {
      n.depth = d;
      n.children.forEach(c => setDepth(c, d + 1));
    }
    setDepth(root, 0);

    function countSubtree(n) {
      n.subtreeSize = 1;
      n.children.forEach(c => { countSubtree(c); n.subtreeSize += c.subtreeSize; });
    }
    countSubtree(root);

    return { root, nodes };
  }

  function layout(root) {
    root.x = 0; root.y = 0; root.angle = 0;
    function place(node, a0, a1) {
      const total = node.children.reduce((s, c) => s + c.subtreeSize, 0) || 1;
      let cursor = a0;
      node.children.forEach(c => {
        const span = (a1 - a0) * (c.subtreeSize / total);
        const ca0 = cursor, ca1 = cursor + span;
        const angle = (ca0 + ca1) / 2;
        const r = ROOT_R + (c.depth - 1) * LEVEL_STEP;
        c.x = Math.cos(angle) * r;
        c.y = Math.sin(angle) * r;
        c.angle = angle;
        place(c, ca0, ca1);
        cursor = ca1;
      });
    }
    place(root, -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI);
  }

  function curvedPath(px, py, cx, cy, slug) {
    const dx = cx - px, dy = cy - py;
    const len = Math.hypot(dx, dy) || 1;
    const mx = (px + cx) / 2, my = (py + cy) / 2;
    const perpX = -dy / len, perpY = dx / len;
    const offset = (fnv(slug || "x") - 0.5) * 24;
    const qx = mx + perpX * offset, qy = my + perpY * offset;
    return `M ${px.toFixed(2)},${py.toFixed(2)} Q ${qx.toFixed(2)},${qy.toFixed(2)} ${cx.toFixed(2)},${cy.toFixed(2)}`;
  }

  function ancestorsOf(node) {
    const out = new Set();
    let n = node.parent;
    while (n) { out.add(n.slug); n = n.parent; }
    return out;
  }

  function descendantsOf(node) {
    const out = new Set();
    function walk(n) { n.children.forEach(c => { out.add(c.slug); walk(c); }); }
    walk(node);
    return out;
  }

  function render(svg, root) {
    const branchLayer = document.createElementNS(SVG_NS, "g");
    const nodeLayer = document.createElementNS(SVG_NS, "g");
    svg.appendChild(branchLayer);
    svg.appendChild(nodeLayer);

    const branchEls = new Map();   // child slug -> path el
    const nodeEls = new Map();     // slug -> g el
    const slugToNode = new Map();  // slug -> tree node

    function visit(n) {
      slugToNode.set(n.slug, n);
      if (n.parent) {
        const path = document.createElementNS(SVG_NS, "path");
        path.setAttribute("class", "branch");
        path.setAttribute("data-child", n.slug);
        path.setAttribute("d", curvedPath(n.parent.x, n.parent.y, n.x, n.y, n.slug));
        branchLayer.appendChild(path);
        branchEls.set(n.slug, path);
      }

      const g = document.createElementNS(SVG_NS, n.url ? "a" : "g");
      g.setAttribute("class", "node" + (n === root ? " root" : ""));
      g.setAttribute("data-slug", n.slug);
      if (n.url) g.setAttribute("href", n.url);
      if (n.title) g.setAttribute("aria-label", n.title);

      const onLeft = Math.cos(n.angle) < 0;

      if (n.accent && n !== root) {
        // Place dot between the label and the page center, adjacent to the label's leading edge.
        const dot = document.createElementNS(SVG_NS, "circle");
        dot.setAttribute("class", "accent-dot");
        dot.setAttribute("r", 3);
        const dotX = n.x + (onLeft ? -8 : 8);
        dot.setAttribute("cx", dotX.toFixed(2));
        dot.setAttribute("cy", n.y.toFixed(2));
        dot.setAttribute("fill", n.accent);
        g.appendChild(dot);
      }

      const t = document.createElementNS(SVG_NS, "text");
      t.setAttribute("y", n.y.toFixed(2));
      if (n === root) {
        t.setAttribute("x", n.x.toFixed(2));
        t.setAttribute("text-anchor", "middle");
      } else {
        t.setAttribute("text-anchor", onLeft ? "end" : "start");
        const padX = onLeft ? -14 : 14;
        t.setAttribute("x", (n.x + padX).toFixed(2));
      }
      t.textContent = n.title;
      g.appendChild(t);

      nodeLayer.appendChild(g);
      nodeEls.set(n.slug, g);

      n.children.forEach(visit);
    }
    visit(root);

    // Hover lineage highlight.
    function setHover(node) {
      svg.classList.add("has-hover");
      const ancs = ancestorsOf(node);
      const descs = descendantsOf(node);
      const lit = new Set([node.slug, ...ancs, ...descs]);
      nodeEls.forEach((el, slug) => {
        el.classList.toggle("lit", lit.has(slug));
        el.classList.toggle("hovered", slug === node.slug);
      });
      // A branch is "lit" if both endpoints are in the lineage.
      branchEls.forEach((el, childSlug) => {
        const childNode = slugToNode.get(childSlug);
        const parentLit = childNode && childNode.parent && lit.has(childNode.parent.slug);
        el.classList.toggle("lit", lit.has(childSlug) && !!parentLit);
      });
    }
    function clearHover() {
      svg.classList.remove("has-hover");
      nodeEls.forEach(el => { el.classList.remove("lit"); el.classList.remove("hovered"); });
      branchEls.forEach(el => el.classList.remove("lit"));
    }

    nodeEls.forEach((el, slug) => {
      const n = slugToNode.get(slug);
      el.addEventListener("mouseenter", () => setHover(n));
      el.addEventListener("mouseleave", clearHover);
      el.addEventListener("focus", () => setHover(n));
      el.addEventListener("blur", clearHover);
    });
  }

  function build() {
    const svg = document.getElementById("mindmap");
    if (!svg) return;
    const rootTitle = svg.getAttribute("data-site-title") || "Mindmap";
    const pages = loadPages();

    const w = svg.clientWidth || window.innerWidth;
    const h = svg.clientHeight || Math.round(window.innerHeight * 0.8);
    svg.setAttribute("viewBox", `${-w / 2} ${-h / 2} ${w} ${h}`);

    if (!pages.length) {
      const { root } = buildTree([], rootTitle);
      const g = document.createElementNS(SVG_NS, "g");
      g.setAttribute("class", "node root");
      const t = document.createElementNS(SVG_NS, "text");
      t.setAttribute("x", 0); t.setAttribute("y", 0);
      t.setAttribute("text-anchor", "middle");
      t.textContent = root.title;
      g.appendChild(t);
      svg.appendChild(g);
      const note = document.createElementNS(SVG_NS, "text");
      note.setAttribute("class", "empty-note");
      note.setAttribute("x", 0); note.setAttribute("y", 32);
      note.textContent = "(no posts yet)";
      svg.appendChild(note);
      return;
    }

    const { root } = buildTree(pages, rootTitle);
    layout(root);
    render(svg, root);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", build);
  } else {
    build();
  }
})();
