# Clean source release

20 October 2026. Original layout base: the supplied yesterday's commit archive, with its single `DramaSaga-main/` root retained. Current code was recovered from the live restricted Drive source export and merged without deleting base-only source/research. The supplied ZIP does not establish a verified Git commit SHA.

## Scope

Included: original modular production/QA/tests, scripts, notebooks, benchmark research; all current audio-first code, form, provider adapters, writers, execution controls, subtitles, local assembly, soundtrack license gate and season ZIP continuation; six unchanged H3 modules actually taken. `CHANGE_SUMMARY.json` lists exact added/changed/removed paths relative to the previous clean release ZIP (the 10:46 PM file). The original base layout and benchmark research are still preserved. `SOURCE_MANIFEST.json` binds release content hashes and the base archive hash.

Not a full H3 checkout: the earlier source review counted 879 source/documentation/config/prompt files in a source-only extraction. This release includes the six selected modules, their manifest and vendor note, not the other source files, the original repository's media/demo datasets, external services or deployment dependencies. A request for the entire H3 codebase would require a separately scoped source inventory/rights/dependency review, not silently importing everything from its multi-gigabyte archive.

## H3 reuse and rights

Verbatim modules: soundtrack.mjs, tools-film.mjs, render-all.mjs, join.mjs, check-prompt.mjs and comfy_r2v.py, under their supplied relative paths in `vendor/h3-film-reference`. All six match the hashes in that folder's source manifest. Our optional wrapper executes only join.mjs for local assembly; our own Python path remains available. The other modules are reference material, not a complete runnable H3 deployment.

Keep this mixed source release private/restricted. Attribution stays in NOTICE and the vendor folder. No public redistribution or blanket rights clearance is asserted. MiniMax H3 model-weight rights and compute approval are separate; the H3 model entry point refuses. No weights, GPU/Modal/RunPod jobs or vendor agent/service orchestration were run.

## Verification

218 tests passed on the live Drive source download before packaging and are rerun on this clean release and the downloaded ZIP. Provider HTTP is mocked. Own and H3 join local assembly paths use real ffmpeg synthetic-media fixtures; subtitle/name/introduction placements were visually checked. No live text/image/voice/video generation or spend was used for release verification.

Files are screened for credential prefixes and credential/ledger/cache paths. No detected key material, .env, private key, spend ledger, virtual environment, installed dependency, model weight or generated media is included. Static scanning is not a universal secret/malware guarantee. Archived scripts/notebooks are retained as historical source and may install/download/call APIs when explicitly run; they are not executed as part of import.

## Current limits

See AUDIO_FIRST.md for one current status, rather than old appended gap lists. Live route/account/model behavior and pricing, inference quality, emotional voices, lip sync, automatic word alignment, creative continuity and final playback still require scoped real tests. `produce` makes actual previews from accepted local media, not a guaranteed unattended first-time paid film. Archive content and the original benchmark research are preserved as historical material, not current API/pricing promises.

## Evening completion-code revision

Added local ASR exact-word alignment recovery and bounded retranscription; semantic QA evidence/pixel sampling and two-evaluator acceptance; optional installed-local vision-model transport; audio-bound mouth-track correlation screening; production automatic-preparation hook; free licensed Commons audio search/download/attribution; local H3 API-graph compiler, license/weights/free-compute preflight, duplicate-safe submission/history collection; and elementary OBJ prop blockout. No service generation, real model inference, public audio download, weights download, installation, paid compute or keys were used.

Stress checks include all 512 required-check presence combinations (only the complete valid evidence passes), 32 license/host/MIME/restriction combinations (one compatible combination passes), 12 ASR confidence/mismatch combinations, low/unknown/NaN/stale/duplicate evidence and download/runtime/tamper/unknown-job rejection paths. These are explicit finite matrices, NOT proof that every possible input combination or real-world failure has been tested.

The synthetic actual-ffmpeg automatic-preparation/assembly fixture passed and its caption/name/introduction pixels were inspected. Real ASR, vision, face tracking and H3 inference are not installed/validated here. Automatic acceptance refuses without the required capable local engines or evidence. Lip-sync correlation is a screening signal, not a phoneme-quality judge. Full H3 runtime deployment/template/weights and licensing, human 3D reconstruction, hosted deployment and actual final-film quality remain blocked/unverified. No claim that these have been completed is made.

## Portable runtime additions

The `portable/` directory adds pinned official model/source manifests, installation and local execution scripts plus a no-output notebook. No weights, keys, caches or installed environments are bundled. See README for actual model smoke measurements and unverified GPU/platform areas. H3 reference comments are sanitized; source origin remains attributed. The new minimal H3 API graph is adapted from the official Comfy template at the commit in `portable/sources.lock.json`; its license is included separately.
