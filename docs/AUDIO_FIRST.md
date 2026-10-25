# Audio-first workflow

Current source contract, 20 October 2026. This document replaces historical appended status lists.

## Available commands

```sh
python -m magicdrama.audiofirst.form --out output/my-brief
python audiofirst.py plan --brief brief.json --out writing-request.json
python audiofirst.py run --brief brief.json --story story.json --out output/new-plan
python audiofirst.py run --brief brief.json --local-model INSTALLED_MODEL --out output/local-plan
python audiofirst.py image-plan --brief brief.json --story story.json --image-cap 12 --exposure exposure.json --out images.json
python audiofirst.py produce --package media-package.json --out output/season-preview --backend own
python audiofirst.py produce --package media-package.json --out output/h3-preview --backend h3_join
python audiofirst.py inspect-season season1.zip
python audiofirst.py run --brief season2.json --previous-season season1.zip --story story2.json --out output/next-plan
```

Other CLI commands cover story validation, reference planning, measured line timeline/master, subtitles/burn-in, dialogue timing checks, free-audio license checks, optional review chains and safe ZIP pack/extract. Run `--help` for argument names. Use fresh output directories; do not overwrite accepted media or reset ledgers.

## Input and story

The loopback-only form collects character count (1-50), episodes (1-50), genre multi-select, a single era/setting field up to 1,000 Unicode code points, English language, season target and episode maximum (<=180 seconds). Each character needs an ID, name, description and uploaded PNG/JPEG/WebP or Nano Banana generation prompt. Upload limits: 5 MiB/image, 30 MiB/request. The 25 October update adds decoded-image checks, story goals/relationships, environment references and staged writing; see [STORY_PIPELINE.md](STORY_PIPELINE.md) for the current contract. Image integrity is not image-quality validation.

Story schema: series ID and season matching the brief; each episode has unique ID, title, draft_seconds, setup, turn, cliffhanger, lines and shots. Lines have globally unique IDs, cast speaker or narrator, text and performance direction. Shots cover the ordered lines exactly once and specify location/description, visible characters, camera, action, wardrobe and props. Runtime is estimated until accepted audio is measured. See tests and `writer.py:season_schema()` for examples.

`run` writes the brief, continuation-aware writing request, supplied/generated story, image/voice/soundtrack plans and explicit blocked states. No story means a writing request, not an invented season. `--template-draft` is an opt-in repetitive software scaffold, not a quality creative writer. Automatic planning does not waive paid-use consent or actual quality checks.

## Writers

`writer.py` validates strict model-returned JSON. `local_writer.py` supports only an already-installed loopback Ollama model, with no key, auto-download or cloud fallback. No local Ollama runtime was available during the check; no model weights were downloaded.

`cloud_writer.py` supports NVIDIA `nvidia/nemotron-3-super-120b-a12b` first. A 60-second no-visible-output stall may close its stream and fall back to explicitly approved Claude Sonnet 5. HTTP errors, early empty/malformed/truncated responses and stalls after partial content do not silently trigger paid fallback. A read-only NVIDIA catalog check returned HTTP 200 with the writer listed; inference quota/latency was not tested.

Cloud CLI options: `--cloud-writer-config`, `--writer-approval`, `--writer-ledger`, `--enable-cloud-writing`. No enable flag means refusal. Keys are supplied privately as `SARALYA_NVIDIA_KEY` and `ANTHROPIC_API_KEY`, never inside files/ZIPs. Config pins NVIDIA/Claude model, maximum output tokens, Claude cap <=$2.30/run, current rate-check date, pricing URL and input/output rates. Sonnet 5 base rates checked 20 October: $2/M input, $10/M output; reverify before use. No cache/tools/batch premium options.

Writer approval binds run ID, exact `{body, config}` hash, source approval reference, expiry <=24h, whether fallback is allowed and key identities. Before Claude generation, token-count preflight bounds input plus maximum-output cost. Reserve worst-case spend in the persistent run ledger first. Unknown submissions keep their exposure; no auto-retry. An approval-reference string is an interlock, not authenticated consent. No live writing or Claude request was made in this release.

## Images before video

`images.py` plans shared character/location/prop references before every shot keyframe. Uploaded character images are not regenerated. Missing dependencies fail rather than dropping identity references. Fresh keyframes prevent accidental chaining across location changes. Hash-bound pixel evidence is required before video consumes the reference plan.

