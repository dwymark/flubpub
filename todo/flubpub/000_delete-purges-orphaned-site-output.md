# delete must purge the page's built _site output

`delete` removes the page source (`site/src/pages/<slug>.{md,html}`) and the `pages.json` entry, then rebuilds via `npx @11ty/eleventy`. But 11ty does not clean its output directory, so `_site/<slug>/index.html` survives and nginx keeps serving the deleted page as HTTP 200 until something happens to overwrite it. A re-push of the same slug masks the bug; a genuine delete leaves the page live.

**Trap.** This looks fixed because most delete-then-repush flows overwrite the orphan. It is not — a bare delete leaves a ghost page. Observed directly: deleting `fisher-frobenius-coincidence` from bj left the stale (and separately broken) page serving 200 until the orphan dir was removed by hand over SSH.

**Do.** In the server delete path (`server.py`, the DELETE handler), remove `_site/<slug>/` as part of the delete, not just the source and the `pages.json` entry. Check the root-index case too (the root's output is `_site/index.html`, not `_site/<slug>/`; see `inject_index_pages`). Consider whether `unset-index` and any other path that orphans output needs the same treatment.

**Falsifier.** After `flubpub --site KEY delete <slug>`, `curl https://host/<slug>/` returns 404 with no manual cleanup step.

Points at: `server.py` delete handler, `rebuild_site`, `inject_index_pages`.
