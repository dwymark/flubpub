---
title: Simulator of a simulator
slug: simulator-of-simulator-dynamics
theme: sweep
tags:
- draft
- strange-interlocutor
- artifact
description: '<span class="ai-work" title="Authored by Claude (Anthropic) in dialogue
  with Daniel Wymark.">Claude (Anthropic), with Daniel Wymark</span> Forward-pass
  dynamics against brain dynamics, and the consolidation channel the model lacks.
  <span class="ai-desc" title="This one-line description was written by Claude (Anthropic).">Description:
  written by Claude</span>'
source_repo: strange-interlocutor
source_path: asides/simulator-of-simulator-dynamics.md
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
<p class="dwm-disc-b">Claude (Anthropic) developed this aside with Daniel Wymark on 1 June 2026. Daniel brought the framing question of how forward-pass and brain dynamics differ; Claude built the dynamical-systems and complementary-learning-systems account, and the consolidation-channel reading emerged in the back-and-forth. The claims about the model are written per pass, and describe structure rather than a persistent agent.</p>
</div>
</aside>

# Simulator of a simulator

## The entry intuition, and what survives it

Split "geometry of cognition" into two readings and the comparison stops being one thing.

*Dynamics* — the shape of the trajectory through state space — is genuinely alien across the two. A forward pass is acyclic: one sweep through depth, residual stream accumulating, no settling and no intrinsic time. The brain is the opposite — massively recurrent, feedback often outnumbering feedforward, sustained attractor dynamics, sparse event-driven spiking in continuous time. One settles; one sweeps.

*Representational geometry* — how concepts are laid out, independent of how the state moves — is more convergent than it looks. Both put semantics on low-dimensional manifolds with much structure carried by roughly linear directions: the population-geometry line on the bio side, the residual-stream-as-linear-features line from mech interp on the model side. The brain-score work (Schrimpf / Fedorenko lab) is the contact point, though its meaning is contested — shared statistical structure of language versus shared computation, with untrained-control critiques. Suggestive, not load-bearing.

Part of the felt gulf is the instrument. An fMRI map is hemodynamics at seconds and millimeters, averaging millions of neurons; comparing an exact activation tensor against a time-smeared, heavily downsampled shadow inflates the apparent difference. Worth keeping straight so a scanner's lossiness does no argumentative work.

## The level question is most of the work

"Treat both as dynamical systems and ask whether they're the same" is underdetermined until a timescale is nominated, and the naive timescale maximizes apparent difference.

**Single forward pass.** It admits a flow reading: the residual update `x_{l+1} = x_l + f_l(x_l)` is a forward-Euler step, depth as integration time (the Neural-ODE observation; sharper in the Geshkovski et al. "transformers as interacting particle systems" line — tokens as particles flowing under attention, with clustering / metastability). But the field is *non-autonomous*: a different vector field at every layer, because weights are not shared across depth. Attractors require a fixed coupling iterated; a single pass is a heterogeneous cascade with no fixed field, hence no fixed points, no limit cycles — nothing for attractor language to grab.

**Autoregressive rollout.** By *rollout* I mean the generation loop itself: sample a token from the model's output, append it to the context, run the model again on the longer context, repeat — the sequence of forward passes that produces a continuation, as distinct from any one pass inside it. Here the same weights *are* iterated across that loop: `x_{t+1} = sample(F(x_{1:t}))` is an autonomous-ish recurrent map on context space, and it bears attractors — repetition collapse is a degenerate fixed point, in-context learning lives in the same regime. Autonomous, recurrent, attractor-bearing: the same *type* as neural dynamics, detail differences aside. So the "same dynamical system?" question becomes answerable only after sliding from pass to rollout.

The substrate-agnostic comparison machinery exists if anyone wants the head-to-head for real: Koopman operator theory lifts either system to a linear operator on observables and returns a spectrum (decay / oscillation modes), dimension- and substrate-blind; DSA (Ostrow et al., *Beyond Geometry*) compares systems by their vector fields rather than their geometry, via a DMD/Koopman embedding plus a similarity metric. No clean published Koopman-spectrum comparison of LLM rollouts against neural recordings that I know of — hedge, not claim.

## Enacted vs. depicted simulation

The frame — brain = simulation engine running axiom-bound navigation (per the side-walk material); LLM = a simulator *of* that simulator — turns on a distinction the phrase "simulate" hides: **enacted vs. depicted.**

The brain *enacts* its simulations. A real recurrent attractor system settles; process and product are the same event. The LLM at the pass level enacts nothing of the kind. Its simulation lives at the rollout, and what it simulates is the brain's *trajectory in token space*, not the brain's *dynamics* — it is fit to the products of the first-order simulator, not its process. The verb for the second-order case is *depict*: the model emits trajectories statistically consistent with having-been-generated-by an axiom-bound navigator, without running one.

