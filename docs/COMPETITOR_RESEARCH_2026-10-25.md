# AI story-to-film research and architecture decision

**Date:** 25 October 2026 (Asia/Kolkata)

**Status:** Proposed; research complete, rendering comparison not run

**Decision owner:** Rahul

## Recommendation

Keep DramaSaga's audio-first timing, assembly, evidence and spend controls. Add a staged story-development process, a persistent continuity record, a storyboard preview and a renderer capability contract. Use ViMax as the closest Python implementation reference, Jellyfish for asset/readiness design, and VideoClaw/Toonflow for continuity review. Evaluate an isolated ViMax baseline before considering a wholesale migration.

For an immediately usable external workspace, trial LTX Studio against the same scene. For building our product, adopt the production methods below rather than assuming that any competitor's one-prompt demo guarantees a good season.

This is an engineering recommendation from documentation and source inspection, not a measured ranking of output quality.

## Scope and evidence

Reviewed official product documentation, public repositories, selected implementation files, research papers and the local DramaSaga source. The comparison covers six commercial workspaces, fourteen public repositories, and two additional research methods. It is a focused landscape review, not an exhaustive census of every competitor.

Evidence levels:

- **Implementation inspected:** selected executable code, models or prompts examined; no inference run.
- **Documentation inspected:** official capabilities reviewed; implementation and output quality unverified.
- **Research:** methods reported by authors; not treated as a deployable product.

No paid generation, account signup, model download, installation or competitor execution occurred. No side-by-side video benchmark was performed. Prices and marketing quality claims are not ranking evidence. Public source availability does not establish a model's license, compute affordability or API access.

## Commercial workspaces

