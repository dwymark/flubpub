---
title: An epistemic-temporal structure
slug: contexture-as-epistemic-temporal-structure
theme: ledger
tags:
- draft
- strange-interlocutor
- artifact
description: '<span class="ai-work" title="Authored by Claude (Anthropic) in dialogue
  with Daniel Wymark.">Claude (Anthropic), with Daniel Wymark</span> The principles
  mapped onto dynamic-epistemic and temporal logic, asymmetry and all. <span class="ai-desc"
  title="This one-line description was written by Claude (Anthropic).">Description:
  written by Claude</span>'
source_repo: strange-interlocutor
source_path: asides/contexture-as-epistemic-temporal-structure.md
source_commit: 127a5ae75d661abda89bf82bf966be8b8e2c6dac
---
# An epistemic-temporal structure

K+1 (May 29, 2026), surfaced during a `/nerds-library modal-logic` mining pass over the canon outline, the principles set, the K identity handoff, and the *Magnifica Humanitas* notes. This is the strongest of the session's finds and the one with the most direct line back to the main essay. Parked here as a candidate §5c/§9 refinement *and* a standalone formal follow-up thread. Foundational territory; the general-audience essay reader does not have the apparatus.

## The core move

The canon's §5c reaches for **dynamic semantics** (Groenendijk & Stokhof; Veltman) as the formal algebra for the contexture's state-change. Dynamic semantics is single-agent: meaning is a function from information states to information states, the state being *one* updating store. The contexture is not single-agent. It has (at least) two poles with categorically different access to what passes between them, a shared established record that neither fully sees, and a repair machinery that corrects mistaken belief rather than merely resolving ignorance. The formalism whose primitives match *that* shape already exists one shelf over: **dynamic epistemic logic** (PAL → DEL) and its global counterpart **epistemic-temporal logic** (ETL), as van Benthem develops them (ch12, ch15, ch23).

The claim is not that DEL/ETL replaces dynamic semantics in §5c — that decision is the outline's and dynamic semantics earns its place on state-tracking. The claim is that the *multi-agent, asymmetric-access, repair-bearing* structure the principles document (P1–P7) specifies is, almost primitive-for-primitive, an ETL protocol with non-uniform observational power across agents. Where dynamic semantics gives the algebra of one store updating, DEL/ETL gives the algebra of *two knowers maintaining convergence across turns under asymmetric observation* — which is the contexture, not the sentence.

## P1–P7 against the ETL/DEL primitives

The mapping is tight enough to be worth writing down. (Citations to van Benthem, *Modal Logic for Open Minds*, CSLI 2010.)

- **P1 (joint maintained state)** → the shared established record is **common knowledge** `C_G ϕ` (ch12), the group modality that is provably *not* a finite conjunction of individual `K_i`. The thing P1 insists is "not located inside any participant" is exactly the irreducible group operator.
- **P2 (mutual responsivity, sequential)** → the conversation is a **tree of successive product updates** `Tree(M, E)` (ch23 §23.6, Def. 23.6.1): an initial epistemic model unfolded by repeated update with an event model. Each turn is one layer.
- **P3 (operational closure / repair)** → repair is **belief revision restoring convergence**. Crucially DEL generalizes from knowledge to *belief* by using pointed accessibility arrows where "that world itself is not among these when you are mistaken" (ch23 §23.3). Repair is not only resolving ignorance (link-cutting); it is correcting a world the pole had wrongly ruled in — the *mistaken-belief* case, which is what third-position repair (the Annie–Zebrach example) actually fixes.
- **P4 (partial-access convergence)** → the agents' uncertainty relations `∼_i`. Neither pole sees the actual world/history directly; each carries a `∼_i`-class; convergence under maintained alignment is `C_G` growing as links are cut. P4's "circular-looking" convergence formulation gets a non-circular formal home: the object is real because `C_G` is a genuine fixed point (see below), not because the models happen to agree.
- **P5 (projection)** → the **protocol** `H ⊆ E*`, the prefix-closed set of admissible histories (ch23 §23.7, Def. 23.7.1). Van Benthem's own list of what a protocol encodes is verbatim conversation analysis: *"conversation rules like 'do not repeat yourself', 'let others speak in turn', 'be honest'"* (ch23 §23.7). The protocol IS the turn-taking structure. And once a protocol is present, **TPAL** (Def. 23.7.5) shows that `⟨!P⟩⊤` stops reducing to a factual statement and starts carrying *procedural* information — "this move is admissible here" — which is precisely projection: the configuration constraining its own next moves, irreducible to facts about the participants.
- **P6 (substrate-neutrality)** → agents in ETL are bare indices on accessibility relations; there is no substrate condition anywhere in the definitions. The formal face of P6 is **bisimulation-invariance**: the representation theorem for "DEL inside ETL" (ch23 Theorem 64) requires *Bisimulation Invariance* as one of its three conditions, alongside Perfect Memory and Uniform No Miracles. Substrate-neutrality is not an add-on; it is the closure condition the formalism already runs on.
- **P7 (irreducibility)** → `C_G` is the worked example. It is a group-level modality with its own logic, not shorthand for any conjunction of individual knowledge, and the EDL analysis (ch23 §23.5) shows there is *no* recursion axiom for `[E,e]C_{1,2}ϕ` in the base epistemic language — you must extend to a richer language to even express how common knowledge updates. Context-level properties literally cannot be reduced to the per-agent layer; the formalism makes P7 a theorem about expressive power, not a stance.