Pinned model/route: `nano-banana-2.1`, single image, explicit `1k`, portrait `9:16`; generator `/v1/ai-image-generator`, referenced editor `/v1/ai-image-editor`. Official docs checked 20 October quote 50 credits for one 640px/1k image. Grids of 4/9/16 have different 150-credit total pricing and are excluded; 2k/4k are not quoted here.

Default cap: 12 new images/episode, up to 600 image credits, within (not added to) 3,000 total Magic Hour credits/episode and 30,000/batch. Explicit image-cap changes remain within hard credit caps. Shared assets are charged once at first use. Exposure includes actual/reserved image/video/replacement/unknown jobs; missing exposure is not zero. Pixel receipts bind bytes but cannot prove the inspection occurred or guarantee acting/geometry. These are 2D references, not true reconstructed 3D.

## Tagged dialogue and captions

`voices.py` plans one continuous `eleven_v3` dialogue request per episode, with conservative performance tags and separate exact spoken/submitted character counts. The selected named Clara/Clara Bennett role defaults to Amelia; Oliver/Oliver Reed defaults to Peter Harwood. Other cast get trait profiles and unresolved catalog choices, not inferred genders. Override via `--voices` mapping. Tags do not certify emotion. Catalog access, license and surcharge/model compatibility require a fresh check.

`dialogue_timing.py` checks exact provider text/speaker segments, monotonic times and coverage of the actual PCM16 WAV. It rejects the earlier early-ending provider alignment. Waveform coverage is not word-level sync certification. Automatic recovery is now available through the local-only alignment module described below. Exact word matching, confidence/onset checks still fail closed, never a guessed global shift.

Subtitle text stays exact English, at most two lines, <=25 chars/second with safe margins. Speaker bars and first-appearance introduction bars are separate overlays. Existing line-timeline commands require hash-bound accepted audio evidence. Optional audit review chains are not spend permission.

## Live-capable execution, default off

`live.py` supports approved Magic Hour image/editor/video create, poll, upload and download plus ElevenLabs tagged dialogue. `production_run.py` can execute an exact approved job manifest and then assemble accepted media. No live provider generation was exercised. Supported video request builders do not establish perfect fixed-audio/multi-speaker sync or exact current video pricing.

A media package optionally has `manifest: {run_id, batch_id, jobs, uploads}`. Each job has ID, stable batch-scoped episode ID, provider, kind, exact request `{endpoint, body}` and current verified quote `{amount, unit, verified_on, source_url}`. Magic Hour uses integer credits; image requests are pinned at 50 credits. Video requires fresh exact cost plus `image_evidence: {plan, accepted}` that passes hash/pixel checks. Approved upload records bind input SHA-256 and media kind.

ElevenLabs quote amount is exact tagged characters. It also needs verified billing `{unit: credits|INR|USD, max_amount, rate_verified: true}`. Submitted characters are not a verified credit charge. Verify included allowance and overage controls before activation.

CLI live jobs require `--approval token.json --enable-live --ledger /private/shared-batch.sqlite`. The token binds run/batch IDs, exact manifest hash, approval source, expiry <=24h, exact job counts/totals, voice billing limits and designated key identities. Key values come only from `MAGICHOUR_IMAGE_VIDEO_KEY` and `ELEVENLABS_API_KEY` or private injection. The image/video key is never routed to voice/writing. Do not put secrets in manifests, tokens, notebooks or source.

Use one shared ledger for the entire batch across restarts/directories. Reservations are transactional; unknown/submitting/failed jobs never automatically resubmit. Pending jobs resume the provider project. Completed outputs are rehashed. Overcharges stop the batch after detection; local software cannot undo provider charges. No silent paid retries, fallback or top-up. Conservative provider-host checks refuse arbitrary downloads/redirects.

Future generated bytes, uploaded dependency paths, actual voice timings and precise video quotes are unknown initially. Generate/check/quote the next stage under scoped approval; do not fabricate acceptance or timing to force an uninterrupted first-time paid run.

## Actual local assembly and soundtrack

Package `season` needs series ID, season number, reviewed canon and episodes. An episode needs:
- `id`, `audio: {path, sha256}`, `audio_checked: true`, `cue_audio_sha256` matching that audio.
- `spoken_lines` containing exact dialogue; `names` mapping speaker IDs to display names.
- `cues: [{start, end, text, speaker, actual_audio_checked: true}]` in measured seconds.
- `shots: [{path, sha256, kind: image|video, frames, pixel_checked: true}]` covering `ceil(audio_seconds*24)` frames exactly.

