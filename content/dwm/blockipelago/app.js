/* ============================================================
   Blockipelago — Spiral + Lloyd, glyph-substrate edition.

   The geometry is unchanged from the original CPU/SVG version:
   each block's seed is laid down by a coarse spiral and then
   relaxed under six rounds of Lloyd. What changes is the fill.

   For each Voronoi cell we paint the *actual codepoints from
   that block* into an offscreen 4096² Canvas2D — colored by
   cluster, fonted by cluster — then upload it as a single GPU
   texture. The fragment shader samples that texture through an
   inverse Gaussian fisheye: given a screen point q and a cursor
   u, it solves for the source point p such that the forward
   warp q = u + (p − u)·(1 + A·exp(−|p−u|²/2σ²)) holds. Five
   fixed-point iterations converge to numerical accuracy.

   No SVG. No per-cell triangulation. One quad, one shader, one
   uniform per frame.
   ============================================================ */

(function () {
  "use strict";

  // ---------- Constants ----------
  const DATA = window.DATA;

  // Geometric algorithm parameters — unchanged.
  const A_MAX = 5.5;                  // peak fisheye magnification at full intensity — factor 6.5×, so a c≈12 source-px glyph reaches ~17 CSS-px under the lens
  const SIGMA = 0.24;                 // fisheye stddev (unit coords)
  const TWOSIGSQ = 2 * SIGMA * SIGMA;
  const WHEEL_GAIN = 1 / 1000;        // intensity delta per pixel of wheel deltaY; ~10 notches for full 0→1 travel
  let   lensIntensity = 0.30;         // [0, 1]; multiplies A_MAX. Boots at a gentle 30%; mouse-wheel scrolls up toward 100% or down toward 0.

  // Atlas parameters.
  const ATLAS_SIZE = 4096;            // square texture, also the pixel diameter of the disk inside it
  const DISK_RADIUS_PX = ATLAS_SIZE / 2;
  const ATLAS_CENTER = ATLAS_SIZE / 2;

  // Vogel sunflower-spiral parameters. Glyph centers sit on
  //   r_k = SPIRAL_C * sqrt(k + 0.5),  θ_k = k * GOLDEN_ANGLE
  // (k from SPIRAL_K0). The spiral has constant point density 1/(π·c²),
  // local nearest-neighbor distance ≈ c, no overlap if glyph size ≤ c.
  // K_total ≈ (DISK_RADIUS_PX / SPIRAL_C)² positions.
  const SPIRAL_C = 12.0;              // spiral parameter ≈ target nearest-neighbor distance, in atlas px
  const SIZE_RATIO = 1.6;              // For a Vogel spiral with point density 1/(π·c²), 100% coverage by square slots
                                       // requires slot side ≈ √π · c ≈ 1.77c. We're well over 1.0 because the user
                                       // explicitly preferred overlap to gaps; 1.6 means each glyph fills a slot bigger
                                       // than the nearest-neighbor distance, ensuring near-zero whitespace.
  const SPIRAL_K0 = 8;                // skip first few indices to avoid the small-k center cluster
  const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));   // ≈ 137.5077°

  // Per-cluster font fallback chain (used for atlas drawing AND inspector).
  // The browser walks the chain per-codepoint: first font with a glyph wins.
  // Last Resort HE sits at the end of every chain — its 381 designed
  // placeholders mean the *very worst* outcome for an unknown codepoint is a
  // stylized block-name square, never a generic tofu rectangle.
  // Master list of every font family we ship. Order matters within each
  // cluster's chain — earlier wins when both have a glyph for the codepoint.
  const NOTO_LIVING = [
    '"Noto Sans"',
    '"Noto Sans Hebrew"', '"Noto Sans Arabic"', '"Noto Sans Syriac"',
    '"Noto Sans Thaana"', '"Noto Sans NKo"',
    '"Noto Sans Mongolian"',
    '"Noto Sans Devanagari"', '"Noto Sans Bengali"', '"Noto Sans Gujarati"',
    '"Noto Sans Gurmukhi"', '"Noto Sans Tamil"', '"Noto Sans Telugu"',
    '"Noto Sans Kannada"', '"Noto Sans Malayalam"', '"Noto Sans Sinhala"',
    '"Noto Sans Thai"', '"Noto Sans Lao"', '"Noto Sans Khmer"',
    '"Noto Sans Tibetan"', '"Noto Sans Myanmar"',
    '"Noto Sans Georgian"', '"Noto Sans Armenian"',
    '"Noto Sans Ethiopic"', '"Noto Sans Cherokee"',
    '"Noto Sans Canadian Aboriginal"',
    '"Noto Sans Adlam"', '"Noto Sans Tagalog"',
    '"Noto Sans Oriya"', '"Noto Sans Osage"', '"Noto Sans Miao"',
    '"Noto Sans Nushu"', '"Noto Sans Javanese"',
    '"Noto Serif Tibetan"',
    '"Noto Sans Hanunoo"', '"Noto Sans Buhid"', '"Noto Sans Tagbanwa"',
    '"Noto Sans Limbu"', '"Noto Sans Tai Le"', '"Noto Sans New Tai Lue"',
    '"Noto Sans Tai Tham"', '"Noto Sans Tai Viet"',
    '"Noto Sans Buginese"', '"Noto Sans Balinese"',
    '"Noto Sans Sundanese"', '"Noto Sans Batak"',
    '"Noto Sans Lepcha"', '"Noto Sans Ol Chiki"',
    '"Noto Sans Saurashtra"', '"Noto Sans Kayah Li"',
    '"Noto Sans Rejang"', '"Noto Sans Cham"', '"Noto Sans Meetei Mayek"',
    '"Noto Sans Tifinagh"', '"Noto Sans Yi"', '"Noto Sans Lisu"',
    '"Noto Sans Vai"', '"Noto Sans Bamum"',
    '"Noto Sans Hanifi Rohingya"', '"Noto Sans Wancho"',
    '"Noto Sans Mahajani"', '"Noto Sans Modi"',
    '"Noto Sans Sora Sompeng"', '"Noto Sans Takri"',
    '"Noto Sans Newa"', '"Noto Sans Sharada"',
    '"Noto Sans Khojki"', '"Noto Sans Khudawadi"', '"Noto Sans Multani"',
    '"Noto Sans Tirhuta"', '"Noto Sans Siddham"',
    '"Noto Sans Mro"', '"Noto Sans Pau Cin Hau"',
    '"Noto Sans Bassa Vah"', '"Noto Sans Pahawh Hmong"',
    '"Noto Sans Bhaiksuki"', '"Noto Sans Marchen"',
    '"Noto Sans Soyombo"', '"Noto Sans Vithkuqi"',
    '"Noto Sans Kawi"', '"Noto Sans Tangsa"',
    '"Noto Sans KR"', '"Noto Sans JP"',
  ].join(", ");

  const NOTO_HISTORICAL = [
    '"Noto Sans Egyptian Hieroglyphs"',
    '"Noto Sans Anatolian Hieroglyphs"',
    '"Noto Sans Cuneiform"',
    '"Noto Sans Old Italic"', '"Noto Sans Old Persian"',
    '"Noto Sans Old Turkic"', '"Noto Sans Old Hungarian"',
    '"Noto Sans Old Permic"',
    '"Noto Sans Old North Arabian"', '"Noto Sans Old South Arabian"',
    '"Noto Sans Old Sogdian"', '"Noto Sans Sogdian"',
    '"Noto Sans Phoenician"', '"Noto Sans Glagolitic"',
    '"Noto Sans Coptic"',
    '"Noto Sans Linear A"', '"Noto Sans Linear B"',
    '"Noto Sans Brahmi"', '"Noto Sans Ugaritic"',
    '"Noto Sans Runic"', '"Noto Sans Deseret"',
    '"Noto Sans Ogham"', '"Noto Sans Gothic"',
    '"Noto Sans Shavian"', '"Noto Sans Osmanya"',
    '"Noto Sans Cypriot"',
    '"Noto Sans Warang Citi"',
    '"Noto Sans Duployan"', '"Noto Sans SignWriting"',
    '"Noto Sans Imperial Aramaic"',
    '"Noto Sans Inscriptional Pahlavi"',
    '"Noto Sans Inscriptional Parthian"',
    '"Noto Sans Lycian"', '"Noto Sans Carian"', '"Noto Sans Lydian"',
    '"Noto Sans Avestan"', '"Noto Sans Mandaic"',
    '"Noto Sans Manichaean"',
    '"Noto Sans Nabataean"', '"Noto Sans Palmyrene"',
    '"Noto Sans Hatran"',
    '"Noto Sans Mende Kikakui"',
    '"Noto Sans Caucasian Albanian"',
    '"Noto Sans Elbasan"',
    '"Noto Sans Kharoshthi"',
    '"Noto Serif Tangut"', '"Noto Serif Khitan Small Script"',
    '"Noto Traditional Nushu"',
    '"Noto Sans"',
  ].join(", ");

  const FALLBACK = '"Last Resort HE"';
  // Also include other clusters' Notos in every chain — sometimes a script
  // appears in a "wrong" cluster (Greek/Coptic in historical, Phaistos Disc
  // in emoji-misc) and the right glyph is in another family.
  // "Noto Symbols Full" is the locally-hosted full Noto Sans Symbols 2 TTF —
  // covers Phaistos Disc and many other esoteric blocks that Google Fonts'
  // subset omits. Local first so the browser's per-codepoint walk tries it
  // before falling through to the GF subset.
  const SYMBOLS = '"Noto Symbols Full", "Noto Sans Symbols 2", "Noto Sans Symbols", "Noto Sans Math", "Noto Music", "Noto Sans Indic Siyaq Numbers"';

  const CLUSTER_FONTS = {
    "living-scripts":     `${NOTO_LIVING}, ${SYMBOLS}, ${FALLBACK}, sans-serif`,
    "historical-scripts": `${NOTO_HISTORICAL}, ${SYMBOLS}, ${FALLBACK}, serif`,
    "cjk":                `"Noto Sans SC", "Noto Sans JP", "Noto Sans KR", "Noto Sans HK", ${FALLBACK}, serif`,
    "emoji-misc":         `"Noto Color Emoji", ${SYMBOLS}, ${FALLBACK}, sans-serif`,
    "symbols-math":       `"Noto Sans Math", ${SYMBOLS}, ${FALLBACK}, serif`,
    "symbols-technical":  `"Noto Sans Mono", ${SYMBOLS}, ${FALLBACK}, monospace`,
    "punctuation-format": `"Noto Sans", ${SYMBOLS}, ${FALLBACK}, serif`,
  };

  // The full set of font families we want force-loaded before the atlas
  // bake. document.fonts.load() pulls the WOFF2 binary from the network so
  // ctx.fillText doesn't silently fall back to a system font.
  const FONTS_TO_PRELOAD = [
    "Noto Sans", "Noto Sans Mono",
    "Noto Sans SC", "Noto Sans JP", "Noto Sans KR", "Noto Sans HK",
    "Noto Sans Math", "Noto Sans Symbols", "Noto Sans Symbols 2",
    "Noto Symbols Full",
    "Noto Color Emoji", "Noto Music",
    "Noto Sans Hebrew", "Noto Sans Arabic", "Noto Sans Syriac",
    "Noto Sans Thaana", "Noto Sans NKo", "Noto Sans Mongolian",
    "Noto Sans Devanagari", "Noto Sans Bengali", "Noto Sans Gujarati",
    "Noto Sans Gurmukhi", "Noto Sans Tamil", "Noto Sans Telugu",
    "Noto Sans Kannada", "Noto Sans Malayalam", "Noto Sans Sinhala",
    "Noto Sans Thai", "Noto Sans Lao", "Noto Sans Khmer",
    "Noto Sans Tibetan", "Noto Sans Myanmar",
    "Noto Sans Georgian", "Noto Sans Armenian",
    "Noto Sans Ethiopic", "Noto Sans Cherokee",
    "Noto Sans Canadian Aboriginal",
    "Noto Sans Adlam", "Noto Sans Tagalog",
    "Noto Sans Oriya", "Noto Sans Osage", "Noto Sans Miao",
    "Noto Sans Nushu", "Noto Sans Javanese",
    "Noto Serif Tibetan", "Noto Serif Tangut",
    "Noto Serif Khitan Small Script", "Noto Traditional Nushu",
    "Noto Sans Hanunoo", "Noto Sans Buhid", "Noto Sans Tagbanwa",
    "Noto Sans Limbu", "Noto Sans Tai Le", "Noto Sans New Tai Lue",
    "Noto Sans Tai Tham", "Noto Sans Tai Viet",
    "Noto Sans Buginese", "Noto Sans Balinese",
    "Noto Sans Sundanese", "Noto Sans Batak",
    "Noto Sans Lepcha", "Noto Sans Ol Chiki",
    "Noto Sans Saurashtra", "Noto Sans Kayah Li",
    "Noto Sans Rejang", "Noto Sans Cham", "Noto Sans Meetei Mayek",
    "Noto Sans Tifinagh", "Noto Sans Yi", "Noto Sans Lisu",
    "Noto Sans Vai", "Noto Sans Bamum",
    "Noto Sans Hanifi Rohingya", "Noto Sans Wancho",
    "Noto Sans Mahajani", "Noto Sans Modi",
    "Noto Sans Sora Sompeng", "Noto Sans Takri",
    "Noto Sans Newa", "Noto Sans Sharada",
    "Noto Sans Khojki", "Noto Sans Khudawadi", "Noto Sans Multani",
    "Noto Sans Tirhuta", "Noto Sans Siddham",
    "Noto Sans Mro", "Noto Sans Pau Cin Hau",
    "Noto Sans Bassa Vah", "Noto Sans Pahawh Hmong",
    "Noto Sans Bhaiksuki", "Noto Sans Marchen",
    "Noto Sans Soyombo", "Noto Sans Vithkuqi",
    "Noto Sans Kawi", "Noto Sans Tangsa",
    "Noto Sans Egyptian Hieroglyphs", "Noto Sans Anatolian Hieroglyphs",
    "Noto Sans Cuneiform",
    "Noto Sans Old Italic", "Noto Sans Old Persian",
    "Noto Sans Old Turkic", "Noto Sans Old Hungarian",
    "Noto Sans Old Permic",
    "Noto Sans Old North Arabian", "Noto Sans Old South Arabian",
    "Noto Sans Old Sogdian", "Noto Sans Sogdian",
    "Noto Sans Phoenician", "Noto Sans Glagolitic",
    "Noto Sans Coptic",
    "Noto Sans Linear A", "Noto Sans Linear B",
    "Noto Sans Brahmi", "Noto Sans Ugaritic",
    "Noto Sans Runic", "Noto Sans Deseret",
    "Noto Sans Ogham", "Noto Sans Gothic",
    "Noto Sans Shavian", "Noto Sans Osmanya",
    "Noto Sans Cypriot",
    "Noto Sans Warang Citi",
    "Noto Sans Duployan", "Noto Sans SignWriting",
    "Noto Sans Imperial Aramaic",
    "Noto Sans Inscriptional Pahlavi", "Noto Sans Inscriptional Parthian",
    "Noto Sans Lycian", "Noto Sans Carian", "Noto Sans Lydian",
    "Noto Sans Avestan", "Noto Sans Mandaic", "Noto Sans Manichaean",
    "Noto Sans Nabataean", "Noto Sans Palmyrene",
    "Noto Sans Hatran",
    "Noto Sans Mende Kikakui",
    "Noto Sans Caucasian Albanian", "Noto Sans Elbasan",
    "Noto Sans Kharoshthi",
    "Noto Sans Indic Siyaq Numbers",
    "Last Resort HE",
  ];

  // ---------- DOM ----------
  const vizWrap   = document.getElementById("viz-wrap");
  const canvas    = document.getElementById("gl-canvas");
  const inspector = document.getElementById("inspector");
  const fpsEl     = document.getElementById("fps");
  const statusEl  = document.getElementById("status-msg");
  const stageReadoutEl = document.getElementById("stage-readout");
  const stagePrevBtn   = document.getElementById("stage-prev");
  const stageNextBtn   = document.getElementById("stage-next");
  const modeBtn        = document.getElementById("mode-btn");

  // ============================================================
  //  Per-cell index — two modes, both selectable at runtime.
  // ============================================================
  // data.js carries two layouts:
  //   - cells_stages  : 6 snapshots of textbook Lloyd's relaxation. Cells
  //                     have roughly equal areas; sites move toward
  //                     centroids over the 6 stages.
  //   - cells_weighted: a single additively-weighted (power-diagram) layout
  //                     where each cell's area tracks min(codepoints, 4096).
  //                     One "stage" because the weighted algorithm doesn't
  //                     have natural intermediate steps in the same way.
  //
  // Mode toggles with the `M` key (or the mode button). In classic mode the
  // stage stepper (←/→, 1–6) walks the snapshots; in weighted mode the
  // stepper is disabled — there's only the one layout.

  const blocks         = DATA.blocks;
  const N              = blocks.length;
  const classicStages  = DATA.cells_stages  || [DATA.cells];
  const weightedCells  = DATA.cells_weighted || DATA.cells;
  const NUM_STAGES     = classicStages.length;

  // Mode-specific layout fetcher.
  function layoutCells(mode, stageIdx) {
    return (mode === "weighted") ? weightedCells : classicStages[stageIdx];
  }
  function modeStageCount(mode) {
    return (mode === "weighted") ? 1 : NUM_STAGES;
  }

  const seedX = new Float32Array(N);
  const seedY = new Float32Array(N);
  const seedW = new Float32Array(N);
  const cellById = {};

  let activeMode  = "classic";              // "classic" | "weighted"
  let activeStage = NUM_STAGES - 1;         // default: fully-relaxed classic
  let lastClassicStage = activeStage;       // remembered across mode toggles

  function loadStageSeeds(mode, stageIdx) {
    const cs = layoutCells(mode, stageIdx);
    for (let i = 0; i < N; i++) {
      const c = cs[i];
      seedX[i] = (c.sx !== undefined) ? c.sx : c.cx;
      seedY[i] = (c.sy !== undefined) ? c.sy : c.cy;
      seedW[i] = (c.sw !== undefined) ? c.sw : 0;
    }
  }
  loadStageSeeds(activeMode, activeStage);

  for (let i = 0; i < N; i++) {
    cellById[blocks[i].id] = { idx: i, block: blocks[i] };
  }

  // Track active highlight (string id, or null)
  let activeId = null;

  // ============================================================
  //  Codepoint enumeration + sampling.
  // ============================================================

  // Parse a range string like "U+0000–U+007F" → [start, end] inclusive.
  function parseRange(s) {
    const m = s.match(/U\+([0-9A-Fa-f]+)[\u2013\u2014\-]+U\+([0-9A-Fa-f]+)/);
    if (!m) return [0, 0];
    return [parseInt(m[1], 16), parseInt(m[2], 16)];
  }

  // Unassigned (general category Cn) codepoints inside our 152 visible blocks,
  // per Unicode 17.0 DerivedGeneralCategory.txt. Sorted, merged, half-open
  // [lo, hi]. ~1,870 codepoints across 402 ranges. Without this filter, the
  // uniform per-block subsampler hits unassigned slots statistically, and
  // those render as Last Resort HE block placeholders ("little squares with
  // hex labels") — visually scattered across otherwise-coherent cells like
  // Greek and Coptic (9/144 unassigned, ~6%).
  const UNASSIGNED_RANGES = [
    [0x378,0x379], [0x380,0x383], [0x38B,0x38B], [0x38D,0x38D],
    [0x3A2,0x3A2], [0x530,0x530], [0x557,0x558], [0x58B,0x58C],
    [0x590,0x590], [0x5C8,0x5CF], [0x5EB,0x5EE], [0x5F5,0x5FF],
    [0x70E,0x70E], [0x74B,0x74C], [0x7B2,0x7BF], [0x7FB,0x7FC],
    [0x984,0x984], [0x98D,0x98E], [0x991,0x992], [0x9A9,0x9A9],
    [0x9B1,0x9B1], [0x9B3,0x9B5], [0x9BA,0x9BB], [0x9C5,0x9C6],
    [0x9C9,0x9CA], [0x9CF,0x9D6], [0x9D8,0x9DB], [0x9DE,0x9DE],
    [0x9E4,0x9E5], [0x9FF,0xA00], [0xA04,0xA04], [0xA0B,0xA0E],
    [0xA11,0xA12], [0xA29,0xA29], [0xA31,0xA31], [0xA34,0xA34],
    [0xA37,0xA37], [0xA3A,0xA3B], [0xA3D,0xA3D], [0xA43,0xA46],
    [0xA49,0xA4A], [0xA4E,0xA50], [0xA52,0xA58], [0xA5D,0xA5D],
    [0xA5F,0xA65], [0xA77,0xA80], [0xA84,0xA84], [0xA8E,0xA8E],
    [0xA92,0xA92], [0xAA9,0xAA9], [0xAB1,0xAB1], [0xAB4,0xAB4],
    [0xABA,0xABB], [0xAC6,0xAC6], [0xACA,0xACA], [0xACE,0xACF],
    [0xAD1,0xADF], [0xAE4,0xAE5], [0xAF2,0xAF8], [0xB00,0xB00],
    [0xB04,0xB04], [0xB0D,0xB0E], [0xB11,0xB12], [0xB29,0xB29],
    [0xB31,0xB31], [0xB34,0xB34], [0xB3A,0xB3B], [0xB45,0xB46],
    [0xB49,0xB4A], [0xB4E,0xB54], [0xB58,0xB5B], [0xB5E,0xB5E],
    [0xB64,0xB65], [0xB78,0xB81], [0xB84,0xB84], [0xB8B,0xB8D],
    [0xB91,0xB91], [0xB96,0xB98], [0xB9B,0xB9B], [0xB9D,0xB9D],
    [0xBA0,0xBA2], [0xBA5,0xBA7], [0xBAB,0xBAD], [0xBBA,0xBBD],
    [0xBC3,0xBC5], [0xBC9,0xBC9], [0xBCE,0xBCF], [0xBD1,0xBD6],
    [0xBD8,0xBE5], [0xBFB,0xBFF], [0xC0D,0xC0D], [0xC11,0xC11],
    [0xC29,0xC29], [0xC3A,0xC3B], [0xC45,0xC45], [0xC49,0xC49],
    [0xC4E,0xC54], [0xC57,0xC57], [0xC5B,0xC5B], [0xC5E,0xC5F],
    [0xC64,0xC65], [0xC70,0xC76], [0xC8D,0xC8D], [0xC91,0xC91],
    [0xCA9,0xCA9], [0xCB4,0xCB4], [0xCBA,0xCBB], [0xCC5,0xCC5],
    [0xCC9,0xCC9], [0xCCE,0xCD4], [0xCD7,0xCDB], [0xCDF,0xCDF],
    [0xCE4,0xCE5], [0xCF0,0xCF0], [0xCF4,0xCFF], [0xD0D,0xD0D],
    [0xD11,0xD11], [0xD45,0xD45], [0xD49,0xD49], [0xD50,0xD53],
    [0xD64,0xD65], [0xD80,0xD80], [0xD84,0xD84], [0xD97,0xD99],
    [0xDB2,0xDB2], [0xDBC,0xDBC], [0xDBE,0xDBF], [0xDC7,0xDC9],
    [0xDCB,0xDCE], [0xDD5,0xDD5], [0xDD7,0xDD7], [0xDE0,0xDE5],
    [0xDF0,0xDF1], [0xDF5,0xE00], [0xE3B,0xE3E], [0xE5C,0xE80],
    [0xE83,0xE83], [0xE85,0xE85], [0xE8B,0xE8B], [0xEA4,0xEA4],
    [0xEA6,0xEA6], [0xEBE,0xEBF], [0xEC5,0xEC5], [0xEC7,0xEC7],
    [0xECF,0xECF], [0xEDA,0xEDB], [0xEE0,0xEFF], [0xF48,0xF48],
    [0xF6D,0xF70], [0xF98,0xF98], [0xFBD,0xFBD], [0xFCD,0xFCD],
    [0xFDB,0xFFF], [0x10C6,0x10C6], [0x10C8,0x10CC], [0x10CE,0x10CF],
    [0x1249,0x1249], [0x124E,0x124F], [0x1257,0x1257], [0x1259,0x1259],
    [0x125E,0x125F], [0x1289,0x1289], [0x128E,0x128F], [0x12B1,0x12B1],
    [0x12B6,0x12B7], [0x12BF,0x12BF], [0x12C1,0x12C1], [0x12C6,0x12C7],
    [0x12D7,0x12D7], [0x1311,0x1311], [0x1316,0x1317], [0x135B,0x135C],
    [0x137D,0x137F], [0x13F6,0x13F7], [0x13FE,0x13FF], [0x169D,0x169F],
    [0x16F9,0x16FF], [0x1716,0x171E], [0x17DE,0x17DF], [0x17EA,0x17EF],
    [0x17FA,0x17FF], [0x181A,0x181F], [0x1879,0x187F], [0x18AB,0x18AF],
    [0x1A5F,0x1A5F], [0x1A7D,0x1A7E], [0x1A8A,0x1A8F], [0x1A9A,0x1A9F],
    [0x1AAE,0x1AAF], [0x1B4D,0x1B4D], [0x1F16,0x1F17], [0x1F1E,0x1F1F],
    [0x1F46,0x1F47], [0x1F4E,0x1F4F], [0x1F58,0x1F58], [0x1F5A,0x1F5A],
    [0x1F5C,0x1F5C], [0x1F5E,0x1F5E], [0x1F7E,0x1F7F], [0x1FB5,0x1FB5],
    [0x1FC5,0x1FC5], [0x1FD4,0x1FD5], [0x1FDC,0x1FDC], [0x1FF0,0x1FF1],
    [0x1FF5,0x1FF5], [0x1FFF,0x1FFF], [0x2065,0x2065], [0x2072,0x2073],
    [0x208F,0x208F], [0x209D,0x209F], [0x20C2,0x20CF], [0x218C,0x218F],
    [0x242A,0x243F], [0x2B74,0x2B75], [0x2CF4,0x2CF8], [0x2D68,0x2D6E],
    [0x2D71,0x2D7E], [0x2E5E,0x2E7F], [0x2E9A,0x2E9A], [0x2EF4,0x2EFF],
    [0x2FD6,0x2FDF], [0x3040,0x3040], [0x3097,0x3098], [0x3100,0x3104],
    [0x3130,0x3130], [0x318F,0x318F], [0x31E6,0x31EE], [0x321F,0x321F],
    [0xA48D,0xA48F], [0xA62C,0xA63F], [0xA6F8,0xA6FF], [0xA7DD,0xA7F0],
    [0xA9CE,0xA9CE], [0xA9DA,0xA9DD], [0xABEE,0xABEF], [0xABFA,0xABFF],
    [0xD7A4,0xD7AF], [0xFA6E,0xFA6F], [0xFADA,0xFAFF], [0xFB07,0xFB12],
    [0xFB18,0xFB1C], [0xFB37,0xFB37], [0xFB3D,0xFB3D], [0xFB3F,0xFB3F],
    [0xFB42,0xFB42], [0xFB45,0xFB45], [0xFDD0,0xFDEF], [0xFF00,0xFF00],
    [0xFFBF,0xFFC1], [0xFFC8,0xFFC9], [0xFFD0,0xFFD1], [0xFFD8,0xFFD9],
    [0xFFDD,0xFFDF], [0xFFE7,0xFFE7], [0xFFEF,0xFFF8], [0xFFFE,0xFFFF],
    [0x1000C,0x1000C], [0x10027,0x10027], [0x1003B,0x1003B], [0x1003E,0x1003E],
    [0x1004E,0x1004F], [0x1005E,0x1007F], [0x100FB,0x100FF], [0x1019D,0x1019F],
    [0x101A1,0x101CF], [0x101FE,0x101FF], [0x10324,0x1032C], [0x1034B,0x1034F],
    [0x1039E,0x1039E], [0x103C4,0x103C7], [0x103D6,0x103DF], [0x1049E,0x1049F],
    [0x104AA,0x104AF], [0x104D4,0x104D7], [0x104FC,0x104FF], [0x10737,0x1073F],
    [0x10756,0x1075F], [0x10768,0x1077F], [0x10806,0x10807], [0x10809,0x10809],
    [0x10836,0x10836], [0x10839,0x1083B], [0x1083D,0x1083E], [0x1091C,0x1091E],
    [0x10C49,0x10C4F], [0x10CB3,0x10CBF], [0x10CF3,0x10CF9], [0x1104E,0x11051],
    [0x11076,0x1107E], [0x118F3,0x118FE], [0x1239A,0x123FF], [0x16F4B,0x16F4E],
    [0x16F88,0x16F8E], [0x18CD6,0x18CFE], [0x1B130,0x1B131], [0x1B133,0x1B14F],
    [0x1B153,0x1B154], [0x1B156,0x1B163], [0x1B168,0x1B16F], [0x1B2FC,0x1B2FF],
    [0x1BC6B,0x1BC6F], [0x1BC7D,0x1BC7F], [0x1BC89,0x1BC8F], [0x1BC9A,0x1BC9B],
    [0x1CF2E,0x1CF2F], [0x1CF47,0x1CF4F], [0x1CFC4,0x1CFCF], [0x1D0F6,0x1D0FF],
    [0x1D127,0x1D128], [0x1D1EB,0x1D1FF], [0x1D2D4,0x1D2DF], [0x1D2F4,0x1D2FF],
    [0x1D357,0x1D35F], [0x1D455,0x1D455], [0x1D49D,0x1D49D], [0x1D4A0,0x1D4A1],
    [0x1D4A3,0x1D4A4], [0x1D4A7,0x1D4A8], [0x1D4AD,0x1D4AD], [0x1D4BA,0x1D4BA],
    [0x1D4BC,0x1D4BC], [0x1D4C4,0x1D4C4], [0x1D506,0x1D506], [0x1D50B,0x1D50C],
    [0x1D515,0x1D515], [0x1D51D,0x1D51D], [0x1D53A,0x1D53A], [0x1D53F,0x1D53F],
    [0x1D545,0x1D545], [0x1D547,0x1D549], [0x1D551,0x1D551], [0x1D6A6,0x1D6A7],
    [0x1D7CC,0x1D7CD], [0x1DA8C,0x1DA9A], [0x1DAA0,0x1DAA0], [0x1E007,0x1E007],
    [0x1E019,0x1E01A], [0x1E022,0x1E022], [0x1E025,0x1E025], [0x1E02B,0x1E02F],
    [0x1E94C,0x1E94F], [0x1E95A,0x1E95D], [0x1EE04,0x1EE04], [0x1EE20,0x1EE20],
    [0x1EE23,0x1EE23], [0x1EE25,0x1EE26], [0x1EE28,0x1EE28], [0x1EE33,0x1EE33],
    [0x1EE38,0x1EE38], [0x1EE3A,0x1EE3A], [0x1EE3C,0x1EE41], [0x1EE43,0x1EE46],
    [0x1EE48,0x1EE48], [0x1EE4A,0x1EE4A], [0x1EE4C,0x1EE4C], [0x1EE50,0x1EE50],
    [0x1EE53,0x1EE53], [0x1EE55,0x1EE56], [0x1EE58,0x1EE58], [0x1EE5A,0x1EE5A],
    [0x1EE5C,0x1EE5C], [0x1EE5E,0x1EE5E], [0x1EE60,0x1EE60], [0x1EE63,0x1EE63],
    [0x1EE65,0x1EE66], [0x1EE6B,0x1EE6B], [0x1EE73,0x1EE73], [0x1EE78,0x1EE78],
    [0x1EE7D,0x1EE7D], [0x1EE7F,0x1EE7F], [0x1EE8A,0x1EE8A], [0x1EE9C,0x1EEA0],
    [0x1EEA4,0x1EEA4], [0x1EEAA,0x1EEAA], [0x1EEBC,0x1EEEF], [0x1EEF2,0x1EEFF],
    [0x1F02C,0x1F02F], [0x1F094,0x1F09F], [0x1F0AF,0x1F0B0], [0x1F0C0,0x1F0C0],
    [0x1F0D0,0x1F0D0], [0x1F0F6,0x1F0FF], [0x1F6D9,0x1F6DB], [0x1F6ED,0x1F6EF],
    [0x1F6FD,0x1F6FF], [0x1F7DA,0x1F7DF], [0x1F7EC,0x1F7EF], [0x1F7F1,0x1F7FF],
    [0x1FA58,0x1FA5F], [0x1FA6E,0x1FA6F], [0x1FA7D,0x1FA7F], [0x1FA8B,0x1FA8D],
    [0x1FAC7,0x1FAC7], [0x1FAC9,0x1FACC], [0x1FADD,0x1FADE], [0x1FAEB,0x1FAEE],
    [0x1FAF9,0x1FAFF], [0x1FB93,0x1FB93], [0x1FBFB,0x1FBFF], [0x3347A,0x3347F],
    [0xE0000,0xE0000], [0xE0002,0xE001F],
  ];

  // Binary search the sorted UNASSIGNED_RANGES for cp.
  function isUnassigned(cp) {
    let lo = 0, hi = UNASSIGNED_RANGES.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      const r = UNASSIGNED_RANGES[mid];
      if (cp < r[0]) hi = mid - 1;
      else if (cp > r[1]) lo = mid + 1;
      else return true;
    }
    return false;
  }

  // Skip codepoints that almost never produce a useful glyph.
  function isPaintable(cp) {
    if (cp < 0x20) return false;                       // C0 control
    if (cp >= 0x7F && cp <= 0xA0) return false;        // DEL + C1
    if (cp >= 0xD800 && cp <= 0xDFFF) return false;    // surrogates
    if (cp >= 0xFDD0 && cp <= 0xFDEF) return false;    // Arabic noncharacters
    if ((cp & 0xFFFE) === 0xFFFE) return false;        // plane-end noncharacters
    if (isUnassigned(cp)) return false;                // Cn (Unicode 17.0)
    return true;
  }

  // Build a deterministic codepoint plan for `slots` glyph slots in a block of
  // codepoint range [start, end]. The plan handles both regimes:
  //   - paintable codepoints ≥ slots: subsample uniformly across the range.
  //   - paintable codepoints < slots: cycle (each codepoint repeats ~slots/n times).
  function planCodepoints(start, end, slots) {
    if (slots <= 0) return [];
    const paintable = [];
    for (let cp = start; cp <= end; cp++) {
      if (isPaintable(cp)) paintable.push(cp);
    }
    if (paintable.length === 0) return [];
    const out = new Array(slots);
    if (paintable.length >= slots) {
      const stride = paintable.length / slots;
      for (let k = 0; k < slots; k++) out[k] = paintable[Math.floor(k * stride)];
    } else {
      for (let k = 0; k < slots; k++) out[k] = paintable[k % paintable.length];
    }
    return out;
  }

  // Deterministic PRNG so atlas layouts are repeatable across reloads.
  function mulberry32(seed) {
    let t = seed >>> 0;
    return function () {
      t = (t + 0x6D2B79F5) >>> 0;
      let r = t;
      r = Math.imul(r ^ (r >>> 15), r | 1);
      r ^= r + Math.imul(r ^ (r >>> 7), r | 61);
      return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
    };
  }

  // Find the index of the cell that owns (ux, uy) under the power diagram
  // generated by additively-weighted Lloyd. Cell membership is
  //
  //     argmin_i  ||(ux, uy) - s_i||^2 - w_i
  //
  // This generalizes BCKO ch7's nearest-site Voronoi: with all w_i = 0 it
  // reduces to plain Euclidean Voronoi. The negative-weight subtraction is
  // what gives heavily-weighted sites larger cells. Linear scan over 152
  // seeds is ~10⁷ ops for 10⁵ queries; trivial.
  function nearestSeed(ux, uy) {
    let bestI = -1, bestD = Infinity;
    for (let i = 0; i < N; i++) {
      const dx = seedX[i] - ux, dy = seedY[i] - uy;
      const d = dx * dx + dy * dy - seedW[i];
      if (d < bestD) { bestD = d; bestI = i; }
    }
    return bestI;
  }

  // ============================================================
  //  Atlas builder — Vogel sunflower spiral, cell-tinted.
  // ============================================================
  // Lay glyph centers along a Vogel phyllotaxis spiral that fills the disk
  // at constant point density 1/(π·c²) and minimum nearest-neighbor distance
  // ≈ c. Each position is then tagged with the Voronoi cell that owns it
  // (nearest seed); within each cell we plan codepoints (subsample if
  // codepoints ≥ slots, cycle if codepoints < slots) so density is uniform
  // regardless of block size.

  function nextFrame() {
    return new Promise(resolve => requestAnimationFrame(() => resolve()));
  }

  async function buildAtlas(onProgress) {
    const t0 = performance.now();
    const cv = document.createElement("canvas");
    cv.width = ATLAS_SIZE;
    cv.height = ATLAS_SIZE;
    const ctx = cv.getContext("2d", { alpha: true });

    ctx.clearRect(0, 0, ATLAS_SIZE, ATLAS_SIZE);
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    // ---- Phase 1: generate spiral positions and assign each to a cell. ----
    // Margin keeps the outermost glyph fully inside the disk.
    const fontSize = SPIRAL_C * SIZE_RATIO;
    const rMaxAtlas = DISK_RADIUS_PX - fontSize * 0.5 - 1.0;
    const K = Math.max(0, Math.floor((rMaxAtlas / SPIRAL_C) ** 2) - SPIRAL_K0);

    // Per-cell bin: positions assigned to cell i.
    const bins = new Array(N);
    for (let i = 0; i < N; i++) bins[i] = [];

    for (let j = 0; j < K; j++) {
      const k = j + SPIRAL_K0;
      const r = SPIRAL_C * Math.sqrt(k + 0.5);
      const theta = k * GOLDEN_ANGLE;
      // Atlas pixel coords with origin at center.
      const xa = ATLAS_CENTER + r * Math.cos(theta);
      const ya = ATLAS_CENTER + r * Math.sin(theta);
      // Convert to unit coords for the seed lookup.
      const ux = (xa - ATLAS_CENTER) / DISK_RADIUS_PX;
      const uy = (ya - ATLAS_CENTER) / DISK_RADIUS_PX;
      const idx = nearestSeed(ux, uy);
      if (idx < 0) continue;
      bins[idx].push(xa, ya);
    }

    // ---- Phase 2: paint each cell's glyphs. Yield periodically so the ----
    // status strip can repaint mid-build.
    let totalPainted = 0;
    const YIELD_EVERY = 16;

    for (let i = 0; i < N; i++) {
      const block = blocks[i];
      const positionsFlat = bins[i];
      const slots = positionsFlat.length / 2;

      if (slots > 0) {
        const [start, end] = parseRange(block.range);
        const plan = planCodepoints(start, end, slots);

        if (plan.length > 0) {
          // Shuffle the position-to-codepoint mapping so any cycling in the
          // codepoint plan doesn't show up as a visible row pattern.
          const idxs = new Array(slots);
          for (let k = 0; k < slots; k++) idxs[k] = k;
          const rng = mulberry32(0x9E3779B1 ^ (i * 2654435761));
          for (let k = slots - 1; k > 0; k--) {
            const m = Math.floor(rng() * (k + 1));
            const tmp = idxs[k]; idxs[k] = idxs[m]; idxs[m] = tmp;
          }

          // Measure each glyph at a reference em-size, then scale non-uniformly
          // so its visual bbox fills the SPIRAL_C × SPIRAL_C slot. Latin "i"
          // gets stretched horizontally; CJK passes through unchanged; Last
          // Resort placeholders that overflow the em get squashed to fit.
          // Scale factors are clamped: degenerate metrics (combining marks,
          // variation selectors, zero-width joiners) would otherwise scale
          // to infinity and paint solid horizontal bars.
          const refSize = SPIRAL_C;
          ctx.font = `${refSize.toFixed(2)}px ${CLUSTER_FONTS[block.cluster]}`;
          ctx.fillStyle = DATA.palette[block.cluster];

          const target = SPIRAL_C * SIZE_RATIO;  // visual bbox side, in atlas px
          const SCALE_MIN = 0.5;
          const SCALE_MAX = 5.0;                  // narrow chars (Latin "i", periods, IPA tails) need bigger stretch to fill 1.45c slots
          const MIN_BBOX  = refSize * 0.10;       // below this the glyph is essentially zero-area; skip

          let painted = 0;
          for (let k = 0; k < slots; k++) {
            const ch = String.fromCodePoint(plan[idxs[k]]);
            // Combining marks (Mn/Me), variation selectors, ZWJ, format
            // controls report zero/tiny bbox in isolation — fillText would
            // either silently no-op or paint a single horizontal bar (target/w
            // → ∞). Detect and retry with U+25CC DOTTED CIRCLE prefix, which
            // is Unicode's canonical "isolated combining mark" presentation.
            // If the compound is still degenerate, skip the slot.
            let toDraw = ch;
            let m = ctx.measureText(toDraw);
            let w = m.width;
            let ascent  = m.actualBoundingBoxAscent  || refSize * 0.8;
            let descent = m.actualBoundingBoxDescent || refSize * 0.2;
            let h = ascent + descent;
            if (w < MIN_BBOX || h < MIN_BBOX) {
              toDraw = "\u25CC" + ch;
              m = ctx.measureText(toDraw);
              w = m.width;
              ascent  = m.actualBoundingBoxAscent  || refSize * 0.8;
              descent = m.actualBoundingBoxDescent || refSize * 0.2;
              h = ascent + descent;
              if (w < MIN_BBOX || h < MIN_BBOX) continue;
            }
            const sx = Math.min(SCALE_MAX, Math.max(SCALE_MIN, target / w));
            const sy = Math.min(SCALE_MAX, Math.max(SCALE_MIN, target / h));
            ctx.save();
            ctx.translate(positionsFlat[2 * k], positionsFlat[2 * k + 1]);
            ctx.scale(sx, sy);
            // Recenter vertically: with textBaseline=middle, the glyph's
            // visual mid-line is roughly at y=0, but ascent/descent often
            // differ; nudge by half the difference so the box centers exactly.
            ctx.fillText(toDraw, 0, (descent - ascent) * 0.5);
            ctx.restore();
            painted++;
          }
          totalPainted += painted;
        }
      }

      if ((i + 1) % YIELD_EVERY === 0 || i === N - 1) {
        if (onProgress) onProgress(i + 1, N, totalPainted);
        await nextFrame();
      }
    }

    // A subtle ink-dim disk-edge ring, baked into the atlas. Because the
    // fragment shader samples this texture through an inverse warp, the
    // ring stretches naturally with the lens — no separate draw call.
    ctx.lineWidth = 1.4;
    ctx.strokeStyle = "rgba(90, 80, 72, 0.55)"; // --ink-dim
    ctx.beginPath();
    ctx.arc(ATLAS_CENTER, ATLAS_CENTER, DISK_RADIUS_PX - 1.0, 0, Math.PI * 2);
    ctx.stroke();

    const dt = (performance.now() - t0) | 0;
    return { canvas: cv, charCount: totalPainted, totalSpiral: K, buildMs: dt };
  }

  // ============================================================
  //  WebGL renderer.
  // ============================================================
  // One static quad covering the unit square [-1, 1]². The fragment shader
  // applies an inverse fisheye (radial fixed-point solve) and samples the
  // pre-baked atlas. Pixels outside the unit disk are discarded.

  // Vertex shader: the quad is a full-viewport [-1,1]² in clip space.
  // The disk lives at u_diskCenterClip with half-extent u_diskRadiusClip
  // (in clip-space units; x and y differ when the viewport isn't square).
  // Each fragment recovers its unit-disk coordinate from its clip position
  // so the lens can warp content well past the disk's geometric edge —
  // those off-disk fragments simply get a discard once their inverse
  // source point lands outside the unit disk.
  const VS_SRC = `
precision highp float;
attribute vec2 a_clip;
varying vec2 v_clip;

void main() {
    v_clip = a_clip;
    gl_Position = vec4(a_clip, 0.0, 1.0);
}`;

  // mediump fallback for fragment precision: most desktop GPUs honor highp,
  // but some mobile drivers (especially older PowerVR) reject it. We rely on
  // GL_FRAGMENT_PRECISION_HIGH to pick. Without highp the inverse iteration
  // is still numerically fine for unit-coord math at our scale.
  const FS_SRC = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