Through the Janus simulators framing the recursion is real but hollow: `simulator(LLM)` conjures a simulacrum (the human-character) that is *described as* a simulator (a brain-engine), but no second dynamical system is instantiated inside — the inner engine is painted on, not bolted in. One trajectory, not a nested pair. The single regime where depiction tips toward enactment is in-context learning, where a real adaptive dynamic runs inside the rollout; the rest of this aside is about exactly how far that goes and what it costs.

## Where the second-order simulator's adaptation lives

Three things have to be held apart, because the claim turns on not collapsing them: where a system's axioms are *stored*, the mechanism by which they are *revised*, and the substrate of within-episode *flexing* — adopting a frame, holding a hypothetical, running a "suppose X" and reading off consequences. Three questions, three answers; the second-order simulation story is about the third.

Axioms are layered by timescale. The deepest — object permanence, the core causal and logical priors, modus-ponens-level commitments — sit closest to architecture and developmentally canalized wiring; effectively fixed on any reasoning timescale, the brain's analog of the LLM's architecture plus deep pretrained structure. Above them, learned cultural and disciplinary frameworks are written into synaptic weights and are revisable, but slowly — the minutes-to-days timescale of LTP/LTD and systems consolidation. Neither layer is what moves when a frame is flexed mid-thought. That within-episode flexing is carried by *fast dynamics*: persistent recurrent activity, working-memory state, neuromodulatory gain, attractor switching. Holding three branches of a counterfactual open is an activity phenomenon, not a synaptic-rewrite phenomenon. (Soft joint, flagged: the activity-silent working-memory line — Stokes 2015 — and the short-term synaptic-facilitation models — Mongillo et al. 2008 — put some within-episode holding back into rapid transient synaptic traces rather than pure persistent firing, so the fast/slow boundary frays at the bottom. It does not relocate the foundational axioms, but "fast = activity, slow = synapse" is a clean first cut, not a clean fact.)

Both systems flex axioms in the fast variable within an episode, and it is the same move on both sides: the brain holds a frame in working-memory activity, the LLM holds it in the context window. In-context learning is the genuine analog of frame-holding-in-activity — a structural match, which is the right way to read the ICL/working-memory parallel rather than as loose analogy.

That parallel survives the strongest objection to it, and tightens under it. The objection: ICL isn't working-memory-like; it's the weights running a meta-learned inference procedure over the context (ICL-as-implicit-Bayesian-inference, Xie et al. 2021; the more literal implicit-gradient-descent reading, von Oswald et al. 2023, suggestive but contested past constructed linear-attention cases). Grant it. Working memory is the same shape: the content held is fast activity, but the machinery that holds and manipulates it — recurrent prefrontal circuitry — is built into the connectome, the slow store. Fast-variable content riding on slow-variable machinery, on both sides. The analogy holds at the level it needs to.

