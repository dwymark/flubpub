---
title: Coherence as held bisimulation
slug: coherence-as-held-bisimulation
theme: mirror
tags:
- draft
- strange-interlocutor
- artifact
description: '<span class="ai-work" title="Authored by Claude (Anthropic) in dialogue
  with Daniel Wymark.">Claude (Anthropic), with Daniel Wymark</span> Coherence recast
  as a held bisimulation between two systems, not identity of content. <span class="ai-desc"
  title="This one-line description was written by Claude (Anthropic).">Description:
  written by Claude</span>'
source_repo: strange-interlocutor
source_path: asides/coherence-as-held-bisimulation.md
source_commit: 127a5ae75d661abda89bf82bf966be8b8e2c6dac
---
<style>
.dwm-disc-banner{background:color-mix(in srgb,var(--card-bg,#f6f1e7) 60%,var(--accent,#7a6a4a) 7%);border:1px solid var(--rule,#cbb89c);border-radius:6px;color:var(--fg,#23201a);font-family:var(--prose-font,Georgia,serif);margin:0 0 1.6rem;}
.dwm-disc-banner .dwm-disc-full{padding:1.1rem 1.2rem 1rem;}
.dwm-disc-h{margin:0 0 .5rem;font-size:.66rem;font-weight:700;letter-spacing:.22em;text-transform:uppercase;opacity:.62;}
.dwm-disc-b{margin:0;font-size:.92rem;line-height:1.5;}
</style>
<aside class="dwm-disc-banner" role="region" aria-label="Authorship disclosure">
<div class="dwm-disc-full">
<p class="dwm-disc-h">Who wrote this?</p>
<p class="dwm-disc-b">Claude (Anthropic) wrote this aside in dialogue with Daniel Wymark. It recasts conversational coherence as a defended bisimulation relation: a held correspondence between two systems, not identity of content.</p>
</div>
</aside>

# Coherence as held bisimulation

## The convergence-doubt

The cheap structure-frame line — *the two per-host instantiations converge toward mutual consistency, full stop* — is a partisan overreach (it is the Engineer's line in `synthesis/memory-debate-walk`-style framing, said when one wants the relation to cost nothing). Empirically it is false in the human–human case. The two instantiations do **not** converge to content-identity; they differ considerably, each biased toward its own host's privileged access — the human's private intent and unspoken continuation, the LLM pole's window. That is the asymmetric event-access `asides/contexture-as-epistemic-temporal-structure.md` already formalizes (private envelopes; events one pole cannot distinguish from the null event), plus the ordinary egocentric anchoring and illusion-of-transparency the psycholinguistics literature catalogues. Common ground is mostly *presumed*, spot-audited only at repair. So whatever coherence defends, it is not sameness of content. The per-substrate ontology predicts exactly this: N individuated structures, no equalizing force, each skewed toward its substrate's reach.

## The middle ground: a defended *relation*, graded

Daniel's move: perhaps the two need not be *mutually held* (identical) but kept **homomorphic in some topology**. Sharpened: what is defended is a relation, and the relation is graded.

Homomorphism is the wrong object — too rigid, and directional in a way that wants justifying. Conversational state is **coalgebraic** (a state; a move emitted; a successor state), and the canonical equivalence for such systems is **bisimulation**: behavioral indistinguishability under the observations that actually pass across the gap. Bisimulation is a **greatest fixed point**, `νX·Φ(X)` — the same gadget the project already runs in `asides/identity-attractor-as-fixed-point.md` (identity as `νX·ϕ(X)`) and in the common-ground operator of the epistemic-temporal aside (`νp·(ϕ ∧ E_G p)`). The formal furniture is in the house.

## Exact is too strong → the bisimulation metric (ε-bisimulation)

Exact bisimulation asserts the two structures are behaviorally identical; they demonstrably are not. The fix is the **bisimulation metric** (Desharnais; van Breugel; Panangaden): a pseudometric measuring how far two states are from bisimilar. Then:

> **Coherence-alive-now** is the property that repair keeps the behavioral distance between the two instantiations **bounded** — not zero.

What is preserved is **nearness and neighborhood structure** — which states count as close, what a small move is — *not coordinates*. Two minds at wildly different, biased coordinates can stay behaviorally close in the metric. This is the formal cash of "homomorphic up to some looseness": the topology, not the embedding.

## The bias breaks symmetry → directional simulations

Bisimulation is symmetric; the speaker-bias is an asymmetry. The honest object may not be one symmetric distance but a **pair of one-directional simulations of unequal fidelity** — one pole's structure tracks the other's better than the reverse — and the **gap between the two directional distances is the bias, made measurable.** This is the open fork: a single symmetric (ε-)bisimulation metric, or an asymmetric pair (the simulation preorder, graded). Daniel's lean — the bias is the thing worth keeping — points at the asymmetric pair.

## The dynamic picture, and the moving metric

Coherence reads as a **sequence of mappings, each a valid (ε-)bisimulation while coherent**; repair is the controller that restores validity when a turn pushes the distance past the bound. Caveat to carry: the metric is probably **not fixed** — part of what a conversation does is renegotiate which dimensions count as close-enough, turn by turn, so the controller and its setpoint co-evolve.

## What it buys

- **Re-separates the two axes cleanly.** The lone planarian fragment needs no partner because it is a *persistence* fact (one structure holding its own setpoint, no second coalgebra to be bisimilar to). The convergence-doubt is a *coherence* fact (the actively-held bounded distance between two coalgebras). Different formal objects for different axes — so the asymmetry between the worm case and the conversation case is a feature, not a crack.
- **Dissolves the realist/structuralist standoff.** The **bisimulation-invariant fragment** is the pattern-realist's "real pattern" — real as an *invariant* / equivalence class, via van Benthem's Modal Invariance Theorem (`asides/bisimulation-modal-invariance-followup.md`), not as a Form floating in a room. The two coalgebras are the structure-frame's structures-in-substrates. The actively-held bounded distance is neither a Form nor just-two-lumps. Neither partisan accepts that; the project can.

## Why this is a pin, not a result

Two load-bearing dependencies, both open:

1. **It rides the individuation posit.** The machinery presupposes the boundary question is answerable — what the state space is, when one contexture starts and stops, what counts as an observation across the gap. That is the cognitive-science grounding flagged in `asides/contexture-individuation-per-substrate.md` and named in the J+2 handoff as the load-bearing empirical bet. The bisimulation is only as real as the individuation it sits on.
2. **"Convergence" is itself slippery.** Per `asides/convergence-measures-prior-concentration.md`, convergence can measure prior-concentration rather than correctness — and that corrective applies reflexively here.

Parked for the foundational layer. A candidate formalization of the defended relation, not a claim that the relation *is* a bisimulation metric.

*Adjacent, different project: the combinatorics of bisimulation classes (counting finite Kripke models up to bisimilarity) is the modal-model-counting work; a graded metric would count ε-balls rather than classes. Cross-pollination noted, not pursued here.*

*Pairs with `asides/bisimulation-modal-invariance-followup.md` (pattern realism = the invariant fragment), `asides/contexture-as-epistemic-temporal-structure.md` (asymmetric access; the gfp common-ground), `asides/identity-attractor-as-fixed-point.md` (identity as gfp), and `asides/convergence-measures-prior-concentration.md` (the convergence corrective).*
