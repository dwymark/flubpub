# flubpub index templates

Each subdirectory is one template. The entry point is `index.html`. Local refs
(`<link>`, `<script>`, `<img>`) are uploaded as page assets at
`set-index` / `push` time.

| Template | Description |
|---|---|
| gallery | Square-tile grid with fBm shader backdrop |

A template's contract is the `<script type="application/json" id="flubpub-pages">`
marker — the flubpub server fills it with the relevant page list at every
rebuild. What the template does with that JSON is its choice.