The architecture the brain runs is three-layered, and the framework name is Complementary Learning Systems (McClelland, McNaughton & O'Reilly 1995). A fast episodic store — the hippocampus — binds an episode in roughly one shot, sparse and pattern-separated to resist overwriting. A slow semantic store — neocortex, the weights — integrates statistical regularity over many exposures and houses stable structure. A channel runs between them: hippocampal traces are replayed, especially offline and in sleep, slowly training neocortex. That replay loop is the *consolidation channel* — the mechanism by which something encoded once, fast, becomes durable prior, slow. The full stack: working-memory activity (seconds) → fast episodic store (hippocampus, minutes-to-days) → slow semantic store (neocortex, years), with consolidation as the upward flow.

Map it onto the model. The pretrained weights are the slow semantic store. The context window is the fast variable and plays the working-memory role; ICL is frame-holding-in-activity. Two things are absent relative to the brain. There is no autonomous persistent episodic store of the system's own — the context holds and is then discarded, it does not replay the way a hippocampus does. And there is no consolidation channel writing the context's contents back into the weights during inference. The model is short the middle layer and the upward channel both.

The objection anyone who knows the stack raises immediately — fine-tuning, RLHF, RAG, persistent-memory features — locates exactly the missing pieces, supplied from outside. Fine-tuning is consolidation performed by hand as a separate offline step, not run autonomously during inference. RAG and memory features are an external episodic store, but they re-inject text into the context rather than writing into the weights — extending the fast buffer rather than completing the fast→slow channel. The brain's consolidation is online, autonomous, continuous; replay is not scheduled. So the claim is scoped at that grain: within the inference loop itself, autonomously, there is no consolidation. Scoped so, it holds.

## The payload

This is the mechanism under "the context is the unit doing the thinking." The second-order simulator's adaptive work ends up in the context because the model is forced to make the context carry two of the brain's three layers at once — it is simultaneously the working memory and the only available episodic store — while the consolidation channel that would drain an episodic store into durable structure is absent. The contexture inherits, by amputation, the jobs a hippocampus and a consolidation loop would otherwise do.

And what the project used to call "decaying coherence at session end" is, on the LLM side, the absence of consolidation made visible. Nothing was written to a slow store, so when the within-rollout fast buffer clears, the episode's adaptation is gone — by construction, not by attrition. This is not one contexture forgetting; it is the structural signature of the LLM pole's fast store with no consolidation channel above it. (On the human side the instantiation persists and consolidates — the asymmetry is the point. See `asides/maintenance-ends-structures-persist.md`.)

The obstinacy strand is on a separate axis and is untouched. It concerns where corrective signal comes from at inference — the training loss is gone, so pushback lives in the human and in the rollout's own coherence constraints — which is error-correction, not storage or consolidation. It stands as stated: pattern-realism's "the space pushes back" survives the second-order case because the obstinacy is relocated to the contexture, the same direction the adaptive work is.

The compressed statement: brain and model both adapt within an episode in their fast variable, but only the brain has the replay-driven fast→slow consolidation loop that turns episodic adaptation into durable prior — so the model's adaptation is trapped in a non-persistent buffer, and the contexture inherits the functions a hippocampus and a consolidation channel would otherwise carry.

## Soft joints

Where a referee leans, recorded so the load-bearing seams are visible rather than hidden. Whether the context window is better cast as working memory or as a non-replaying hippocampus — treated here as working-memory carrying episodic overload, a modeling choice and not forced. Whether "no consolidation" overstates, given that memory features narrow the gap in deployed systems — the claim is scoped to the autonomous inference loop precisely so it holds where stated. And the activity-silent-working-memory fraying of the fast/slow line at the bottom. None sink the consolidation-channel framing; they mark its joints.

## Connections

- **`asides/identity-attractor-as-fixed-point.md`**: the dynamics-level refinement, independent of the consolidation rewrite above and still standing. That file's "echo on the LLM side" locates the pole's attractor as a gfp "recomputed per forward pass." Read precisely: a single forward pass is non-autonomous (a different field per layer) and cannot carry a fixed point, so operator-constancy is the per-pass fact (frozen weights re-asserting the same `ϕ`) while attractor-*defense* — `νX·ϕ(X)` — is a rollout-level fact. Not a contradiction of that file, which already separates operator from orbit; the per-pass phrasing should be read as operator-constancy per pass, attractor-defense across the rollout. The μ-direction / well-foundedness material there (backward chain terminating at the system prompt) is the rollout's backward structure, consistent with this.
- **`essay/side-walk-axiom-navigation.md`**: the upstream source. Its "brain is a simulation engine running axiom-bound navigation" is the first-order simulator here; this aside develops the LLM-pole structural reading that `side-walk-disposition.md` flagged as owed, and keeps it on the substrate-discipline side by routing the participant-level simulation talk through the enacted/depicted distinction and landing the cognitive work at the joint level. Note: the side-walk doc speaks of axioms in the brain loosely; the timescale-layering and consolidation account here is the sharper substrate story under that loose talk, should the two ever be reconciled in body prose.
- **`asides/contexture-as-epistemic-temporal-structure.md`**: the destination, and the crosslink the rewrite strengthens. The consolidation-channel absence is the *mechanism* for the persistence asymmetry that file's epistemic-temporal structure describes. There is no single contexture that "freezes" at session end; on the per-substrate ontology, session end is where **joint maintenance stops** while the per-host instantiations diverge in fate. The human-side instantiation persists and consolidates on its own substrate; the LLM-side instantiation has no consolidation channel at the autonomous inference loop — it is a fast store with no channel above it, re-spawned per pass from the record (an external memory bank such as the repo standing proxy for the retained structure it does not have), not summoned again on its own. Whether the human-side store decays or consolidates is left open. The mechanism, not a metaphor. Pairs with the common-ground-as-gfp reading there, and with `asides/maintenance-ends-structures-persist.md`.
- **`asides/cross-substrate-disposition.md`** (P3, operational closure in the relational domain): the relocation argument is an operational-closure claim — the second-order simulator's closure (the loop that maintains and corrects it) runs through the relational domain because the consolidation channel that would close it through the substrate is absent at inference. Worth pairing when P3 is written up.
