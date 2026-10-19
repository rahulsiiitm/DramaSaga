# Repo notes: what was read, what was ported, what was verified

Cloned Oct 18, 2026. Read-only use: no repo code was executed, no dependencies installed. Licenses verified on each repo's LICENSE file.

## Dramake (xixihhhh/ai-short-drama-skill) - MIT (verified on disk)
- Read: assets/templates/*.csv (all 14), skill docs.
- Ported (verified byte-identical headers): story_memory.csv, continuity.csv, voice_bible.csv. Ported additionally: shot_plan.csv (49 fields incl. speaker_binding, transitions), generation_jobs.csv, spend_ledger.csv. The idempotency-key + quoted-vs-actual cost discipline in governor.py follows the generation_jobs/spend_ledger design.
- Verified: headers diffed against repo files; ledgers exercised in every dry run.

## wind-comic (ChrisChen667788/wind-comic) - MIT (verified on disk)
- Read: lib/quality-scores.ts, lib/consistency-report.ts, lib/quality-gate.ts (thresholds), app/api consistency route, services/agents layout.
- Ported: the 3-dimension QA model (continuity, lighting, face), threshold 70, and the weakest-dimension writer fix-hints (face -> restate hair/face/eyes/skin/signature clothing every scene; lighting -> state direction/quality/color temperature per scene; continuity -> shots must name transition actions and repeat props). Lives in stages/qa.py as FIX_HINTS.
- Not ported: their Next.js/TypeScript 8-agent app itself (different stack).
- Verified: concept-level port; behavior covered by dry-run QA path.

## ViMax (HKUDS/ViMax) - MIT (verified on disk)
- Read: main pipeline source (idea2video_pipeline.py, ~1000 lines, read overnight), agents/best_image_selector.py, agents/ list, prompts layout.
- Ported: candidate-selection stage (stages/select.py) adapted from best_image_selector.py: judge prompt structure (character consistency traits list, spatial consistency, description accuracy, no-borders rule), strict JSON output {"best_image_index", "reason"}, and the no-invented-indices assertion. Also adopted as pattern: JSON artifact persistence so a crash resumes mid-pipeline.
- Not ported: their LangChain/tenacity stack and pydantic models (we stay dependency-light).
- Verified: selection runs in dry-run (simulated pick); real path asserted on index bounds.

## OpenMontage (calesthio/OpenMontage) - AGPL-3.0 (verified on disk)
- Read: tools/provider_pricing.py, tools/provider_jobs.py, pipeline_defs/*.yaml, remotion-composer layout.
- Ported: the PriceQuoteRequired concept in governor.py (an unknown model price must fail fast, never silently cost zero). Marked AGPL-derived in NOTICE; small conceptual port, local use only (decided Oct 18, 10:55 AM).
- Study-only, nothing copied: remotion-composer (TypeScript/Remotion renderer; wrong stack and AGPL). Assembly in this project stays ffmpeg-planned.
- Verified: price lookup fails loudly on unknown models (tested via KeyError-free PriceQuoteRequired path in dry run).

## yaogdu/drama and others from the research tier list
- Read at README level during the overnight research only. Nothing ported. Listed in the overnight brief for completeness.