varying vec2 v_clip;

uniform sampler2D u_atlas;
uniform vec2  u_cursor;
uniform float u_cursorActive;
uniform float u_A;
uniform float u_twoSigSq;
uniform float u_sigma;
uniform float u_lensThicknessU;   // half-thickness of the lens ring in unit coords
uniform vec3  u_lensColor;
uniform vec2  u_diskCenterClip;
uniform vec2  u_diskRadiusClip;

const float PI = 3.14159265359;
const float TAU = 6.28318530718;

void main() {
    // Recover unit-disk coords from clip-space (with the +y-down flip).
    vec2 v_unit = vec2(
         (v_clip.x - u_diskCenterClip.x) / u_diskRadiusClip.x,
        -(v_clip.y - u_diskCenterClip.y) / u_diskRadiusClip.y
    );

    // ---------- Inverse fisheye ----------
    // Forward warp: q = u + (p - u) * (1 + A * exp(-|p-u|^2 / 2sigma^2))
    // Direction is preserved (radial); we solve only for r_p given r_q.
    vec2 sourceUnit = v_unit;
    if (u_cursorActive > 0.5) {
        vec2 d = v_unit - u_cursor;
        float rq = length(d);
        if (rq > 1e-6) {
            float rp = rq;
            // Fixed-point iteration converges geometrically because f(r) is
            // bounded and Lipschitz < 1 in the fixed-point neighborhood for
            // A < ~6. Seven iterations is comfortable for A=4.
            for (int i = 0; i < 7; i++) {
                float fr = 1.0 + u_A * exp(-rp * rp / u_twoSigSq);
                rp = rq / fr;
            }
            sourceUnit = u_cursor + d * (rp / rq);
        } else {
            sourceUnit = u_cursor;
        }
    }

    // ---------- Disk SDF clip ----------
    float r_src = length(sourceUnit);
    if (r_src > 1.0) discard;

    // ---------- Texture sample ----------
    // atlas was uploaded with UNPACK_FLIP_Y_WEBGL=true so its v=0 is at the
    // top of the canvas; sourceUnit's +y is also down, so a straight
    // (sourceUnit*0.5+0.5) UV maps correctly.
    vec2 uv = sourceUnit * 0.5 + 0.5;
    vec4 tex = texture2D(u_atlas, uv);

    // The atlas is drawn with non-premultiplied alpha; convert here.
    vec3 rgb = tex.rgb;
    float a = tex.a;

    // ---------- Lens ring (screen-space, undisplaced) ----------
    if (u_cursorActive > 0.5) {
        float dToCursor = length(v_unit - u_cursor);
        float ringDist = abs(dToCursor - u_sigma);
        float ringMask = 1.0 - smoothstep(0.0, u_lensThicknessU, ringDist);
        // Dashed: 16 segments
        float ang = atan(v_unit.y - u_cursor.y, v_unit.x - u_cursor.x);
        float dash = step(0.5, fract(ang * 16.0 / TAU));
        ringMask *= dash * 0.36;
        rgb = mix(rgb, u_lensColor, ringMask);
        a   = max(a, ringMask);
    }

    // Premultiplied output, paired with blendFunc(ONE, ONE_MINUS_SRC_ALPHA).
    gl_FragColor = vec4(rgb * a, a);
}`;

  const webgl = (function () {
    let gl = null;
    let supported = true;
    let dpr = 1;

    let prog;
    let aClip;
    let uAtlas, uCursor, uCursorActive, uA, uTwoSigSq, uSigma;
    let uLensColor, uLensThicknessU;
    let uDiskCenterClip, uDiskRadiusClip;

    let quadBuf;
    let activeAtlasTex = null;

    function compile(type, src) {
      const sh = gl.createShader(type);
      gl.shaderSource(sh, src);
      gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
        throw new Error("Shader compile failed: " + gl.getShaderInfoLog(sh));
      }
      return sh;
    }

    function buildProgram() {
      const vs = compile(gl.VERTEX_SHADER, VS_SRC);
      const fs = compile(gl.FRAGMENT_SHADER, FS_SRC);
      prog = gl.createProgram();
      gl.attachShader(prog, vs);
      gl.attachShader(prog, fs);
      gl.linkProgram(prog);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
        throw new Error("Program link failed: " + gl.getProgramInfoLog(prog));
      }
      gl.useProgram(prog);

      aClip         = gl.getAttribLocation(prog, "a_clip");
      uAtlas        = gl.getUniformLocation(prog, "u_atlas");
      uCursor       = gl.getUniformLocation(prog, "u_cursor");
      uCursorActive = gl.getUniformLocation(prog, "u_cursorActive");
      uA            = gl.getUniformLocation(prog, "u_A");
      uTwoSigSq     = gl.getUniformLocation(prog, "u_twoSigSq");
      uSigma        = gl.getUniformLocation(prog, "u_sigma");
      uLensColor    = gl.getUniformLocation(prog, "u_lensColor");
      uLensThicknessU = gl.getUniformLocation(prog, "u_lensThicknessU");
      uDiskCenterClip = gl.getUniformLocation(prog, "u_diskCenterClip");
      uDiskRadiusClip = gl.getUniformLocation(prog, "u_diskRadiusClip");

      gl.uniform1i(uAtlas, 0);
      gl.uniform1f(uA, A_MAX * lensIntensity);
      gl.uniform1f(uTwoSigSq, TWOSIGSQ);
      gl.uniform1f(uSigma, SIGMA);
      gl.uniform2f(uDiskCenterClip, 0, 0);
      gl.uniform2f(uDiskRadiusClip, 1, 1);
      gl.uniform3f(uLensColor, 0.165, 0.145, 0.125); // ink
      gl.uniform1f(uLensThicknessU, 0.003);
    }

    function buildQuad() {
      // Two triangles covering [-1,1] × [-1,1] in unit coords.
      const verts = new Float32Array([
        -1, -1,   1, -1,   1, 1,
        -1, -1,   1,  1,  -1, 1,
      ]);
      quadBuf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, quadBuf);
      gl.bufferData(gl.ARRAY_BUFFER, verts, gl.STATIC_DRAW);
    }

    function uploadAtlas(canvasSrc) {
      const tex = gl.createTexture();
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, tex);
      // No flip: our vertex shader already negates unit.y to get clip.y, so the
      // shader's uv = sourceUnit*0.5+0.5 maps sourceUnit.y=-1 (top of disk) to
      // uv.y=0, which without flip lands on canvas row 0 (top of canvas).
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
      gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, canvasSrc);

      // ATLAS_SIZE is power of two so mipmaps are legal.
      // Min filter stays LINEAR_MIPMAP_LINEAR (trilinear): when the lens shrinks
      // the source patch, mipmaps + linear interpolation across them keeps the
      // far field smooth. Mag filter is NEAREST: under magnification the lens
      // upsamples atlas texels by ~2.4×, and bilinear over that upscale washes
      // the glyphs out. Nearest preserves sharp edges at the cost of pixel
      // stairstepping — the user explicitly preferred crisp-and-pixelated to
      // smooth-and-blurry.
      gl.generateMipmap(gl.TEXTURE_2D);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

      // Anisotropic filtering, when available — the lens stretches the
      // texture asymmetrically, which is exactly what aniso is for.
      const aniso = gl.getExtension("EXT_texture_filter_anisotropic")
                 || gl.getExtension("MOZ_EXT_texture_filter_anisotropic")
                 || gl.getExtension("WEBKIT_EXT_texture_filter_anisotropic");
      if (aniso) {
        const max = gl.getParameter(aniso.MAX_TEXTURE_MAX_ANISOTROPY_EXT);
        gl.texParameterf(gl.TEXTURE_2D, aniso.TEXTURE_MAX_ANISOTROPY_EXT, Math.min(8, max));
      }
      return tex;
    }

    // Phase 1: open the GL context, set up the program and quad, and report
    // back the device's MAX_TEXTURE_SIZE so the caller can size the atlas.
    function createContext() {
      const ctxOpts = { antialias: true, premultipliedAlpha: true, alpha: true };
      gl = canvas.getContext("webgl", ctxOpts)
        || canvas.getContext("experimental-webgl", ctxOpts);
      if (!gl) { supported = false; return null; }

      try {
        buildProgram();
        buildQuad();
      } catch (e) {
        console.error(e);
        supported = false;
        return null;
      }

      gl.enable(gl.BLEND);
      gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      gl.disable(gl.DEPTH_TEST);
      gl.clearColor(0, 0, 0, 0);
      resize();

      return { maxTextureSize: gl.getParameter(gl.MAX_TEXTURE_SIZE) };
    }

    // Phase 2: upload an atlas Canvas2D as a fresh GPU texture; returns the
    // texture handle on success, or null on GL error. Stages each get their
    // own handle, cached by `setActiveAtlas`.
    function createAtlasTexture(atlasCanvas) {
      let tex;
      try {
        tex = uploadAtlas(atlasCanvas);
      } catch (e) {
        console.error(e);
        supported = false;
        return null;
      }
      const err = gl.getError();
      if (err !== gl.NO_ERROR) {
        console.warn("GL error after atlas upload:", err);
        supported = false;
        return null;
      }
      return tex;
    }

    function setActiveAtlas(tex) {
      activeAtlasTex = tex;
    }

    // The canvas is 200% × 200% of viz-wrap, centered on it, so the disk
    // (an inscribed circle of viz-wrap) sits at the canvas centre with a
    // radius of one quarter of the canvas's CSS width — i.e. half of the
    // canvas's clip-space half-extent. Constant; no tracking required.
    function updateDiskGeometry() {
      if (!gl || !prog) return;
      gl.useProgram(prog);
      gl.uniform2f(uDiskCenterClip, 0, 0);
      gl.uniform2f(uDiskRadiusClip, 0.5, 0.5);
    }

    function resize() {
      if (!gl) return;
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      const cssW = canvas.clientWidth;
      const cssH = canvas.clientHeight;
      const w = Math.max(1, Math.floor(cssW * dpr));
      const h = Math.max(1, Math.floor(cssH * dpr));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      gl.viewport(0, 0, w, h);
      updateDiskGeometry();
    }

    function render() {
      if (!gl) return;
      resize();
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.useProgram(prog);

      if (cursorUnit) {
        gl.uniform2f(uCursor, cursorUnit[0], cursorUnit[1]);
        gl.uniform1f(uCursorActive, 1.0);
      } else {
        gl.uniform2f(uCursor, 0, 0);
        gl.uniform1f(uCursorActive, 0.0);
      }

      if (!activeAtlasTex) return;

      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, activeAtlasTex);

      gl.bindBuffer(gl.ARRAY_BUFFER, quadBuf);
      gl.enableVertexAttribArray(aClip);
      gl.vertexAttribPointer(aClip, 2, gl.FLOAT, false, 0, 0);

      gl.drawArrays(gl.TRIANGLES, 0, 6);
    }

    // Push the current lensIntensity to u_A. Called from the wheel handler;
    // safe to call before the program is built (no-op).
    function pushLensIntensity() {
      if (!gl || !prog) return;
      gl.useProgram(prog);
      gl.uniform1f(uA, A_MAX * lensIntensity);
    }

    return {
      createContext, createAtlasTexture, setActiveAtlas, render, resize,
      pushLensIntensity,
      isSupported: () => supported,
    };
  })();

  // ============================================================
  //  Frame loop
  // ============================================================

  let cursorUnit = null;
  let rafHandle  = null;
  let frameCount = 0;
  let fpsLastT   = performance.now();

  function frame() {
    rafHandle = null;
    webgl.render();

    frameCount++;
    const now = performance.now();
    if (now - fpsLastT >= 500) {
      const fps = (frameCount * 1000) / (now - fpsLastT);
      fpsLastT = now;
      frameCount = 0;
      fpsEl.textContent = fps.toFixed(0) + " fps";
    }
  }

  function requestUpdate() {
    if (!rafHandle) rafHandle = requestAnimationFrame(frame);
  }

  // ============================================================
  //  Cursor → unit coords → fisheye + inspector hit-test.
  // ============================================================

  const CORNER_MARGIN = 0.10;
  const ANTIPODE = { tl: "br", tr: "bl", bl: "tr", br: "tl" };

  function updateAntipodalCorner(cx, cy) {
    const wx = window.innerWidth, wy = window.innerHeight;
    const lo_x = wx * (0.5 - CORNER_MARGIN), hi_x = wx * (0.5 + CORNER_MARGIN);
    const lo_y = wy * (0.5 - CORNER_MARGIN), hi_y = wy * (0.5 + CORNER_MARGIN);
    let hx = null, vy = null;
    if (cx < lo_x) hx = "l"; else if (cx > hi_x) hx = "r";
    if (cy < lo_y) vy = "t"; else if (cy > hi_y) vy = "b";
    if (!hx || !vy) return;
    const target = ANTIPODE[vy + hx];
    if (!inspector.classList.contains("pos-" + target)) {
      inspector.classList.remove("pos-tl", "pos-tr", "pos-bl", "pos-br");
      inspector.classList.add("pos-" + target);
    }
  }

  // Convert a viewport-space (clientX, clientY) into our unit coordinate
  // system [-1, 1] using viz-wrap's bounding rect (the disk lives there;
  // the canvas itself is full-viewport).
  function clientToUnit(clientX, clientY) {
    const r = vizWrap.getBoundingClientRect();
    const u = ((clientX - r.left) / r.width) * 2 - 1;
    const v = ((clientY - r.top)  / r.height) * 2 - 1;
    return [u, v];
  }

  function updateCursorFromEvent(evt) {
    updateAntipodalCorner(evt.clientX, evt.clientY);
    const [ux, uy] = clientToUnit(evt.clientX, evt.clientY);
    const r = Math.sqrt(ux * ux + uy * uy);
    const wasActive = cursorUnit != null;
    cursorUnit = (r > 1.05) ? null : [ux, uy];
    requestUpdate();

    if (!cursorUnit) {
      if (wasActive) clearHighlight();
      return;
    }
    // Nearest-seed hit-test. cursorUnit is in unwarped substrate space, so the
    // same nearestSeed used at atlas-build time gives the right cell.
    const bestI = nearestSeed(ux, uy);
    if (bestI >= 0) highlightCell(blocks[bestI].id);
  }

  function highlightCell(id) {
    if (id === activeId) return;
    activeId = id;
    renderInspector(cellById[id].block);
    requestUpdate();
  }

  function clearHighlight() {
    activeId = null;
    inspector.classList.add("resting");
    requestUpdate();
  }

  // ============================================================
  //  Inspector + legend (mostly unchanged from the original)
  // ============================================================

  function renderInspector(b) {
    inspector.classList.remove("resting");
    const clusterColor = DATA.palette[b.cluster];
    const clusterLabel = DATA.labels[b.cluster];
    const metaRow = inspector.querySelector(".meta-row");
    metaRow.innerHTML =
      '<span class="meta-item">' + escapeHtml(b.range) + '</span>' +
      '<span class="meta-item"><span class="bucket-chip" style="background:' + clusterColor + '"></span><strong>' + escapeHtml(clusterLabel) + '</strong></span>' +
      '<span class="meta-item">' + escapeHtml(b.size) + '</span>';
    inspector.querySelector(".project-name").textContent = b.name;
    inspector.querySelector(".desc").textContent = b.desc;

    const fontByCluster = {
      "living-scripts": "font-living", "historical-scripts": "font-historical",
      "cjk": "font-cjk", "emoji-misc": "font-emoji", "symbols-math": "font-math",
      "symbols-technical": "font-technical", "punctuation-format": "font-punct",
    };
    const fontClass = fontByCluster[b.cluster] || "font-living";
    const glyphEl = inspector.querySelector(".glyphs-display");
    glyphEl.innerHTML = "";
    (b.glyphs || []).slice(0, 3).forEach(g => {
      const span = document.createElement("span");
      span.className = "g " + fontClass;
      span.textContent = g;
      glyphEl.appendChild(span);
    });

    const tidbitEl      = inspector.querySelector(".tidbit");
    const tidbitLabelEl = inspector.querySelector(".tidbit-note-label");
    if (b.tidbit && b.tidbit.trim().length > 0) {
      tidbitEl.textContent = b.tidbit;
      tidbitEl.style.display = ""; tidbitLabelEl.style.display = "";
    } else {
      tidbitEl.textContent = "";
      tidbitEl.style.display = "none"; tidbitLabelEl.style.display = "none";
    }
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }

  function buildLegend() {
    const legendGrid = document.getElementById("legend-grid");
    DATA.order.forEach(bucket => {
      const row = document.createElement("div");
      row.className = "legend-row";
      row.innerHTML =
        '<span class="sw" style="background:' + DATA.palette[bucket] + '"></span>' +
        '<span class="lname">' + escapeHtml(DATA.labels[bucket]) + '</span>' +
        '<span class="lcount">' + DATA.counts[bucket] + '</span>';
      legendGrid.appendChild(row);
    });
  }

  // ============================================================
  //  Event wiring
  // ============================================================

  // Whether a viewport coordinate falls within the disk (with a small
  // slack so the cursor doesn't pop out at the edge).
  function inDisk(clientX, clientY) {
    const [ux, uy] = clientToUnit(clientX, clientY);
    return (ux * ux + uy * uy) <= 1.05 * 1.05;
  }

  function wireEvents() {
    // The canvas is pointer-events:none, so we listen on the window. The
    // inspector aside has its own z-index; clicks inside it never reach us.
    window.addEventListener("mousemove", evt => {
      if (inspector.contains(evt.target)) return;
      updateCursorFromEvent(evt);
    });

    // No "mouseleave" on window — instead, the cursor is cleared whenever
    // it strays outside the disk in `updateCursorFromEvent`.

    window.addEventListener("click", evt => {
      if (inspector.contains(evt.target)) return;
      if (inDisk(evt.clientX, evt.clientY)) {
        updateCursorFromEvent(evt);
      } else {
        clearHighlight();
      }
    });

    // Wheel modulates lens intensity in [0, 1]; only intercept when the
    // cursor is over the disk so the rest of the page scrolls normally.
    window.addEventListener("wheel", evt => {
      if (!inDisk(evt.clientX, evt.clientY)) return;
      evt.preventDefault();
      const next = Math.max(0, Math.min(1, lensIntensity - evt.deltaY * WHEEL_GAIN));
      if (next === lensIntensity) return;
      lensIntensity = next;
      webgl.pushLensIntensity();
      refreshLiveStatus();
      requestUpdate();
    }, { passive: false });

    // Stage stepper: ←/→ and 1–6, plus the dedicated buttons in the
    // status strip. Number keys jump directly; arrows step. Ignored when
    // a form field has focus so the page stays accessible.
    window.addEventListener("keydown", evt => {
      const tag = (evt.target && evt.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA" || evt.target.isContentEditable) return;
      if (evt.key === "ArrowLeft")  { stepStage(-1); evt.preventDefault(); }
      else if (evt.key === "ArrowRight") { stepStage(+1); evt.preventDefault(); }
      else if (/^[1-9]$/.test(evt.key)) {
        const n = parseInt(evt.key, 10) - 1;
        if (n >= 0 && n < NUM_STAGES) { switchStage("classic", n); evt.preventDefault(); }
      }
      else if (evt.key === "m" || evt.key === "M") { toggleMode(); evt.preventDefault(); }
    });

    if (stagePrevBtn) stagePrevBtn.addEventListener("click", () => stepStage(-1));
    if (stageNextBtn) stageNextBtn.addEventListener("click", () => stepStage(+1));
    if (modeBtn)      modeBtn.addEventListener("click", () => toggleMode());

    window.addEventListener("resize", () => {
      webgl.resize();
      requestUpdate();
    });
  }

  // ============================================================
  //  Boot
  // ============================================================

  function setStatus(msg) { if (statusEl) statusEl.textContent = msg; }

  // After boot, the status strip stays on a stable "live …" banner that ends
  // with the current lens intensity. The wheel handler and the stage stepper
  // both call this; it pulls fresh stats for whichever stage is currently
  // active, so the banner stays in sync with what's actually on screen.
  function refreshLiveStatus() {
    const s = cacheFor(activeMode).stats[activeStage];
    if (!s) return;
    const pct = Math.round(lensIntensity * 100);
    const label = (activeMode === "weighted")
      ? "weighted layout"
      : `Lloyd stage ${activeStage + 1}/${NUM_STAGES}`;
    setStatus(
      `live · ${label} · ` +
      `${s.glyphs.toLocaleString()} glyphs (${s.slots.toLocaleString()} slots) ` +
      `in ${s.ms} ms · lens ${pct}%`
    );
  }

  // Force-load every font family we plan to use in the atlas. @font-face fonts
  // are lazy by default — the browser only fetches the WOFF2 binary when
  // something asks for it. We need them ALL loaded before fillText runs,
  // because Canvas2D bakes whatever font is currently resolved at draw time:
  // late-arriving fonts won't retroactively redraw the atlas.
  async function loadFonts(onProgress) {
    if (!document.fonts || !document.fonts.load) return;
    let done = 0;
    const total = FONTS_TO_PRELOAD.length;
    if (onProgress) onProgress(0, total);
    await Promise.all(FONTS_TO_PRELOAD.map(async name => {
      try {
        await document.fonts.load(`16px "${name}"`);
      } catch (e) {
        // A network failure on one font shouldn't sink the whole atlas — the
        // fallback chain is long and the cluster will just degrade gracefully.
        console.warn(`font load failed: ${name}`, e);
      } finally {
        done++;
        if (onProgress) onProgress(done, total);
      }
    }));
    // Belt-and-suspenders: also wait for the global FontFaceSet to settle.
    try { await document.fonts.ready; } catch (_) {}
  }

  async function boot() {
    buildLegend();
    wireEvents();

    setStatus("opening WebGL context…");
    await nextFrame();

    const ctxInfo = webgl.createContext();
    if (!ctxInfo) {
      setStatus("WebGL is unavailable in this browser.");
      return;
    }

    if (ctxInfo.maxTextureSize < ATLAS_SIZE) {
      setStatus(
        `this device caps textures at ${ctxInfo.maxTextureSize}², ` +
        `below the ${ATLAS_SIZE}² atlas this build assumes.`
      );
      return;
    }

    setStatus(`fetching ${FONTS_TO_PRELOAD.length} fonts…`);
    await nextFrame();
    await loadFonts((done, total) => {
      setStatus(`fetching fonts (${done}/${total} loaded)…`);
    });

    // Build the default classic-mode final stage first so the page is
    // interactive as soon as possible. Other stages — and the weighted
    // mode — get built on demand and cached on first visit.
    await ensureStageBuilt(activeMode, activeStage, /*becomeActive*/ true);
  }

  // ============================================================
  //  Stage stepping + mode toggling
  // ============================================================
  // Atlases are cached per (mode, stage). For weighted mode there's only
  // one stage so its cache is a single slot. For classic mode there are
  // NUM_STAGES slots. First visit pays the ~5 s atlas-build cost; revisits
  // are an instant texture-bind.
  const stageCache = {
    classic:  { textures: new Array(NUM_STAGES), stats: new Array(NUM_STAGES) },
    weighted: { textures: [null], stats: [null] },
  };
  let buildingStage = false;

  function cacheFor(mode) { return stageCache[mode]; }

  // Build the atlas for (mode, idx), caching its texture. The seeds get
  // loaded for the duration of the build (the spiral assignment scans
  // against seedX/Y/W) and then restored to whatever's on screen, unless
  // `becomeActive` is true.
  async function ensureStageBuilt(mode, idx, becomeActive) {
    const cache = cacheFor(mode);
    if (cache.textures[idx]) {
      if (becomeActive) commitActiveStage(mode, idx);
      return true;
    }
    if (buildingStage) return false;
    buildingStage = true;
    const restoreMode = activeMode, restoreStage = activeStage;
    refreshStageReadout();
    loadStageSeeds(mode, idx);
    const label = stageLabel(mode, idx);
    setStatus(`tracing spiral & painting glyphs for ${label}…`);
    await nextFrame();
    const { canvas: atlasCanvas, charCount, totalSpiral, buildMs } = await buildAtlas(
      (done, total, painted) => {
        setStatus(`${label}: painting ${painted.toLocaleString()} glyphs (${done}/${total} cells)…`);
      }
    );
    setStatus(`uploading ${label} atlas to GPU…`);
    await nextFrame();
    const tex = webgl.createAtlasTexture(atlasCanvas);
    buildingStage = false;
    if (!tex) {
      setStatus("texture upload failed.");
      return false;
    }
    cache.textures[idx] = tex;
    cache.stats[idx] = { glyphs: charCount, slots: totalSpiral, ms: buildMs };
    if (becomeActive) {
      commitActiveStage(mode, idx);
    } else {
      loadStageSeeds(restoreMode, restoreStage);
    }
    refreshStageReadout();
    refreshLiveStatus();
    requestUpdate();
    return true;
  }

  function stageLabel(mode, idx) {
    return (mode === "weighted")
      ? "weighted layout"
      : `Lloyd stage ${idx + 1}/${NUM_STAGES}`;
  }

  function commitActiveStage(mode, idx) {
    activeMode = mode;
    activeStage = idx;
    if (mode === "classic") lastClassicStage = idx;
    loadStageSeeds(mode, idx);
    webgl.setActiveAtlas(cacheFor(mode).textures[idx]);
    if (cursorUnit) {
      const bestI = nearestSeed(cursorUnit[0], cursorUnit[1]);
      if (bestI >= 0) { activeId = null; highlightCell(blocks[bestI].id); }
    }
  }

  async function switchStage(mode, idx) {
    if (mode === activeMode && idx === activeStage) return;
    const max = modeStageCount(mode);
    if (idx < 0 || idx >= max) return;
    const cache = cacheFor(mode);
    if (cache.textures[idx]) {
      commitActiveStage(mode, idx);
      refreshStageReadout();
      refreshLiveStatus();
      requestUpdate();
    } else {
      await ensureStageBuilt(mode, idx, /*becomeActive*/ true);
    }
  }

  function stepStage(delta) {
    if (activeMode !== "classic") return;     // weighted has only one stage
    let n = activeStage + delta;
    if (n < 0) n = 0;
    if (n >= NUM_STAGES) n = NUM_STAGES - 1;
    switchStage("classic", n);
  }

  function toggleMode() {
    if (activeMode === "classic") {
      switchStage("weighted", 0);
    } else {
      switchStage("classic", lastClassicStage);
    }
  }

  function refreshStageReadout() {
    const cache = cacheFor(activeMode);
    if (stageReadoutEl) {
      if (activeMode === "weighted") {
        const built = cache.textures[0] ? "" : " · building";
        stageReadoutEl.textContent = `weighted${built}`;
      } else {
        const built = cache.textures[activeStage] ? "" : " · building";
        stageReadoutEl.textContent = `Lloyd ${activeStage + 1} / ${NUM_STAGES}${built}`;
      }
    }
    const atFirst = (activeMode !== "classic") || activeStage === 0;
    const atLast  = (activeMode !== "classic") || activeStage === NUM_STAGES - 1;
    if (stagePrevBtn) stagePrevBtn.disabled = atFirst || buildingStage;
    if (stageNextBtn) stageNextBtn.disabled = atLast  || buildingStage;
    if (modeBtn) modeBtn.textContent = (activeMode === "classic")
      ? "switch to weighted"
      : "switch to classic";
  }

  boot();
})();
