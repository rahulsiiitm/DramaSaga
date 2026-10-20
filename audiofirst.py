import argparse
import json
from pathlib import Path

from magicdrama.audiofirst.core import timeline, validate_brief, writing_request, write_json
from magicdrama.audiofirst.planning import reference_plan, threejs_request
from magicdrama.audiofirst.season import inspect_season_zip, extract_season_zip, pack_season
from magicdrama.audiofirst.media import build_master
from magicdrama.audiofirst.story import validate_story
from magicdrama.audiofirst.subtitles import write_subtitles, burn_subtitles
from magicdrama.audiofirst.gates import require_stage, require_inputs
from magicdrama.audiofirst.pipeline import offline_flow, validate_free_audio_asset
from magicdrama.audiofirst.images import image_first_plan
from magicdrama.audiofirst.runner import run, write_draft
from magicdrama.audiofirst.production_run import media_run
from magicdrama.audiofirst.local_writer import LocalWriter
from magicdrama.audiofirst.cloud_writer import NvidiaClaudeWriter
from magicdrama.audiofirst.dialogue_timing import validate_dialogue_alignment


def main():
    parser = argparse.ArgumentParser(description='Audio-first planning and accepted-media assembly. Live generation refuses unless explicitly enabled with exact approval.')
    sub = parser.add_subparsers(dest='command', required=True)
    plan = sub.add_parser('plan')
    plan.add_argument('--brief', required=True)
    plan.add_argument('--previous-season')
    plan.add_argument('--out', required=True)
    story = sub.add_parser('validate-story')
    story.add_argument('--brief', required=True)
    story.add_argument('--story', required=True)
    refs = sub.add_parser('references')
    refs.add_argument('--brief', required=True)
    refs.add_argument('--episodes', required=True)
    refs.add_argument('--out', required=True)
    timing = sub.add_parser('timeline')
    timing.add_argument('--lines', required=True)
    timing.add_argument('--characters', nargs='+', required=True)
    timing.add_argument('--out', required=True)
    master = sub.add_parser('master')
    master.add_argument('--timeline', required=True)
    master.add_argument('--out', required=True)
    inspect = sub.add_parser('inspect-season')
    inspect.add_argument('archive')
    extract = sub.add_parser('extract-season')
    extract.add_argument('archive')
    extract.add_argument('--out', required=True)
    pack = sub.add_parser('pack-season')
    pack.add_argument('--root', required=True)
    pack.add_argument('--metadata', required=True)
    pack.add_argument('--out', required=True)
    scene = sub.add_parser('threejs-request')
    scene.add_argument('--reference', required=True)
    scene.add_argument('--asset-id', required=True)
    scene.add_argument('--subject', choices=['prop', 'location', 'character'], required=True)
    scene.add_argument('--output-dir', required=True)
    scene.add_argument('--out', required=True)
    captions = sub.add_parser('subtitles')
    captions.add_argument('--timeline', required=True)
    captions.add_argument('--out', required=True)
    captions.add_argument('--names', required=True, help='JSON speaker-id to display-name map')
    captions.add_argument('--introductions', help='JSON frame intervals and speaker ids')
    burn = sub.add_parser('burn-subtitles')
    burn.add_argument('--timeline', required=True)
    burn.add_argument('--video', required=True)
    burn.add_argument('--subtitles', required=True)
    burn.add_argument('--out', required=True)
    for command in (refs, timing, master, captions, burn, pack):
        command.add_argument('--reviews', help='Optional human audit chain; automatic validations always run')
    gate = sub.add_parser('check-stage')
    gate.add_argument('--reviews', required=True)
    gate.add_argument('--stage', required=True)
    flow = sub.add_parser('flow')
    flow.add_argument('--brief', required=True)
    flow.add_argument('--story', required=True)
    flow.add_argument('--out', required=True)
    license_check = sub.add_parser('check-free-audio')
    license_check.add_argument('--asset', required=True)
    alignment = sub.add_parser('check-dialogue-timing')
    alignment.add_argument('--wav', required=True)
    alignment.add_argument('--response', required=True)
    alignment.add_argument('--inputs', required=True)
    images = sub.add_parser('image-plan')
    images.add_argument('--brief', required=True)
    images.add_argument('--story', required=True)
    images.add_argument('--image-cap', type=int, default=12)
    images.add_argument('--exposure', help='JSON current reserved/actual image+video credits per episode, including other batch episodes')
    images.add_argument('--out', required=True)
    unified = sub.add_parser('run')
    unified.add_argument('--brief', required=True)
    unified.add_argument('--story')
    unified.add_argument('--cloud-writer-config', help='NVIDIA-first model/token/rate config')
    unified.add_argument('--writer-approval')
    unified.add_argument('--writer-ledger')
    unified.add_argument('--enable-cloud-writing', action='store_true')
    unified.add_argument('--local-model', help='Already installed local Ollama model. No download or cloud fallback')
    unified.add_argument('--previous-season')
    unified.add_argument('--template-draft', action='store_true', help='Opt-in repetitive local scaffold, not a model-written season')
    unified.add_argument('--voices')
    unified.add_argument('--exposure')
    unified.add_argument('--soundtrack')
    unified.add_argument('--image-cap', type=int, default=12)
    unified.add_argument('--out', required=True)
    produce = sub.add_parser('produce')
    produce.add_argument('--package', required=True)
    produce.add_argument('--out', required=True)
    produce.add_argument('--ledger', help='Required shared private batch ledger path for live jobs')
    produce.add_argument('--approval', help='Exact per-run approval manifest token; not a secret key')
    produce.add_argument('--enable-live', action='store_true', help='Still requires matching approval and provider keys')
    produce.add_argument('--qa-models', nargs=2, help='Two distinct already-installed free local Ollama vision models; speech/lip-sync still need actual evidence')
    produce.add_argument('--backend', choices=['own','h3_join'], default='own')
    align = sub.add_parser('align-local')
    align.add_argument('--wav', required=True)
    align.add_argument('--lines', required=True)
    align.add_argument('--model-path', required=True)
    align.add_argument('--out', required=True)
    sounds = sub.add_parser('find-free-audio')
    sounds.add_argument('--query', required=True)
    sounds.add_argument('--out', required=True)
    sounds.add_argument('--download-first', action='store_true', help='Download a compatible licensed candidate, still requires listening')
    args = parser.parse_args()
    load = lambda p: json.loads(Path(p).read_text())
    predecessors = {'references': 'story', 'timeline': 'audio', 'master': 'audio',
                    'subtitles': 'timing', 'burn-subtitles': 'picture', 'pack-season': 'final'}
    if args.command in predecessors and args.reviews:
        fields = {'references': ['brief', 'episodes'], 'timeline': ['lines'], 'master': ['timeline'],
                  'subtitles': ['timeline'], 'burn-subtitles': ['timeline', 'video'],
                  'pack-season': ['metadata']}
        inputs = [getattr(args, name) for name in fields[args.command]]
        if args.command == 'pack-season':
            inputs += [str(path) for path in Path(args.root).rglob('*') if path.is_file()]
        require_inputs(load(args.reviews), predecessors[args.command], inputs)
    if args.command == 'align-local':
        from magicdrama.audiofirst.alignment import LocalWhisper, recover_alignment
        result = recover_alignment(args.wav, load(args.lines), LocalWhisper(args.model_path))
        write_json(args.out,result); print(json.dumps(result,indent=2)); return
    elif args.command == 'find-free-audio':
        from magicdrama.audiofirst.free_audio import CommonsAudio
        client=CommonsAudio()
        result=client.choose_and_download(args.query,args.out) if args.download_first else client.search(args.query)
        if not args.download_first: write_json(args.out,result)
        print(json.dumps(result,indent=2)); return
    elif args.command == 'produce':
        import os
        keys = {'magichour': os.environ.get('MAGICHOUR_IMAGE_VIDEO_KEY'),
                'elevenlabs': os.environ.get('ELEVENLABS_API_KEY')} if args.enable_live else {}
        evaluators = None
        if args.qa_models:
            from magicdrama.audiofirst.local_vision import OllamaVision
            if args.qa_models[0] == args.qa_models[1]: parser.error('QA models must be distinct')
            evaluators = [{'evaluate': OllamaVision(model), 'engine': {'id': model, 'version': 'explicit-installed-runtime', 'local_free': True}} for model in args.qa_models]
        result = media_run(load(args.package), args.out, load(args.approval) if args.approval else None, keys, args.enable_live, backend=args.backend, ledger_path=args.ledger, evaluators=evaluators)
        print(json.dumps(result, indent=2)); return
    elif args.command == 'run':
        if sum(bool(x) for x in (args.story,args.template_draft,args.local_model,args.cloud_writer_config)) > 1:
            parser.error('Choose story or template draft, not both')
        cloud = None
        if args.cloud_writer_config:
            import os
            if not args.writer_approval or not args.writer_ledger: parser.error('Cloud writer needs approval and private ledger')
            cloud = NvidiaClaudeWriter(load(args.cloud_writer_config), load(args.writer_approval),
                {'nvidia': os.environ.get('SARALYA_NVIDIA_KEY'), 'claude': os.environ.get('ANTHROPIC_API_KEY')} if args.enable_cloud_writing else {},
                args.writer_ledger, enabled=args.enable_cloud_writing)
        result = run(load(args.brief), args.out, load(args.story) if args.story else None,
                     args.previous_season, writer=cloud if cloud else LocalWriter(args.local_model) if args.local_model else (lambda request: write_draft(request['brief'],
                         {'series_id': request['brief']['series_id'], 'season': request['brief']['season']-1, 'canon': request['previous_canon']} if request['previous_canon'] else None)) if (args.template_draft or args.local_model or cloud) else None,
                     voices=load(args.voices) if args.voices else None,
                     exposure=load(args.exposure) if args.exposure else None, image_cap=args.image_cap,
                     soundtrack=load(args.soundtrack) if args.soundtrack else None)
        print(json.dumps(result, indent=2))
        return
    elif args.command == 'image-plan':
        result = image_first_plan(load(args.brief), load(args.story), args.image_cap, load(args.exposure) if args.exposure else None)
    elif args.command == 'check-dialogue-timing':
        result = validate_dialogue_alignment(args.wav, load(args.response), load(args.inputs))
    elif args.command == 'flow':
        result = offline_flow(load(args.brief), load(args.story))
    elif args.command == 'check-free-audio':
        result = validate_free_audio_asset(load(args.asset))
    elif args.command == 'check-stage':
        result = require_stage(load(args.reviews), args.stage)
    elif args.command == 'subtitles':
        result = write_subtitles(load(args.timeline), args.out, character_names=load(args.names),
                                 introductions=load(args.introductions) if args.introductions else None)
        print(json.dumps(result, indent=2))
        return
    elif args.command == 'burn-subtitles':
        result = burn_subtitles(load(args.timeline), args.video, args.subtitles, args.out)
        print(json.dumps(result, indent=2))
        return
    elif args.command == 'plan':
        previous = inspect_season_zip(args.previous_season) if args.previous_season else None
        result = writing_request(load(args.brief), previous)
    elif args.command == 'validate-story':
        result = validate_story(load(args.brief), load(args.story))
    elif args.command == 'references':
        result = reference_plan(load(args.brief), load(args.episodes))
    elif args.command == 'timeline':
        result = timeline(load(args.lines), args.characters)
    elif args.command == 'master':
        result = build_master(load(args.timeline), args.out)
        print(json.dumps(result, indent=2))
        return
    elif args.command == 'inspect-season':
        result = inspect_season_zip(args.archive)
    elif args.command == 'extract-season':
        result = extract_season_zip(args.archive, args.out)
        print(json.dumps(result, indent=2))
        return
    elif args.command == 'pack-season':
        metadata = load(args.metadata)
        result = pack_season(args.root, args.out, metadata['series_id'], metadata['season'], metadata['canon'])
        print(json.dumps(result, indent=2))
        return
    else:
        result = threejs_request(args.asset_id, args.reference, args.subject, args.output_dir)
    if hasattr(args, 'out'):
        write_json(args.out, result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
