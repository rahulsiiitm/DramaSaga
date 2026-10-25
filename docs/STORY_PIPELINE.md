# Story development, continuity and production

Source contract: 25 October 2026. This supplements `AUDIO_FIRST.md`; the commands
and schema changes below supersede its older story-writing and episode-count notes.

## Working scope

The implemented path is:

`brief → causal outline → episode draft → contract check → grounded review/repair → reference plan → storyboard → accepted audio/alignment → measured cuts → renderer plan → exact requests → reviewed clips → assembly → season package`

It does not synthesize a film merely by validating JSON. A model's critique is not
an independent audience test. Video, voice and writer API calls require their
existing exact-request approvals. No new model downloads or paid rerolls happen
automatically. The local test fixtures are colors and tone, not generated acting.

## Run the included pilot

From the repository root:

```sh
python audiofirst.py validate-story --brief examples/pilot/brief.json --story examples/pilot/story.json
python audiofirst.py run --brief examples/pilot/brief.json --story examples/pilot/story.json --out output/my-pilot
```

The run writes `brief.json`, `writing-request.json`, `story.json`, `continuity.json`,
`flow.json`, `voice-requests.json`, `run.json` and a versioned storyboard directory.
`draft-timing.json` reports word counts and a deliberately rough speech-duration
range for pacing review. Declared draft seconds cannot substitute for real audio.
Open the printed `storyboard_preview` file. It provides shot navigation, playback,
dialogue, shot purpose, camera/action and start/end state. Missing reference images
remain labeled missing. Its first timing estimate is only a drafting aid.

The six-shot example is an original 45-second estimated drama about two adult
siblings, a concealed grant letter and a key. It uses eleven planned images when
both character masters are generated. It supplies no real media or reviews.

For an existing installed Ollama model:

```sh
python audiofirst.py run --brief examples/pilot/brief.json --local-model INSTALLED_MODEL --out output/model-pilot
```

Staged writing is the CLI default. `--max-repairs 0|1|2` bounds repairs per outline
and episode; default one. `--legacy-writer` explicitly retains the historical
one-call writer. Library `LocalWriter` keeps its old behavior unless a workspace
is supplied. `write_season` remains available for existing integrations.

Each writer stage saves its exact request before inference. Completed responses
are keyed by request content in `writing/stages.sqlite`. Use the same output with
`--resume` to continue, rather than submitting completed stages again. Accepted
episode summaries and the immediately preceding full episode provide deterministic
context retrieval; all prior scripts are not repeatedly sent in full.

Malformed structures get bounded contract repair. Semantic criticism must quote
actual dialogue/action in a named shot and assess causality, motivation, dialogue,
continuity and pacing. Unfounded review quotes fail. Exhausted rejection stays a
rejection; it never becomes acceptance to finish the season.

## Brief and input form

```sh
python -m magicdrama.audiofirst.form --out output/new-brief
```

The existing loopback-only form now supports 1–50 episodes, premise, central
conflict, ending constraints, visual style, character goals, relationships and
multiple environment references. Its existing styling is preserved. JSON briefs
can additionally give each character `motivation` and `secret`.

Optional new brief fields:

- `premise`, `central_conflict`, `ending_constraints`, `visual_style`: text.
- `relationships`: `{from: CAST_ID, to: CAST_ID, description: TEXT}` records.
- `environments`: `{id, description, image?: {mode: "upload", path}}` records.

Brief image paths resolve relative to the brief file, not the shell directory.
The form validates all uploads before writing reference files. Character and
environment images must be PNG/JPEG/WebP, at most 5 MiB each, decodable, at least
64 pixels per dimension, and at most 16 megapixels. The existing 30 MiB request
limit remains. Decodability is not visual-quality approval.

## Version 2 story contract

Legacy stories without `schema_version` remain readable and produce an explicit
`legacy_unchecked` continuity status. They are not silently upgraded into verified
state. Version 2 retains episode/line/shot fields and adds:

