# Topics / pub-sub: retire the "index page" type

Status: brainstorm. Not started.

## What's there now

A page becomes an "index" when its content carries an `index:` block (md
frontmatter or leading `<!--FLUBPUB ... -->` HTML comment), or when the root
`/api/index` adaptor forces it. `content_type: "index"` is a distinct value on
pages.json, parallel to `markdown` / `html_raw`. It changes write semantics
(theming gate, post-build injection of `<!--FLUBPUB-LIST-->` and
`<script id="flubpub-pages">`). Exactly one `IndexSpec` per page. The body is
mostly a host for sentinels.

## The proposal

Any page can embed any number of subscriptions to a "topic." A topic is a
name; pages declare what topics they publish to (tags become a special case),
and pages declare where in their body they want a feed of subscribers
rendered. The "index page" stops existing as a type.

## Angles worth pulling on

**Renaming vs. restructuring.** `IndexSpec.filter` is already pub/sub-ish
(`tags_any/all/none`, `parent`, `kind`, `slug_glob`). A pure rename gives you
`topic.filter.tags_any: [bach]` and stays one-spec-per-page. The restructure
adds two things: (a) plurality (one page hosts multiple lists), and
(b) declarative publish ("this page publishes to topics X, Y") on the
producer side, not just the consumer side.

**Producer-side declaration is the interesting part.** Today, "what does this
index list?" is entirely a consumer-side query. Tags already work pub/sub-
style: producers set `tags:`, consumers filter on `tags_any`. The "topic"
rename is honest about this — call them topics, give them first-class status
separate from free-form tags, and the producer/consumer symmetry becomes the
model rather than a coincidence.

**Plurality is a real shape change.** Injection today is "one entry, one
spec, two sentinels (list + script marker)." For N lists per page you need
addressable sentinels: `<!--FLUBPUB-LIST topic=bach sort=manual-->`, or a
richer block like `<flubpub-list topic="bach" sort="manual" />` parsed
server-side. The spec moves out of frontmatter and into the body, inline at
each injection site. Frontmatter could still declare which topics the page
publishes to.

**What does the root index become?** Today the root has a privileged slug
(`ROOT_INDEX_SLUG`) and an output-path special case. Under the topic model,
the root is just a page that subscribes to topic `everything`. The
`ROOT_INDEX_SLUG` special-case stays but only for URL plumbing — the type
distinction goes away. `set-index` becomes "write a page at the root slug"
and nothing else.

**Migration cost.** `content_type=="index"` is load-bearing in:
`resolve_index`, `_create_or_replace_page` (theming gate, write_ct
branching), `inject_index_pages`, `kind` filter in `_matches_filter`, the
`set_custom_index` adaptor, and several smoke tests. Most of those collapse
to nothing — no type, no theming gate, every page renders normally with
body-level injection sites. `inject_index_pages` becomes "scan every built
page for `<flubpub-list>` blocks; substitute each." That's simpler than
today.

## Open questions to settle before cutting

1. Are topics a closed enumeration per site (registered in
   `_manifest.toml`?), or open like tags? Closed gives typo-resistance and
   the namespacing pays off; open is just "rename tags, kinda."
2. Does the producer-side publish declaration replace tags or augment them?
   Instinct says replace — collapse the two concepts.
3. How much of the filter DSL survives? Sort, limit, group, shaper all still
   make sense per-block. The filter primitives mostly collapse to
   "topic = X" plus a few escape hatches (slug_glob, before/after,
   exclude_self). Lean on that simplification, don't preserve the full
   IndexFilter.

## Concrete next steps

1. Answer the three open questions above (probably in this file, in a
   follow-up pass).
2. Sketch the body-level block syntax: `<flubpub-list topic="..." ...>` vs
   `<!--FLUBPUB-LIST topic="..." ...-->` vs YAML island. Pick one.
3. Spike `inject_index_pages`'s replacement against the dwm site: walk every
   built page, find all `<flubpub-list>` blocks, render each. Confirm the
   simplification.
4. Plan the data migration: existing `content_type=="index"` entries on
   production pages.json get their `index` block translated into a
   body-level block in the source file, then `content_type` is dropped on
   the next write.
5. Delete `resolve_index`, the `index_source_format` theming gate, the
   `set_custom_index` adaptor's force-index branch, and the `kind` filter
   primitive. Keep `IndexSpec` as the per-block spec; rename and shrink.
6. Update smoke tests (`smoke_test_payload.py`, others that touch index
   resolution). Add coverage for multi-block pages.
7. Document the new model in CLAUDE.md once it lands; remove the long
   "One index model" paragraph.

## Out of scope for the first cut

- Cross-site topics (subscribing to another flubpub install's topic).
- Live/streaming feeds (still a static rebuild per write).
- UI for topic discovery on a published site.