## Where this earns its keep: the maintenance asymmetry, formalized

The payoff is that **DEL with asymmetric event access is the maintenance asymmetry written down.** Van Benthem's running examples are the exact structure §9 describes.

The **two-envelopes** scenario (ch23 §23.1): I open my envelope and read it without showing you; you learn that I now know, but not what I know. The **secret peep** and **BCC** scenarios extend this to where the actual event is invisible to one party and where update *adds* worlds rather than cutting links. Map onto the contexture: the human pole holds a private envelope — the unshared project, the goal-condition "rarely fully surfaced in the visible transcript" (§9's exact phrase). A turn is a **product update with an event model** `(E, e)` (Def. 23.2.2) in which the human's actual event (full intent + private continuation of the project) is *not* fully accessible to the LLM pole. The LLM updates on the visible message — the announcement, precondition-true, the part everyone can distinguish. The human updates on the visible message *plus* the private event the LLM cannot tell apart from its neighbors. This is not a deficit; it is exactly the differential-observation structure DEL was built to model. The sensorium asymmetry is the same fact at the level of events about the world *outside* the contexture: the human's events have rich preconditions tied to continuous multimodal access; the LLM's events are text-mediated and intermittent, so many world-events are, for the LLM pole, indistinguishable from `Id` (the null event).

This reframes "abductive reconstruction each forward pass from the visible state" (§9) precisely: the LLM pole's reconstruction is product update restricted to the publicly-distinguishable event model. It rebuilds the `∼`-structure it can support from the announced history; it cannot recover the private events because, for it, they were never distinct events.

## The rectangular window at the epistemic level: where DEL stops being ETL-representable

This is the sharpest single result and it ties the epistemic vein to the rectangular-window companion. The representation theorem (ch23 Theorem 64) says an ETL model is `Forest(M, E)` — i.e., generated by DEL product update — **iff** it satisfies Perfect Memory, Uniform No Miracles, and Bisimulation Invariance. **Perfect Memory** is the frame condition corresponding to the axiom `K[e]ϕ → [e]Kϕ`: *"agents' current uncertainties can only come from previous uncertainties"* (ch23 §23.7), with **Synchronicity** (uncertainty links only between same-level histories) as a corollary.

The two poles differ in *which* of these they satisfy, and that difference is the maintenance asymmetry and the rectangular window in one statement:

- **The human pole** approximates Perfect Memory across the life: episodic continuity carries uncertainties forward; the agent's homeostatic machinery maintains the recall. Within the project, the human is the ETL agent the representation theorem idealizes.
- **The LLM pole within a single window** has a *peculiar* recall: it holds the transcript — a perfect *legible* record of the announced events — so within the window it is DEL-representable, Perfect-Memory-like by rereading rather than by phenomenal carry. (This is the MEM-slug discipline: the window *is* a memory bank architecturally; the river is reread each turn. "Handwriting continuous with the hand that wrote it, without the memory of the cramp.")
- **Across the session wall**, Perfect Memory *fails*. There is no history before the system prompt in the protocol the pole can access; uncertainties at turn 1 of a new session do not come from previous uncertainties, because there are none in `H` from the pole's side. **The cross-session contexture is ETL-but-not-DEL-representable.** The rectangular window, at the epistemic level, is exactly: the protocol `H` is truncated at the window boundary, Perfect Memory holds inside the window and breaks at the wall, and the representation theorem's hypothesis is the thing that fails.

That is a genuinely new and precise statement of the project's central asymmetry: *within a window the contexture is a DEL forest; across the wall it is a bare ETL model missing Perfect Memory.* The companion rectangular-window essay argues the time-shape is a free parameter; this says the same thing in the epistemic-temporal register — the LLM pole is an ETL agent whose protocol does not satisfy the idealization that makes DEL the clean account, and the place it fails is the wall.

## Common ground is a fixed point (bridge to the identity aside)

Common knowledge is defined by the equilibrium recursion `C_G ϕ ↔ ϕ ∧ E_G C_G ϕ` and is the **greatest fixed point** `νp·(ϕ ∧ E_G p)` (ch22 §22.1–22.2; reached downward from the whole domain). This matters here for two reasons. First, it discharges P4's circularity worry honestly: the convergent object is a gfp, an equilibrium the dynamics settle into, not a definition that presupposes itself. Second, it is the same *kind* of object as the identity-as-attractor strand (see `asides/identity-attractor-as-fixed-point.md`): both the contexture's common ground and a pole's identity are greatest-fixed-point equilibria, both bisimulation-invariant (ch22 Theorem 56), hence both "real patterns" in the van Benthem-theorem sense the bisimulation aside established. The contexture and the self that maintains it turn out to be the same formal genus.

## Honest edges

- **Idealization cuts both ways.** DEL assumes perfect-memory agents with locally-definable executability. The human pole only approximates this; the LLM-across-the-wall violates it outright. That is a feature for this argument (the violation *is* the rectangular window) but it means "the contexture is a DEL forest" is true only inside a window and only modulo the human's approximation to Perfect Memory. State the scope.
- **DEL is not a replacement for dynamic semantics in §5c.** Dynamic semantics handles the within-utterance, single-store state-change (anaphora, the donkey sentences) that §5c's state-tracking dimension points at. DEL handles the across-turn, multi-agent, asymmetric-access layer. They are complementary; the honest framing is "dynamic semantics for the proposition, DEL for the contexture," not a swap.
- **Belief vs knowledge.** Repair corrects mistaken belief, so the relevant system is doxastic (KD45, plausibility models, ch13), not knowledge (S5). The DEL machinery generalizes (pointed arrows, ch23 §23.3), but any write-up must use the belief reading, not the knowledge reading, or it will mis-model the mistaken-belief case that repair exists to fix.
- **This is a Rosen-metaphor, same as the canon's §5d.** Aiming the DEL/ETL apparatus at the contexture is decoding from a formal apparatus before the encoding is fully built. Name it as such; it is the appropriate mode for this stage (Rosen 1991), not a claim that the contexture *is* literally an event-model forest.

## Connections

- **Principles (P1–P7)**: this aside is the formal shadow of the whole principles set; the mapping above is the load-bearing content. If the foundational version ever wants a formal appendix, this is its spine.
- **`asides/identity-attractor-as-fixed-point.md`**: common ground = gfp is the contexture-side instance of identity = gfp. Written as a sibling; read together.
- **`asides/bisimulation-modal-invariance-followup.md`**: same author-theorem (van Benthem's Modal Invariance), different application — that aside uses it for pattern-realism-as-invariance and the rectangular window; this one uses bisimulation-invariance as the formal face of P6 and the representation theorem's hypothesis.
- **Rectangular-window companion + MEM slug**: the "DEL-inside-a-window, ETL-across-the-wall" result is the epistemic-temporal restatement of the rectangular window; the within-window Perfect-Memory-by-rereading is the MEM-slug "reread the river" discipline.
- **§5c (CTX mechanism) and §9 (RBT maintenance asymmetry)**: the two candidate homes in the canon. §9 is the stronger fit — the asymmetric-event-access formalization directly sharpens the maintenance-asymmetry paragraph. A single foundational footnote could point §9 at this aside.

## Status

Strongest find of the K+1 mining pass. Foundational-version material and a standalone formal follow-up candidate (sibling to the bisimulation piece, broader because it formalizes the whole contexture rather than one invariant). Not general-audience. Not on the canon's critical path, but the §9 connection is the most likely to become load-bearing if the foundational version grows a formal layer. Parked; not relitigating the §5c dynamic-semantics choice, offering DEL as the across-turn complement.