- Story `facts: [{id, text}]`: immutable fact catalog.
- Shot `scene_id`, `narrative_purpose`, and staged-writer `beat_id`.
- Shot `start_state`, `end_state`, `changes`, `reveals`.
- Optional `offscreen_speakers`, `speaking_faces`, `transition_reason`, `cut`, `render_group`.

State enumerates every cast member, including offscreen ones:

```json
{
  "characters": {
    "mira": {
      "position": "west edge of desk",
      "facing": "east toward Dev",
      "wardrobe": "blue shirt and canvas bag",
      "emotion": "hurt"
    }
  },
  "props": {
    "envelope": {"owner": "mira", "hand": "right", "status": "sealed grant letter"}
  },
  "knowledge": {"mira": ["grant_approved"]}
}
```

The example above illustrates one character; real states must include the full
cast. A prop owner is a cast ID or `set`; its hand is `left`, `right`, `both` or
`none`. `set` requires `none`.

Each changed flattened field needs a matching change record:

```json
{"field":"props.envelope.owner","from":"dev","to":"mira","reason":"Visible handoff"}
```

All changed values, including hand or emotion, need separate records. New props
may be introduced inside a shot with null `from` values for their three fields;
existing entities cannot disappear. Mark destruction/loss in prop status instead.
Knowledge gains need matching `reveals` with a fact ID, an actual shot line ID and
`learned_by` cast IDs. Knowledge cannot be silently erased.

Same-scene cuts preserve the preceding end state. A new scene requires a
`transition_reason`; position, facing and emotion may reset, while wardrobe,
prop inventory and knowledge remain continuous. State values and reasons are
declared contracts, not proof that the generated pixels depict them.

Reference planning reuses uploaded environments, makes a wardrobe variant only
when needed, and uses the preceding storyboard frame as composition context
within a continuous scene. It does not force a first-frame chain across locations.
Never label a failed profile generation as a successful side view.

## Measured audio and render compilation

After real synthesis, review/listen to the dialogue and align it to the exact
script. The existing `align-local` command can use an already installed ASR model.
Its cues include line IDs. Supply:

- `audio.json`: `{path, sha256}` for an actual PCM16 WAV.
- `alignment.json`: `audio_sha256` and ordered `cues` containing `line_id`, `speaker`,
  exact `text`, `start`, `end`, `actual_audio_checked`.
- `audio-review.json`: matching `sha256`, `lines_sha256` (canonical
  `execution.signature(episode['lines'])`), and actual reviewed booleans `words`,
  `speakers`, `emotion`, `pronunciation`.
- `frames.json`: `frame-SHOT_ID` mapped to actual image `{path, sha256}` records.

Do not fabricate review booleans. ASR text agreement does not prove voice identity
or emotional performance. Compile only after the corresponding real checks.

```sh
python audiofirst.py compile-render --brief brief.json --story story.json --episode ep1 --audio audio.json --alignment alignment.json --audio-review audio-review.json --renderer renderer.json --assets frames.json --out output/compiled
```

This writes `track.json` and `render-plan.json`. Omitting `--assets` allows duration
and capability planning, but such an unbound plan cannot create production
requests or accept rendered media. Bound frame bytes are rehashed before use.

A renderer profile declares an explicit ID/model, supported `modes`,
`min_seconds`, `max_seconds`, `exact_audio`, `multi_shot`, `max_speakers`,
`end_frame` and optional `durations` / `max_reference_images`. The sample profile
is illustrative, not evidence of account access or successful acting.

Supported logical modes are `image_to_video`, `audio_to_video`, `performance` and
`native_audio`. These describe capabilities; they do not install adapters.
Visible speech with a locked master requires exact-audio/performance support.
Unsupported duration, speaker count, end frames and connected sequences fail
before submission. Split shots at meaningful edits rather than freezing video.

Default cuts follow measured dialogue. For reactions/inserts or J/L cuts, specify
every shot's `cut: {start_frame, end_frame}`. They must cover the full master in
order at 24 fps without gaps/overlap. Actual audible lines are derived from their
time intersections, independently of visual line ownership. A listener can remain
on screen while the speaker is offscreen.
For shoulder/back views, `speaking_faces` can narrow the visible characters whose
mouths actually need animation; it must be a subset of `visible_characters`.
Without that field, every visible speaking character is checked conservatively.