Do not set evidence booleans true without inspecting/listening. Output: conformed shot MP4s, continuous master, clean MP4, ASS/SRT, captioned MP4 and season ZIP. Image-only input is explicitly a still animatic; short videos fail instead of silently freezing. Generated clip audio is discarded; accepted master plays once. Output is a preview pending full playback/continuity/mix review.

Optional soundtrack entries need local path/hash, approved license, creator/title, source/license HTTPS URLs, checked date, hashed terms file, commercial/sync verification and required attribution, plus start_seconds/gain. CC0/CC-BY/YouTube Audio Library evidence is checked; arbitrary uploads and paid libraries are not presumed free. Local mixing applies gain/delay/limiting; listening still checks speech clarity. Free Commons discovery/download is now available as a separate candidate workflow described below; content listening remains required.

`--backend own` uses our ffmpeg implementation. `--backend h3_join` invokes sanitized hash-pinned `join.mjs` for local trim/concat/master audio, then our subtitle/name-bar pass. No vendor caption Python/font path is invoked. Both paths pass real synthetic-media integration tests. These fixtures are software tests, not dialogue/emotion samples.

## Continuation, exclusions and remaining checks

Season ZIPs enumerate every asset path/size/hash plus canon characters/facts/unresolved/ending. ZIP inspection rejects unsafe paths, symlinks, encryption, duplicates, hash mismatch, suspicious compression and size limits. Arbitrary old videos are not reliable canon. No file is executed on import.

Six H3 source modules remain unchanged in the vendor folder. Only local `join.mjs` executes. `render-all.mjs`, paid service orchestration, Modal/RunPod and MiniMax H3 weights are not activated. Model license/compute permission is separate and remains blocked. Full H3 source/deployment/media/weights, secrets, output caches and private ledgers are excluded.

Remaining verification: real inference quality/account/model access, current video and voice billing quotes, real ASR inference/phonetic timing, emotional acting/lip sync, soundtrack title clearance/listening, creative continuity and final full-playback review. No live film-quality guarantee, true 3D engine or hosted production deployment is claimed.

## Official references

- https://docs.magichour.ai/api-reference/models
- https://docs.magichour.ai/api-reference/image-projects/ai-image-generator
- https://docs.magichour.ai/api-reference/image-projects/ai-image-editor
- https://docs.magichour.ai/api-reference/files/generate-asset-upload-urls
- https://docs.magichour.ai/api-reference/image-projects/get-image-details
- https://docs.magichour.ai/api-reference/video-projects/get-video-details
- https://docs.magichour.ai/api-reference/video-projects/audio-to-video
- https://docs.magichour.ai/api-reference/video-projects/image-to-video
- https://elevenlabs.io/docs/api-reference/text-to-dialogue/convert-with-timestamps
- https://docs.api.nvidia.com/nim/reference/llm-apis
- https://platform.claude.com/docs/en/models/sonnet-5/overview
- https://platform.claude.com/docs/en/about-claude/pricing
- https://docs.ollama.com/api/chat
- https://docs.ollama.com/api/tags

## Free/local completion update (20 October, evening)

### Automatic actual-audio alignment recovery

`python audiofirst.py align-local --wav master.wav --lines lines.json --model-path /existing/faster-whisper-small.en --out alignment.json`

`alignment.py` uses an existing local faster-whisper model only, CPU/int8, `local_files_only=True`; no package install or model download occurs. The previously approved small.en choice can be supplied if available on the target machine. This environment does not currently have faster-whisper installed, so model inference remains untested here. Exact normalized script words must match every ASR word in order, with probability >=.65, valid nonoverlapping times and nearby waveform energy. Number substitutions, missing words, uncertain matches and unsupported onsets reject. Explicit bounded recovery windows trigger independent clip retranscription. Cues retain original text/punctuation, split at source word boundaries and enforce reading speed. This automates recovery mechanics, not phonetic precision or emotional/speaker verification.

### Semantic QA and automatic acceptance

`quality.py` decodes video frames at least twice per second, measures image blankness/size, binds reference/sample/expectation hashes and requires two distinct versioned free-local evaluators to agree at >=.95 confidence on every requested check. Identity, wardrobe, props/orientation, action, expression, lip sync, speech and continuity can independently fail or remain unknown. Missing evidence/engines, low confidence, changed bytes or duplicate evaluators reject, never become a pass. Sampled QA cannot cover every frame or prove actual quality.

`local_vision.py` batches actual frame/reference pixels to an already-installed loopback Ollama vision model. It does not download models or use paid/cloud APIs. It explicitly rejects speech/phoneme lip-sync claims from static frames. No real semantic evaluator or model accuracy was tested here. A confidence score is a model report, not calibrated probability or proof of quality. Two model names do not by themselves establish statistical independence. The library permits stronger local evaluators via explicit callables.

