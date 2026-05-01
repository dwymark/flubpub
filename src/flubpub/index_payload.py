"""Pure functions for parsing index specs and building index page payloads.

Given a list of all pages from `pages.json` and an `IndexSpec`, produces the
filtered/sorted/grouped page list an index page should display. Also extracts
an `IndexSpec` from raw page content (HTML comment block or markdown
frontmatter) and substitutes a JSON payload into the `<script id="flubpub-pages">`
marker an index template carries.
"""

from __future__ import annotations

import fnmatch
import random
import re
from datetime import datetime
from typing import Any, Callable

import yaml
from pydantic import ValidationError

from flubpub.models import IndexSpec


INDEX_PAGES_MARKER_ID = "flubpub-pages"

_FLUBPUB_HTML_COMMENT_RE = re.compile(
    r"\A\s*<!--FLUBPUB\s*(.*?)\s*-->\s*", re.DOTALL
)
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_MARKER_RE = re.compile(
    rf'(<script[^>]*id=["\']{re.escape(INDEX_PAGES_MARKER_ID)}["\'][^>]*>)(.*?)(</script>)',
    re.DOTALL,
)


# --------------------------------------------------------------------------- #
# Spec parsing
# --------------------------------------------------------------------------- #


def _spec_from_dict(data: dict[str, Any]) -> IndexSpec | None:
    """Build an IndexSpec from a parsed dict that may contain `index:` and
    optionally `content_type: index`. Returns None if no index spec present."""
    if not isinstance(data, dict):
        return None
    index_block = data.get("index")
    if index_block is None:
        return None
    if not isinstance(index_block, dict):
        return None
    try:
        return IndexSpec(**index_block)
    except ValidationError:
        return None


def parse_index_spec_from_html(html: str) -> tuple[IndexSpec | None, str]:
    """Parse a leading `<!--FLUBPUB ... -->` YAML block. On success, return
    (spec, html_with_block_stripped). If absent, return (None, html)."""
    match = _FLUBPUB_HTML_COMMENT_RE.match(html)
    if not match:
        return None, html
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return None, html
    spec = _spec_from_dict(data)
    stripped = html[match.end():]
    return spec, stripped


def parse_index_spec_from_markdown(md: str) -> tuple[IndexSpec | None, str]:
    """Read YAML frontmatter (between `---` lines) and look for `index:`.
    On a hit, the frontmatter block is stripped from the returned content;
    on a miss, the original content comes back untouched."""
    match = _FRONTMATTER_RE.match(md)
    if not match:
        return None, md
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return None, md
    spec = _spec_from_dict(data)
    if spec is None:
        return None, md
    return spec, md[match.end():]


def parse_index_spec(content: str, suffix: str) -> tuple[IndexSpec | None, str]:
    """Sniff parser by file suffix; fall back to content shape."""
    sfx = suffix.lower().lstrip(".")
    if sfx in {"md", "markdown"}:
        return parse_index_spec_from_markdown(content)
    if sfx in {"html", "htm"}:
        return parse_index_spec_from_html(content)
    if content.lstrip().startswith("<!--FLUBPUB"):
        return parse_index_spec_from_html(content)
    if content.lstrip().startswith("---"):
        return parse_index_spec_from_markdown(content)
    return None, content


