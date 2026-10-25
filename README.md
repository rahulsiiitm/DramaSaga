# MicroDrama

## Story-first pilot workflow

The upgraded audio-first path supports a single-episode pilot, staged writing,
explicit cut continuity, a local storyboard player, measured render plans and
resumable accepted-media assembly. Start here for new projects:

```sh
python audiofirst.py run --brief examples/pilot/brief.json --story examples/pilot/story.json --out output/my-pilot
python -m unittest discover -s tests -v
```

Open the `storyboard_preview` path printed by the run. The supplied pilot is an
original script and continuity example; no character images, voices or generated
film are bundled. Missing images are displayed explicitly. For generation with an
already installed local writer, replace `--story ...` with `--local-model MODEL`.

See [the complete workflow](docs/STORY_PIPELINE.md) for reference uploads, staged
cloud writing, measured audio, renderer capabilities, request manifests, repairs,
season continuation and the limits of current verification. The commands below
describe the older supervised scene runner and remain supported.

## Install and plan

Python 3.10+ and ffmpeg/ffprobe are required for rendering and QA. Install ffmpeg through your operating system's package manager.

```sh
python -m pip install -r requirements.txt
python run.py
python -m unittest discover -s tests -v
```

The default command loads `examples/honesty.json`, reads all ten scripts, prints per-scene quotes, missing references and cap checks, and makes zero network requests. The sample ten-episode plan exceeds its 25,000-credit batch cap. Planning does not raise the cap or spend anything.

## Inputs

- Copy and edit `examples/honesty.json`. Relative paths resolve from the config file, not the working directory.
- Put your character and location images at the configured paths. No reference media is included.
- Check `characters`, `wardrobe`, `locations` and `scene_overrides` against each scene. Automatic character inference reads only visual descriptions and speaker names; it is not a substitute for reviewing the reference list.
- Confirm current models and prices. Set `quote.verified_at` to today's local date only after checking them. The sample numbers are historical, not a current quote.
- Set episode and batch caps deliberately. Estimates exclude rerolls and may differ from provider charges. Unknown submissions reserve their full quoted cost until reconciled. Recorded charges above estimates count against later jobs; a cap cannot undo a provider overcharge.
- Set the environment variable named by `api_key_env`. Never put a key in JSON, a notebook, or a commit.
- Configure exactly two independent transcription command arrays in `transcribers`. Each receives `{audio}` as a WAV path, must print only the transcript to stdout and exit nonzero on failure. An optional local adapter is provided in `transcribe_whisper.py`; use a different engine/model/service for the second command. The second transcriber is not bundled.

Example primary command: `["python", "/absolute/path/transcribe_whisper.py", "{audio}", "--model", "base"]`. Install `faster-whisper` separately if using it. Model downloads may be needed. Transcription commands run locally under your account; use only commands you trust.

## Render one scene at a time

```sh
python run.py --config examples/honesty.json --episode 1 --live --accept-costs
```

`--live --accept-costs` allows paid requests. Reference files, current price acknowledgement, API key, ffmpeg and two transcription commands are checked first. Each invocation renders at most one new scene. It then stops for human review. This runner is intended for a supervised Linux/Colab environment; output locking uses POSIX file locks.

For each scene it writes the keyframe, clip, three frame samples, audio WAV, transcript comparison and a `review.json`. Watch the full clip and inspect faces, clothes, actions, props, expressions and text. Listen to every line. Only then set all review booleans to true. Review approval is bound to the current clip's SHA-256. Transcript agreement is a screening check, not proof that performance or speech is correct.

Fresh keyframes are the default. To chain a scene, set `chain_from_previous: true` and `same_space_confirmed: true` in that scene's override. The character-reference sets must also match, and the preceding clip must be approved. Do not chain across a location change or from a frame that lacks the required character.

`scene_overrides` keys look like `E01_S02`. They can set `characters`, `location_reference`, `prompt_extra`, `attempt` and the chaining flags. Keyframe and clip prompts retain the original wardrobe, dialogue-purity, action and prop-orientation rules. The original v5 clips used native generated speech, not a separate lip-sync pass.

## Resume, reroll and assemble

Job IDs and credit reservations are persisted before polling. A timeout after submission is treated as an unknown outcome, never an automatic resubmission. Reconcile that outcome in the provider account before changing job state. HTTP generation POSTs are not retried automatically.

For a rejected clip, raise that scene's `attempt` number and adjust `prompt_extra`. Keep the same output directory so prior attempts still count against the caps. Never delete job records to make a budget appear unused. Downstream scenes need review again when an upstream accepted clip changes. Change scripts/config only between supervised attempts, not while a render is running.

Once every scene has current approval:

```sh
python run.py --config examples/honesty.json --episode 1 --live --assemble
```
