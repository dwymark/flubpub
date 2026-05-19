# TODO (do on laptop, with the dwm ssh key available)

This sentinel file makes the SessionStart hook nag every chat until it's gone.
Delete it (`rm deploy/TODO-dwm-api-lockdown.md`) once the steps below are done.

## Why

This branch closed an unauthenticated public mutation surface: nginx no longer
proxies `/api/` (anyone could create/replace/delete pages or upload assets),
and asset writes are now path-sanitized. The fix ships in the nginx template
and the wheel — **production danielwymark.com still runs the old, exposed
config until it is redeployed.**

No backwards-compat shim was added on purpose. dwm is retrofitted by a normal
redeploy, by you, not by Claude (the ssh key lives on your laptop).

## Steps

```bash
# 1. Ship the locked-down nginx + new wheel to dwm:
uv run flubpub deploy --site dwm

# 2. Repopulate the front page via the unified root-index path. For ~1 min
#    between step 1 and step 2 the site shows 11ty's plain default index;
#    the site stays up. Run them back-to-back.
uv run flubpub --site dwm set-index content/dwm/home.md

# 3. (Optional) confirm the front page renders as expected, then:
rm deploy/TODO-dwm-api-lockdown.md
```

bj has no custom index and the same nginx change applies — redeploy it too if
it's live: `uv run flubpub deploy --site bj`.

## One-time, also on laptop

The sites registry moved from TOML to JSON. Convert your existing config once:

```bash
python3 migrate-sites-config.py           # writes ~/.config/flubpub/sites.json
# verify, then: rm ~/.config/flubpub/sites.toml migrate-sites-config.py
```

Optionally anchor the SSOT so `publish from anywhere` is literally true:

```bash
uv run flubpub sites set-content-root /path/to/flubpub-repo
```