`tracked_lip_sync` binds a continuous speaker-specific mouth track to video/audio hashes, rejects ambiguous/occluded/low-confidence tracking and screens motion/audio lag/correlation. A face/landmark tracker is not bundled. Correlation is not phoneme recognition; it cannot alone clear lip sync or identity.

In a production package, `automatic_acceptance: true` calls `prepare_episode`: decode generated audio if needed, recover exact line timings, require existing independent audio-quality evidence, inspect/score visual assets and only then set assembly acceptance fields. Episodes need `dialogue_lines` with IDs/speakers/exact text and `alignment.local_model_path` or an injected transcriber. Shots need explicit `expectations`. `--qa-models MODEL_A MODEL_B` supplies installed local visual models, not speech judges. Generated job pointers may obtain their actual hashes automatically only in this mode, then must pass QA. Failed checks stop before episode assembly; partial artifacts stay in the private state directory for diagnosis, not packaged as final output.

Audio identity/emotion and phoneme lip sync still need capable installed local evaluators or explicit actual review evidence. The system does not pretend those models exist. With no such engines, fully automatic acceptance intentionally refuses. Actual automatic acceptance/assembly plumbing is integration-tested with clearly synthetic evaluator fixtures, not claimed real semantic success.

### Free licensed music/SFX discovery and download

`python audiofirst.py find-free-audio --query 'door closing' --out candidates.json`

`python audiofirst.py find-free-audio --query 'door closing' --download-first --out output/new-audio-asset`

`free_audio.py` searches Wikimedia Commons without keys/accounts/payments, accepting only explicit CC0 or CC BY 4.0 metadata, known license URLs, audio MIME and the expected Commons/upload hosts. Unclear restrictions, NC/ND/SA/unknown/public-domain labels, missing artist, changed metadata, redirects, oversized downloads and non-audio content reject. It rechecks metadata, fetches license terms, downloads within a byte cap, decodes audio, converts to WAV, saves source/license hashes and writes attribution including conversion/mixing notice. No audio was actually downloaded from a public source in release tests; HTTP/content are mocked and decoding is tested with synthetic audio. Source metadata is not independent ownership/rights clearance. The first search result is a candidate, not proof of musical fit or safe content. Listen/check rights before mixing. No popular commercial song or arbitrary YouTube audio is assumed free.

### H3 runtime/compiler and limited 3D

`h3_local.py` compiles an explicitly supplied/pinned Comfy API graph with fixed-audio zero-noise-mask nodes and ordered guide pins, respecting the 17k+5 frame grid. It refuses unknown node classes, compiler-ID collisions and path/URL assets. It does not include the missing complete H3 template/dependency deployment or invent model settings. Runtime preflight accepts loopback only and requires explicit free-local-compute approval, model-license reference and hash-verified installed weights; no automatic download, cloud GPU or account. Submission persists a no-duplicate receipt; unknown outcomes block retries. History collection accepts only one video under a configured local output root and refuses traversal/symlinks. Compiler/transport are mock-tested only. Actual installed H3 runtime, model rights and inference remain unavailable/blocked.

`procedural.py:box_prop` exports a bounded local OBJ box blockout with no GPU or external dependency. This is a working elementary geometry utility, NOT reference-image-to-3D, a character rig, human reconstruction or a photoreal renderer. Full 3D and hosted product deployment remain out of scope for this tested source release. No model license, GPU access or paid service is implied by code reuse permission.

Additional source references: https://www.mediawiki.org/wiki/API:Imageinfo ; https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia ; https://commons.wikimedia.org/wiki/Commons:Machine-readable_data/en ; https://docs.comfy.org/development/comfyui-server/comms_routes . These inform adapters; no current public asset license or actual runtime compatibility is certified by mock tests.

## Portable runtime revision (20 October 2026)

Explicit official-source install/download commands, CPU model smoke tests and H3 runtime setup are now in `portable/README.md`. This supersedes earlier statements that local runtimes were not installed anywhere: faster-whisper tiny.en, SmolVLM-256M and MediaPipe have been installed and exercised on the release-preparation Linux CPU environment. They are not bundled in the ZIP. The strict timing/tracking fixtures rejected, and no output was automatically accepted. Real GPU H3 inference, phoneme lip sync, calibrated emotion/identity/prop/action QA and a complete reference-to-3D reconstruction pipeline remain unverified/unimplemented as described there.