| Product | Documented workflow worth learning | Assessment for this project |
|---|---|---|
| [LTX Studio](https://ltx.io/studio/platform/ai-movie-maker) | Script-to-storyboard, reusable Elements, shot revision and timeline editing | Best initial external workflow reference for our requirements; trial candidate, not a verified quality winner |
| [Google Flow](https://support.google.com/flow/answer/16935718?hl=en) | Save frames as references, sequence/trim clips, preview a complete scene | Learn selective frame reuse and scene-level editing; consumer UI capabilities do not establish backend API parity |
| [Runway](https://help.runwayml.com/hc/en-us/articles/41748090660499-Creating-Multi-Character-Dialogues-with-Act-Two) | Record dialogue/performance first, prepare each character's performance, combine with generated visuals | Strong reference for an optional actor-driven route; its documented Act-Two conversation workflow works around single-character input rather than guaranteeing arbitrary multi-person generation |
| [Luma Dream Machine](https://lumalabs.ai/learning-hub/ray3-modify-user-guide) | Source performance video, character reference and keyframe-guided modification | Useful alternative for difficult acting/action; adds recording and compositing work. [Public Modify API documentation](https://docs.lumalabs.ai/reference/modifyvideo) lists different model support from the consumer Ray3 guide, so verify the intended route |
| [Higgsfield Cinema Studio](https://higgsfield.ai/creator-hub/help-center/tools/how-do-i-use-cinema-studio) | Reusable Elements, camera direction, reference assets and native audiovisual generation | Cinematography/workspace reference; version and API support need an actual account-level check |
| [Katalist](https://www.katalist.ai/) | Script import, character reuse, storyboard and video workflow | Storyboard UX reference; its older [storytelling page](https://www.katalist.ai/storytelling) still labels some video features forthcoming, so treat conflicting pages cautiously |

These are documented workflows and vendor claims, not independently verified continuity or acting scores.

## Public repositories and research implementations

License labels below describe the inspected source/version, not bundled models or every dependency. Pin and retain notices before importing code.

| Project | Evidence and useful mechanism | Adoption decision |
|---|---|---|
| [ViMax](https://github.com/HKUDS/ViMax) | Implementation inspected; separate story/script stages, per-shot reference selection, candidate images; MIT | Closest Python baseline. Study relevant modules; compare independently before migration |
| [Jellyfish](https://github.com/Forget-C/Jellyfish) | Implementation inspected; reusable entities, explicit shot preparation, action beats; Apache-2.0 | Best reference here for production data/readiness. Its named consistency checker is narrowly about character confusion, not full continuity |
| [VideoClaw](https://github.com/HITsz-TMG/VideoClaw) | Implementation prompts inspected; timed script segmentation, spatial continuity repair, editable continuation; MIT | Adapt the boundary/state-checking method; validate actual generated media separately |
| [Toonflow](https://github.com/HBAI-Ltd/Toonflow-app) | Continuity/reviewer/director prompts inspected; extensible canvas, model integrations; current LICENSE is MIT | Strong visual-workspace and bounded review reference; not a drop-in replacement for our Python compiler |
| [Story Claw](https://github.com/ZC89757/story-claw) | Documentation inspected; stage-specific references, persistent voices, resumable stages; MIT | Useful asset-version idea. README says clips can be accepted after failed rerolls exhaust the limit; do not adopt that acceptance policy |
| [Huobao Drama](https://github.com/chatfire-AI/huobao-drama) | Documentation and LICENSE inspected; script rewrite, extraction, storyboard, prompt generation; CC BY-NC-SA 4.0 | Workflow reference; exclude from a permissive commercial-code shortlist without separate permission |
| [waoowaoo](https://github.com/waooAI/waoowaoo) | Documentation and LICENSE inspected; reference canvas, model-aware modes, versioned revisions; current LICENSE is Elastic-2.0 | Source-available comparison, not a permissive hosted-product base. Current preview says music/voiceover controls are absent |
| [MovieAgent](https://github.com/showlab/MovieAgent) | Research implementation documentation inspected; hierarchical scene/camera planning and character bank | Architecture reference; specialized image/video stack, not an immediate product replacement; reuse license not established in this review |
| [FilmAgent](https://filmagent.github.io/) | Research project inspected; crew roles and filmmaking inside a constructed Unity 3D environment | Consider only for a future controlled-3D route; different asset and rendering model from uploaded-photo drama |
| [OpenFilm](https://github.com/openfilm/openfilm) | Documentation inspected; HTML-based tracks, editable composition and deterministic rendering; MIT | Useful editor/compositor reference, especially overlays; does not by itself solve photoreal acting or identity |
| [Dramake](https://github.com/xixihhhh/ai-short-drama-skill) | Documentation inspected; production workflow skill; MIT | Existing local NOTICE already credits ledger/governor influence. More workflow instructions alone will not fix visual storytelling |
| [wind-comic](https://github.com/ChrisChen667788/wind-comic) | Documentation inspected; provider-independent short-drama pipeline; MIT | Existing local NOTICE credits QA adaptation; compare actual quality evidence rather than importing another score system |
| [OpenMontage](https://github.com/calesthio/OpenMontage) | Documentation inspected; broad agentic production tools; AGPL-3.0 | Broad reference. Local NOTICE already flags derived governor material; preserve that provenance and address reuse before product distribution |
| [SkyReels-V2](https://github.com/SkyworkAI/SkyReels-V2) | Inference documentation inspected; diffusion-forcing continuation with overlapping history | Long-duration generation experiment, not a story engine. Several listed variants remain forthcoming; no integration selected |

A [curated project index](https://github.com/PAMPAS-Lab/awesome-ai-short-drama) helped discovery. It is not authoritative for licenses: the inspected Toonflow LICENSE says MIT, and waoowaoo says Elastic-2.0, differing from the index's labels. Repository versions change; do not transfer a conclusion to an older commit without checking it.

## Specific source findings

These are narrow source observations, not claims of full repository audits.

1. **ViMax selects references for the target frame**, including prior scene frames, camera composition and character view, rather than blindly attaching the same portrait set. See [reference_image_selector.py](https://github.com/HKUDS/ViMax/blob/main/agents/reference_image_selector.py). Its [idea pipeline](https://github.com/HKUDS/ViMax/blob/main/pipelines/idea2video_pipeline.py) also copies the front portrait into side/back files when those generations fail. We should preserve honest view metadata and flag missing coverage instead.
2. **VideoClaw checks consequences of movement.** Its [staging review](https://github.com/HITsz-TMG/VideoClaw/blob/main/video-claw/video-claw/backend/prompts/storyboard/staging_continuity_zh.txt) checks positions, facing, furniture relationships and interior/exterior context. Its [segment planner](https://github.com/HITsz-TMG/VideoClaw/blob/main/video-claw/video-claw/backend/prompts/storyboard/segment_plan_zh.txt) preserves ordered script-unit coverage. This is more concrete than asking for generic consistency.
3. **Jellyfish has structured shot records**, entity links and separate [action beat phases](https://github.com/Forget-C/Jellyfish/blob/main/backend/app/services/studio/action_beats.py). However, its [consistency checker](https://github.com/Forget-C/Jellyfish/blob/main/backend/app/chains/agents/consistency_checker_agent.py) targets character identity/action attribution in text. It is not evidence of complete causal or visual continuity checking. Inspected tree: `a9678194ddf2d9be3ccbe78d4287d87d5089e123`.
4. **Toonflow's [continuity knowledge](https://github.com/HBAI-Ltd/Toonflow-app/blob/master/packages/teams/storyboardTeam/knowledge/continuity.md)** tracks clothes, carried objects, injuries, movement endpoints, eyelines and lighting. Its [reviewer](https://github.com/HBAI-Ltd/Toonflow-app/blob/master/packages/teams/storyboardTeam/members/reviewer.md) asks for specific evidence and minimal corrections, and distinguishes text review from inspecting actual media.

VideoClaw's inspected tree was `16c1ce0b553e30eff90ff1274e8a8a63c1d548a3`. Other links use moving branches; resolve immutable commits before implementation reuse. No upstream source was copied into DramaSaga by this research.

## Renderer options: evaluate capabilities, not just duration

| Candidate | Verified documentation | Proposed role / unresolved issue |
|---|---|---|
| [Kling 4.0](https://kling.ai/quickstart/kling-4-model-user-guide) | Official guide lists 3–30s generation, multiple keyframes, references and voice-reference input; video extension is marked coming soon | Hosted candidate for reference-driven shots and connected shot groups. API availability, exact audio control, pricing and our account access remain untested |
| [Seedance 2.0](https://seed.bytedance.com/en/seedance2_0) | Multimodal audio/video reference generation; [BytePlus route documentation](https://docs.byteplus.com/en/docs/ModelArk/seedance-2-0) says direct real-human-face reference uploads are unsupported | Candidate only after checking reference eligibility and actual endpoint. Do not assume uploaded human character photos will work on every route |
| [LTX-2](https://github.com/Lightricks/LTX-2) | Public inference includes audio-conditioned A2Vid, keyframe pipelines and retake; model family uses version-specific/community licenses | Strong self-hosted evaluation candidate on suitable provisioned hardware; actual dialogue and identity quality unmeasured |
| [Wan2.2](https://github.com/Wan-Video/Wan2.2) | Speech-to-video accepts image/audio; Apache-2.0. Official TI2V-5B example specifies at least 24GB VRAM, S2V-14B example at least 80GB | Useful open-model baseline on adequate compute; optimized alternatives may differ. Not a turnkey local-laptop production plan |
| [SkyReels-A2](https://github.com/SkyworkAI/SkyReels-A2) | Multi-element visual conditioning, preview checkpoint and GPU offloading instructions | Secondary research candidate. Do not mistake listed unreleased variants for available deployment choices |

These are a capability shortlist, not a claim that the older named versions are the newest or best available in every family. Product UI features and third-party aggregator endpoints may differ from official APIs. Select exact model/version/route only after the same-scene benchmark and current quotes.

Two relevant research directions are [STAGE](https://arxiv.org/abs/2512.12372), which describes start/end storyboard pairs and a multi-shot memory pack, and [DreamShot](https://arxiv.org/abs/2604.17195), which uses video priors and multi-reference role conditioning for coherent storyboards. Borrow their design insights; this review did not establish a production-ready installation or license for importing their implementations.

## Proposed method for DramaSaga

The following is our proposed design, inferred from the evidence and local failure modes. It has not yet been implemented or benchmarked.

### 1. Separate story development from shot generation

Expand the brief to include premise, central conflict, character goals/relationships, ending constraints, visual style, environment references and intended duration. Preserve supplied story facts as constraints.

Write a compact story bible and causal beat outline first. Draft one episode or scene at a time against that outline and the accepted canon. Review motivation, new information, setup/payoff and repetition with cited script lines; perform a bounded repair only where needed. Use separate role prompts in a controlled pipeline initially; a free-form agent swarm is not required.

Maintain exact facts separately from model-written summaries: who knows what, relationship changes, unresolved promises and event order. Retrieval should fetch the current scene's cast/location/prop records, relevant earlier events and the immediately preceding accepted scene. Add vector search only when exact structured lookup is insufficient.

### 2. Create an explicit scene/cut contract

Before rendering, every shot should identify:

- narrative purpose and source beat/line IDs;
- speaker, listener and offscreen audio;
- location/time and character/wardrobe reference versions;
- character positions, facing, eyelines and screen direction;
- prop owner, hand, orientation and object state;
- starting state, visible action and required ending state;
- camera/framing and the reason for the next cut;
- timing, renderer mode and required capabilities.

Validate ordered line coverage, impossible state jumps and missing references deterministically. Use model review for ambiguous semantics. A continuity checker error must leave the item unresolved, not approve it.

### 3. Keep audio-first for dialogue; add performance options

Build a scene-level performance track so replies, pauses, breaths and reactions have shared timing. Measure accepted audio before setting final cut lengths. Preserve stems where available while retaining one coherent edit timeline.

For speaking faces, use a renderer that actually accepts the locked audio, or an explicit performance/lip-sync stage. Adding arbitrary speech over an unrelated moving mouth is insufficient. For difficult emotional exchanges, optionally use recorded actor performance and a video-modification route.

Native audiovisual generation is a separate mode: if selected, the accepted generated audio becomes the source of truth and captions/timing are rebuilt from it. It cannot silently replace exact scripted dialogue or a locked voice track.

### 4. Prove the story in a cheap preview

Generate shared references, then keyframes with shot-specific reference selection. Prefer individually verifiable reference views; do not label a front view as a profile. Maintain identity separately from wardrobe/injury/prop-state variants.

Assemble a timed storyboard with dialogue before expensive motion rendering. Review whether the viewer can understand the conflict and consequence. A beautiful frame cannot repair an unclear story.

### 5. Support individual shots and small connected sequences

Default to a simple shot with one primary action and clear speaker. Start with roughly 3–8s editorial cuts where suitable; this is a test heuristic, not a hard creative rule.

Where a tested model benefits, group adjacent shots in the same location into a short multi-shot request. Keep the group tied to the same beat/state contract. Longer model duration is useful but does not remove the need for scene planning or editing.

Use previous frames selectively for continuous action. Re-anchor to canonical references at new scenes and changed setups. Neither chaining every last frame nor generating every frame without scene context is a good universal policy.

The provider contract must distinguish a reference image from a fixed first frame, optional end frame, exact audio conditioning, voice reference, multi-shot support and duration constraints. Route unsupported shots to a compatible mode or block them with a clear reason.

### 6. Edit and repair locally

Keep dialogue continuous while cutting to listeners, reactions, inserts or establishing shots when motivated. Put plot-critical phone messages and exact text in deterministic overlays rather than relying on video-model typography. Use room tone, sound bridges and deliberate music transitions.

Track artifact dependencies and content hashes. A changed prop state or accepted shot invalidates the affected downstream references/cuts, not the entire season. Reroll only a diagnosed failure under a bounded budget. Once exhausted, report a rejected shot; never relabel it accepted to finish the batch.

### 7. Measure watchability as well as technical validity

Keep automated checks for media integrity, transcript accuracy, speaker assignment, identity, state and edit coverage. A VLM's self-reported confidence is not calibrated proof of acting or lip sync. Sampled-frame review cannot establish every-frame motion quality.

Use a human playback rubric for motivation, understandable geography, natural exchanges, emotional change and cut motivation. The repo's existing hash-bound evidence and budgets remain useful infrastructure.

## Options and trade-offs

| Option | Quality control | Cost/complexity | Decision |
|---|---|---|---|
| Keep whole-season generation and improve prompts | Limited visibility into failure | Lowest implementation cost; likely reroll waste | Reject as the main solution |
| Replace DramaSaga with an entire competitor | Depends on that implementation | Migration plus provider/UI dependencies; may discard working timing/spend controls | Run an isolated baseline first; no migration yet |
| Incrementally add planning/state/storyboards to audio-first | Explicit and reviewable | Moderate implementation effort; preview reduces expensive waste | Recommended |
| Generate a long continuous video via extension | Helps intra-shot duration | Drift and difficult local repair; narrative still requires planning | Optional renderer feature |
| Full Unity/Blender production | Stronger explicit geometry/state | Requires sets, rigs, animation and substantial new workflow | Defer unless controlled 3D becomes the product goal |

Keep planning, FFmpeg and lightweight checks local. Start heavy video evaluation on an explicitly provisioned compatible backend; local inference needs a measured hardware and memory-capacity check.

## Same-scene evaluation before choosing a winner

Use one original 45–60s two-character scene, one room and one meaningful prop. Include an entrance, a prop handoff, a revelation and a reaction. Keep genre, script, cast references, aspect ratio and total spend ceiling fixed.

Compare three paths:

1. Current DramaSaga baseline.
2. ViMax as an isolated, pinned reference implementation.
3. Proposed scene-state/audio-first pipeline with the shortlisted renderer; test both simple-shot and connected-sequence mode if supported.

An optional LTX Studio cut tests whether buying the workflow meets the need faster. Reuse identical reference bytes and dialogue where supported; record deviations where native-audio or reference policies prevent equivalence. Never describe unequal inputs as a controlled comparison.

Record total spend including rejects, accepted seconds, wall-clock time, manual editing minutes, rerolls, exact transcript/speaker errors, continuity violations and blind viewer preference. Proposed pilot gate: zero critical script/speaker/prop-state errors, no visible identity swap, and an understandable causal sequence in full playback. These are proposed acceptance criteria, not achieved results.

Repeat on at least three different scene types before declaring a general winner: quiet dialogue, movement/prop interaction and a location transition. Prefer cost per accepted second and repair effort to headline cost per generated second.

## Implementation order and local integration points

1. Extend `magicdrama/audiofirst/core.py` brief and writing request, plus `form.py`/`input.html`, without breaking existing briefs. Permit a one-episode pilot through an explicit compatible change; do not require a ten-episode run to test a scene.
2. Extend `writer.py` with outline, scene draft, evidence-based review and bounded repair artifacts. Preserve exact-request spend accounting in cloud writer calls; multiple new calls require real quotes/reservations.
3. Add a continuity contract used by `story.py`, `planning.py` and `images.py`; migrate optional state fields before enforcing them on legacy stories. Reuse existing canon facilities where their contracts fit.
4. Connect measured audio scheduling in `core.py` to the shot contract, preview assembly and provider capability validation. Keep preview evidence distinct from final media acceptance.
5. Adapt `production_run.py` and `live.py` for dependency-aware stage execution and resumable repairs. Preserve existing unknown-submission protection and budget accounting.
6. Reuse `assembly.py`, `dialogue_timing.py`, `alignment.py` and subtitle modules for deterministic editing. Add motivated audio/visual cut support only where current behavior is insufficient.
7. Fix the legacy `series_run_v2.py` continuity exception path before using that route: a failed check currently becomes `ok: True`.
8. Run the scene benchmark, document failures and only then choose a renderer or migration.

Research changed documentation only. It did not repair these source paths, prove film quality, or authorize paid production. The first engineering milestone is a coherent, inspectable one-scene preview and its continuity report.
