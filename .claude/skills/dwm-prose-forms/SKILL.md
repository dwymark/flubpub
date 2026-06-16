---
name: dwm-prose-forms
description: Use when the user wants to batch-review or batch-rewrite the AI-authorship prose on the dwm site — the on-page "Who wrote this?" disclosures and the frontmatter listing descriptions. Regenerates two browser paste-back forms from the current content/dwm SSOT, then ingests the form's exported edits back into the content files. Invoke on "disclosure batch editor", "description batch editor", "edit the dwm disclosures/descriptions", "rebuild the disclosure form".
---

# dwm prose batch-edit forms

Two browser forms for editing the AI-authorship prose across the dwm site in one
pass, each a junkyard paste-back round-trip (fill in the browser, copy, paste
back into chat, Claude applies). Both regenerate from the `content/dwm` SSOT, so
they always reflect current content.

- **Disclosures** — every on-page "Who wrote this?" / "Who made this?" banner in
  `content/dwm/`, across all five markup variants (`dwm-disc-b`, `hl-disc-b`,
  `provenance-body`/`provenance-behavior`, `disc-body`, and the depictions
  `note` div). One editable field per disclosure paragraph.
- **Descriptions** — the frontmatter `description:` of every dwm `.md` article
  that carries one, split into an editable **byline** (the `.ai-work` credit) and
  **blurb** (the listing prose). The "Description: written by Claude" note is
  preserved untouched. Out of scope: html-bundle articles keep their listing
  description in production `pages.json`, not in `content/`.

Forms are styled `/style web palm-eink` illuminated. Changed fields are flagged
by a gold border, never a tinted background — the variant forbids accent colour
under running text.

## When to invoke

- "Open / rebuild the disclosure (or description) batch editor"
- "I want to rewrite a bunch of the dwm disclosures / descriptions at once"
- Paste-back: a message containing `=== flubpub-disclosure-edits-v1 ===` or
  `=== flubpub-description-edits-v1 ===` — skip to step 3.

## Procedure

1. **Regenerate from current content.** Run from anywhere in the repo:
   ```bash
   uv run python3 .claude/skills/dwm-prose-forms/assets/build_disclosure_form.py
   uv run --with pyyaml python3 .claude/skills/dwm-prose-forms/assets/build_description_form.py
   ```
   Each writes to `scratch/<name>-edit-form.html` (gitignored throwaway) unless
   you pass an output path. Pass `[OUT_HTML]` to place it elsewhere. The SSOT is
   `content/dwm`; if production has drifted, `flubpub --site dwm sync` first.

2. **Open it.** `wslview scratch/disclosure-edit-form.html` (interop warnings are
   spurious). The user rewrites any subset and clicks **Copy edits**.

3. **Apply the paste-back.** Feed the pasted block to the apply script (stdin or
   a file); it auto-detects the format from the sentinel and routes per
   file/field:
   ```bash
   uv run --with pyyaml python3 .claude/skills/dwm-prose-forms/assets/apply_edits.py --dry-run < pasted.txt
   uv run --with pyyaml python3 .claude/skills/dwm-prose-forms/assets/apply_edits.py < pasted.txt
   ```
   Dry-run first to preview which files change.

4. **Review, then push.** `git diff content/dwm` — the re-encoding is
   conservative (HTML-escape, restore a small inline-tag whitelist
   em/strong/a/code/br/i/b, leave apostrophes and em-dashes as UTF-8), so check
   for any house-style entity choices it did not impose (`&apos;`, `&mdash;`) and
   adjust by hand if wanted. Then deploy: `flubpub --site dwm sync` (or a per-page
   `revise`). Commit the `content/dwm` changes.

## Paste-back format

One block per changed field, between sentinel lines:
```
=== flubpub-disclosure-edits-v1 ===

[<file> :: <css-class> :: <index>]
new paragraph prose...

=== end ===
```
Descriptions use `=== flubpub-description-edits-v1 ===` with field ids
`[<file> :: byline]` / `[<file> :: blurb]`. The bracket id is the routing key the
apply script parses; `<index>` is the 1-based occurrence of that class in the
file.

## Files

- `assets/formkit.py` — repo discovery, the shared palm-eink illuminated
  template, and the generic card/field renderer both forms use.
- `assets/build_disclosure_form.py` / `assets/build_description_form.py` —
  extract from `content/dwm` and emit a form.
- `assets/apply_edits.py` — parse a paste-back block and write edits into
  `content/dwm`.

Adding a sixth disclosure markup variant: add its body/heading class to
`BODY_CLASSES`/`HEAD_CLASSES` in `build_disclosure_form.py` and teach
`apply_edits.py`'s `apply_disclosures` the same locator pattern.