`--connected` groups contiguous shots with the same `render_group` inside one
scene/location. The renderer must declare multi-shot and enough reference-image
capacity. A grouped result is trimmed using each cut's source offset during
assembly. `--audio-mode native` creates a separate experiment plan; its generated
audio must be reviewed and realigned into a new locked plan/package before assembly.

## Preview before motion rendering

```sh
python audiofirst.py storyboard --brief brief.json --story story.json --assets frames.json --tracks tracks-by-episode.json --out output/storyboard
python audiofirst.py animatic --brief brief.json --story story.json --episode ep1 --track output/compiled/track.json --assets frames.json --out output/animatic
```

`tracks-by-episode.json` maps episode IDs to measured tracks. Without tracks the
HTML preview clearly labels timing estimated. The optional MP4 animatic requires
actual measured audio and every shot image; it never substitutes missing visuals.
`--ffmpeg` can select an existing executable. The MP4 is a still preview, not a
claim of generated acting, final captions or lip sync.

## Exact requests and reviewed production media

The current request builder supports Magic Hour's documented single-shot image-
and audio-to-video routes. The audio route has no selectable model field; use the
explicit route identity `magichour-audio-to-video`. Other renderer profiles can
compile for evaluation/import, but no unimplemented provider or multi-shot API
is silently substituted.

```sh
python audiofirst.py video-manifest --plan output/compiled/render-plan.json --images image-plan.json --accepted-images accepted-images.json --uploads uploads.json --quotes quotes.json --run-id pilot1 --batch-id season1 --out manifest.json
```

`image-plan.json` is `flow.json`'s `image_first` object. Accepted images retain the
existing hash/plan/pixel-review evidence contract. `uploads.json` maps asset IDs
to `{file_path: "api-assets/...", sha256}`; the master uses `audio-EPISODE_ID`.
Without padding, the full accepted master can be referenced at exact shot times.
For discrete/minimum provider durations, prepare exact PCM slices and silence
padding from the accepted master:

```sh
python audiofirst.py prepare-render-inputs --plan output/compiled/render-plan.json --out output/render-inputs
```

This writes WAV segments and `upload-candidates.json`. Each segment retains source
and compiled-input hashes. Before request construction, its samples are checked
against the accepted master and the declared silence padding; a modified segment
cannot pass by changing its file hash. This is deterministic derivation, not new
voice generation or a fabricated human review.

An explicit upload-only manifest has `jobs: []`, run/batch IDs, and `uploads` with
the exact candidate SHA-256/kind pairs. Its approval uses the existing manifest
contract with empty generation counts/totals/billing limits. Upload using:

```sh
python audiofirst.py upload-assets --manifest upload-manifest.json --approval upload-approval.json --assets output/render-inputs/upload-candidates.json --ledger PRIVATE_BATCH.sqlite --out output/uploads --enable-live
```

The result `uploads.json` preserves segment provenance alongside provider paths.
Its `audio-render-SHOT_ID` segments are preferred to the full-master route. Upload
receipts resume by content without repeating completed transfers. No upload was
performed in verification, and an upload approval does not approve generation.