# --------------------------------------------------------------------------- #
# Payload builder helpers
# --------------------------------------------------------------------------- #


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _as_list(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _matches_filter(page: dict[str, Any], spec: IndexSpec, self_slug: str) -> bool:
    f = spec.filter
    slug = page.get("slug", "")

    if f.exclude_self and slug == self_slug:
        return False

    page_tags = page.get("tags") or []
    if f.tags_any and not (set(page_tags) & set(f.tags_any)):
        return False
    if f.tags_all and not set(f.tags_all).issubset(page_tags):
        return False
    if f.tags_none and (set(page_tags) & set(f.tags_none)):
        return False

    for field, allowed in (
        ("theme", f.theme),
        ("color_scheme", f.color_scheme),
        ("content_type", f.content_type),
    ):
        allowed_list = _as_list(allowed)
        if allowed_list and page.get(field) not in allowed_list:
            return False

    if f.slug_glob and not fnmatch.fnmatch(slug, f.slug_glob):
        return False
    if f.slug_regex and not re.search(f.slug_regex, slug):
        return False

    if f.before or f.after:
        created = _parse_dt(page.get("created_at"))
        if created is None:
            return False
        if f.before and created > f.before:
            return False
        if f.after and created < f.after:
            return False

    if f.parent is not None and page.get("parent") != f.parent:
        return False

    if f.kind is not None:
        is_index = page.get("content_type") == "index"
        if f.kind == "index" and not is_index:
            return False
        if f.kind == "page" and is_index:
            return False

    return True


def _sort_pages(pages: list[dict[str, Any]], spec: IndexSpec) -> list[dict[str, Any]]:
    s = spec.sort
    by = s.by
    descending = s.order == "desc"

    if by == "random":
        rng = random.Random(s.seed or 0)
        result = list(pages)
        rng.shuffle(result)
        return result

    if by == "manual":
        position = {slug: i for i, slug in enumerate(s.manual)}
        in_manual = [p for p in pages if p.get("slug") in position]
        in_manual.sort(key=lambda p: position[p["slug"]])
        rest = [p for p in pages if p.get("slug") not in position]
        return in_manual + rest

    if by == "title":
        key: Callable[[dict[str, Any]], Any] = lambda p: (p.get("title") or "").lower()
    elif by in {"created_at", "updated_at"}:
        def key(p: dict[str, Any]) -> datetime:
            return _parse_dt(p.get(by)) or datetime.min
    else:
        key = lambda p: p.get(by) or ""

    return sorted(pages, key=key, reverse=descending)


# --------------------------------------------------------------------------- #
# Grouping
# --------------------------------------------------------------------------- #


def _dotted_get(page: dict[str, Any], path: str) -> Any:
    cur: Any = page
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
        if cur is None:
            return None
    return cur


def _group_label(page: dict[str, Any], group_by: str) -> str:
    if group_by in {"year", "month", "quarter"}:
        dt = _parse_dt(page.get("created_at"))
        if dt is None:
            return "(undated)"
        if group_by == "year":
            return f"{dt.year}"
        if group_by == "month":
            return f"{dt.year:04d}-{dt.month:02d}"
        return f"{dt.year:04d}-Q{(dt.month - 1) // 3 + 1}"

    if group_by == "theme":
        return page.get("theme") or "(no theme)"
    if group_by == "color_scheme":
        return page.get("color_scheme") or "(no color scheme)"
    if group_by == "tags[0]":
        tags = page.get("tags") or []
        return tags[0] if tags else "(untagged)"
    if group_by == "kind":
        return "index" if page.get("content_type") == "index" else "page"

    value = _dotted_get(page, group_by)
    if value is None or value == "":
        return "(none)"
    return str(value)


def _group_pages(
    pages: list[dict[str, Any]], group_by: str
) -> list[dict[str, Any]]:
    sections: dict[str, list[dict[str, Any]]] = {}
    for page in pages:
        label = _group_label(page, group_by)
        sections.setdefault(label, []).append(page)

    descending_axes = {"year", "month", "quarter"}
    labels = sorted(sections.keys(), reverse=group_by in descending_axes)
    return [{"label": label, "pages": sections[label]} for label in labels]


# --------------------------------------------------------------------------- #
# Public builder + shaper registry
# --------------------------------------------------------------------------- #


def _shaper_flat(
    pages: list[dict[str, Any]], spec: IndexSpec
) -> list[dict[str, Any]]:
    return pages


def _shaper_grouped(
    pages: list[dict[str, Any]], spec: IndexSpec
) -> list[dict[str, Any]]:
    if not spec.group_by:
        return pages
    return _group_pages(pages, spec.group_by)


SHAPERS: dict[str, Callable[[list[dict[str, Any]], IndexSpec], list[dict[str, Any]]]] = {
    "flat": _shaper_flat,
    "grouped": _shaper_grouped,
}


def build_index_payload(
    spec: IndexSpec,
    all_pages: list[dict[str, Any]],
    self_slug: str,
) -> list[dict[str, Any]]:
    """Filter, sort, optionally group, and shape `all_pages` for an index page.

    Returns either a flat list of page dicts (each augmented with `url`), or a
    list of `{label, pages}` sections when grouping is requested."""
    filtered = [
        {**p, "url": f"/{p.get('slug', '')}/"}
        for p in all_pages
        if _matches_filter(p, spec, self_slug)
    ]

    sorted_pages = _sort_pages(filtered, spec)

    if spec.limit is not None:
        sorted_pages = sorted_pages[: spec.limit]

    shaper_name = spec.shaper or ("grouped" if spec.group_by else "flat")
    shaper = SHAPERS.get(shaper_name, _shaper_flat)
    return shaper(sorted_pages, spec)


# --------------------------------------------------------------------------- #
# Marker substitution
# --------------------------------------------------------------------------- #


def substitute_pages_marker(html: str, payload_json: str) -> str:
    """Replace the inner contents of the first `<script id="flubpub-pages">`
    tag with `payload_json`. If the marker is absent, return html unchanged."""
    if not _MARKER_RE.search(html):
        return html
    return _MARKER_RE.sub(
        lambda m: f"{m.group(1)}{payload_json}{m.group(3)}", html, count=1
    )
