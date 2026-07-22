# expand the bijectivity.net front page beyond the placeholder

`content/bj/home.html` currently carries only a "Bijectivity" masthead, a hairline rule, and the server-rendered post list (tufte-math register: white `#fdfdfb` background matching the atlas, single rust accent, Georgia serif, self-contained). Prose was deliberately held to the minimum at Daniel's request — details to be filled in later, with him.

The old gallery masthead had a tagline worth reusing or reworking: "a personal math blog · varied in topic, format, and depth."

**Do (with Daniel).** Add whatever framing the site wants — tagline, a short about line, section grouping if the catalogue grows. Keep the tufte register: no second accent, no chrome above the title, no external fonts or assets. The index spec is currently a flat `kind: page` list, newest first, with dates; revisit sort/grouping (e.g. `group_by` or curated `sections`) only if the post count makes a flat list unwieldy.

Edit path: change `content/bj/home.html`, then `flubpub --site bj set-index content/bj/home.html`. The leading `<!--FLUBPUB ...-->` comment holds the index spec; the `<!--FLUBPUB-LIST-->` sentinel marks where the list renders.