`quotes.json` maps each `render-SHOT_ID` to an actual current quote. Request
materialization does not establish a quote or grant spend permission. Use the
existing exact manifest token/shared ledger live execution path. Each job binds
its compiled input hash and exact provider request. Current schemas checked:
[image-to-video](https://docs.magichour.ai/api-reference/video-projects/image-to-video)
and [audio-to-video](https://docs.magichour.ai/api-reference/video-projects/audio-to-video).
Actual provider execution remains untested by this release.

After inspecting real generated clips, `media.json` maps render IDs to
`{path, sha256, kind: "video", pixel_checked, input_sha256}`. The input hash comes
from the corresponding compiled job. Do not mark uninspected clips checked.

```sh
python audiofirst.py media-package --brief brief.json --story story.json --episode ep1 --track output/compiled/track.json --plan output/compiled/render-plan.json --media media.json --out episode-package.json
python audiofirst.py produce --package episode-package.json --out output/season-preview --resume
```

For multi-episode stories, build each episode package and merge them:

```sh
python audiofirst.py merge-packages --brief brief.json --story story.json --packages ep1-package.json ep2-package.json --out season-package.json
python audiofirst.py produce --package season-package.json --out output/season-preview --resume
```

Merging requires every planned episode from the same exact story. Partial exports
are marked incomplete and cannot masquerade as a complete previous season.
Canon reflects the included episode's ending/knowledge, not future revelations.

## Resume, repair and reconciliation

Planning `--resume` requires its ownership marker. Changed input requests create
new stage versions; identical completed requests reuse receipts. Unknown remote
outcomes block automatic retries. Inspect them with:

```sh
python audiofirst.py stage-status --state output/model-pilot/writing/stages.sqlite
```

If the provider actually returned a recoverable response, import that exact
response with `reconcile-stage --state ... --stage ... --input-sha256 ... --result
recovered-response.json --evidence ACCOUNT_RECORD_REFERENCE`. This only completes
an existing unresolved receipt and records the evidence reference. It does not
resubmit inference or erase any spend reservation. A local evidence string does
not independently authenticate a provider record.

Staged cloud writing accepts an approval bundle `{stages: [TOKEN, ...]}`. Every
token retains the existing exact `{body, config}` hash, model, expiry, key identity
and spend requirements. Missing approval leaves the saved request ready for later
authorization without network submission. Resume after supplying the matching
token. Requests depend on earlier actual responses, so later approval hashes
cannot be invented in advance. Claude fallback stages share the existing ledger
cap and use distinct request-derived job keys. Planning reports do not claim zero
paid writer calls when the transport's billing is unknown.

Production `--resume` caches conformed clips by source hash, trim offset, frame
count and encoding settings. Unchanged episodes and exports reuse their receipts.
A replacement clip re-conforms that clip and rebuilds the affected episode/edit;
it does not re-render good provider jobs. Each export gets an immutable versioned
cut directory; ZIPs contain only that current cut. Earlier accepted exports remain.
Changed cached bytes fail rather than silently regenerating accepted work.
Planning and production also take cross-platform workspace locks, preventing
concurrent invocations from mixing artifacts in the same output directory.

Failed local encoding can retry in a fresh attempt directory. Uncertain paid jobs
retain reservations and are not resubmitted. Provider dependencies must form a
valid DAG. Generated bytes written before a crash can be reconciled against the
persisted provider response without another submission. Native-audio packages
are refused before provider execution.

The historical `series_run_v2.py` now stops when its continuity evaluator errors.
It no longer turns an unavailable check into `ok: true`. `h3_join` now correctly
selects the existing local join backend; the old `alec` library alias still works.

## Verification and remaining limits

```sh
python -m unittest discover -s tests -v
python -m compileall -q magicdrama/audiofirst audiofirst.py series_run_v2.py
```

The suite covers legacy compatibility, state/knowledge violations, grounded
reviews, repair limits, request caching, missing approvals, unknown submissions,
hash-bound audio/references, cut coverage, renderer constraints, HTML escaping,
exact request construction and stale-media rejection. FFmpeg/ffprobe integration
tests exercise real encoding, captions, ZIP verification, resume, selective
conformance and grouped-source trim offsets. They skip if those tools are absent.
The animatic test can also use an existing imageio-ffmpeg installation.

The form and storyboard controls were additionally exercised in a real browser.
No production model inference, real voice quality, face consistency, emotional
acting or phonetic lip sync was verified. Those require actual media and full
playback review. No competing pipeline was installed or benchmarked.

For actual controlled trials, `compare-trials --trials trials.json --out report.json`
requires at least two records with the same `input_sha256` (script/references/
format), `name`, `accepted_seconds`, `generated_seconds`, `total_cost: {amount,
unit}`, `elapsed_seconds`, `manual_minutes`, `rerolls`, `critical_errors` and optional
`viewer_scores` on a 1–5 scale. Include rejected generations in total cost. The
report shows cost per accepted second and explicitly leaves absent viewer evidence
unknown. It does not fabricate a winner or compare different currencies as equal.
