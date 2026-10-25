import argparse
import json
from pathlib import Path

from magicdrama.audiofirst.core import timeline, validate_brief, writing_request, write_json, load_brief
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
    preview=sub.add_parser('storyboard',help='Local storyboard player; missing frames remain explicit')
    preview.add_argument('--brief',required=True);preview.add_argument('--story',required=True)
    preview.add_argument('--assets');preview.add_argument('--tracks');preview.add_argument('--out',required=True)
    compile_cmd=sub.add_parser('compile-render',help='Bind accepted audio/alignment to shots and renderer capabilities')
    compile_cmd.add_argument('--brief',required=True);compile_cmd.add_argument('--story',required=True)
    compile_cmd.add_argument('--episode',required=True);compile_cmd.add_argument('--audio',required=True,help='JSON path/sha256 asset')
    compile_cmd.add_argument('--alignment',required=True);compile_cmd.add_argument('--audio-review',required=True)
    compile_cmd.add_argument('--renderer',required=True);compile_cmd.add_argument('--connected',action='store_true')
    compile_cmd.add_argument('--assets',help='Hash-bound shot frame images; required before production requests')
    compile_cmd.add_argument('--audio-mode',choices=['locked','native'],default='locked');compile_cmd.add_argument('--out',required=True)
    video_manifest=sub.add_parser('video-manifest',help='Exact request manifest; no submission or invented quotes')
    for field in ('plan','images','accepted-images','uploads','quotes','run-id','batch-id','out'):
        video_manifest.add_argument('--'+field,required=True)
    package_cmd=sub.add_parser('media-package',help='Bind reviewed video outputs to the measured edit')
    for field in ('brief','story','episode','track','plan','media','out'):
        package_cmd.add_argument('--'+field,required=True)
    animatic=sub.add_parser('animatic',help='Encode a still preview against measured accepted audio')
    for field in ('brief','story','episode','track','assets','out'):
        animatic.add_argument('--'+field,required=True)
    animatic.add_argument('--ffmpeg',default='ffmpeg',help='Existing ffmpeg executable')
    stages=sub.add_parser('stage-status');stages.add_argument('--state',required=True,help='Existing stage SQLite file')
    reconcile=sub.add_parser('reconcile-stage',help='Import an actual recovered writer response; never resubmit inference')
    for field in ('state','stage','input-sha256','result','evidence'):reconcile.add_argument('--'+field,required=True)
    benchmark=sub.add_parser('compare-trials');benchmark.add_argument('--trials',required=True);benchmark.add_argument('--out',required=True)
    merge=sub.add_parser('merge-packages');merge.add_argument('--brief',required=True);merge.add_argument('--story',required=True)
    merge.add_argument('--packages',nargs='+',required=True);merge.add_argument('--out',required=True)
    render_inputs=sub.add_parser('prepare-render-inputs');render_inputs.add_argument('--plan',required=True);render_inputs.add_argument('--out',required=True)
    upload=sub.add_parser('upload-assets',help='Approved upload-only phase; no generation')
    for field in ('manifest','approval','assets','ledger','out'):upload.add_argument('--'+field,required=True)
    upload.add_argument('--enable-live',action='store_true')
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
    unified.add_argument('--resume',action='store_true',help='Reuse content-addressed stages in this planning directory')
    unified.add_argument('--legacy-writer',action='store_true',help='Explicitly use the historical one-call writer')
    unified.add_argument('--max-repairs',type=int,choices=range(3),default=1)
    produce = sub.add_parser('produce')
    produce.add_argument('--package', required=True)
    produce.add_argument('--out', required=True)
    produce.add_argument('--ledger', help='Required shared private batch ledger path for live jobs')
    produce.add_argument('--approval', help='Exact per-run approval manifest token; not a secret key')
    produce.add_argument('--enable-live', action='store_true', help='Still requires matching approval and provider keys')
    produce.add_argument('--qa-models', nargs=2, help='Two distinct already-installed free local Ollama vision models; speech/lip-sync still need actual evidence')
    produce.add_argument('--backend', choices=['own','h3_join'], default='own')
    produce.add_argument('--resume',action='store_true',help='Cache unchanged shots/episodes and export a new immutable cut')
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
    load = lambda p: json.loads(Path(p).read_text(encoding='utf-8-sig'))
    if args.command=='prepare-render-inputs':
        from magicdrama.audiofirst.renderplan import prepare_render_inputs
        print(json.dumps(prepare_render_inputs(load(args.plan),args.out),indent=2));return
    if args.command=='upload-assets':
        import os
        from magicdrama.audiofirst.bridge import upload_inputs
        result=upload_inputs(load(args.manifest),load(args.approval),load(args.assets),args.ledger,args.out,
            {'magichour':os.environ.get('MAGICHOUR_IMAGE_VIDEO_KEY')} if args.enable_live else {},args.enable_live)
        print(json.dumps(result,indent=2));return
    if args.command=='merge-packages':
        from magicdrama.audiofirst.bridge import merge_packages
        result=merge_packages(load_brief(args.brief),load(args.story),[load(p) for p in args.packages])
        write_json(args.out,result);print(json.dumps(result,indent=2));return
    if args.command=='compare-trials':
        from magicdrama.audiofirst.benchmark import compare_trials
        result=compare_trials(load(args.trials));write_json(args.out,result);print(json.dumps(result,indent=2));return
    if args.command in ('storyboard','compile-render','media-package','animatic'):
        brief=load_brief(args.brief);story_data=load(args.story);validate_story(brief,story_data)
        if args.command=='storyboard':
            from magicdrama.audiofirst.preview import storyboard_preview
            result=storyboard_preview(brief,story_data,args.out,load(args.assets) if args.assets else None,load(args.tracks) if args.tracks else None)
        else:
            episode=next((e for e in story_data['episodes'] if e['id']==args.episode),None)
            if episode is None:parser.error('Unknown episode ID')
            if args.command=='compile-render':
                from magicdrama.audiofirst.renderplan import measured_track,compile_render_plan
                track=measured_track(episode,load(args.audio),load(args.alignment),load(args.audio_review))
                if track['seconds']>brief.get('max_episode_seconds',180):parser.error('Measured audio exceeds requested episode maximum')
                result=compile_render_plan(episode,track,load(args.renderer),args.connected,args.audio_mode,load(args.assets) if args.assets else None)
                destination=Path(args.out)
                if destination.exists():parser.error('Use a fresh compile output directory')
                write_json(destination/'track.json',track);write_json(destination/'render-plan.json',result)
            elif args.command=='media-package':
                from magicdrama.audiofirst.bridge import accepted_package
                result=accepted_package(brief,story_data,args.episode,load(args.track),load(args.plan),load(args.media));write_json(args.out,result)
            else:
                from magicdrama.audiofirst.preview import render_animatic
                result=render_animatic(episode,load(args.track),load(args.assets),args.out,args.ffmpeg)
        print(json.dumps(result,indent=2));return
    if args.command=='video-manifest':
        from magicdrama.audiofirst.bridge import video_manifest as build_manifest
        result=build_manifest(load(args.plan),load(args.images),load(args.accepted_images),load(args.uploads),load(args.quotes),args.run_id,args.batch_id)
        write_json(args.out,result);print(json.dumps(result,indent=2));return
    if args.command in ('stage-status','reconcile-stage'):
        from magicdrama.audiofirst.workflow import StageStore
        if not Path(args.state).is_file():parser.error('State database does not exist')
        with StageStore(args.state) as store:
            if args.command=='reconcile-stage':store.reconcile(args.stage,args.input_sha256,load(args.result),args.evidence)
            print(json.dumps(store.report(),indent=2))
        return
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
        result = media_run(load(args.package), args.out, load(args.approval) if args.approval else None, keys, args.enable_live, backend=args.backend, ledger_path=args.ledger, evaluators=evaluators,resume=args.resume)
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
        writer_workspace=None if args.legacy_writer else str(Path(args.out)/'writing')
        writer=cloud.staged(writer_workspace,args.max_repairs) if cloud and writer_workspace else cloud if cloud else LocalWriter(args.local_model,workspace=writer_workspace,max_repairs=args.max_repairs) if args.local_model else None
        result = run(load_brief(args.brief), args.out, load(args.story) if args.story else None,
                     args.previous_season, writer=writer if writer else (lambda request: write_draft(request['brief'],
                         {'series_id': request['brief']['series_id'], 'season': request['brief']['season']-1, 'canon': request['previous_canon']} if request['previous_canon'] else None)) if (args.template_draft or args.local_model or cloud) else None,
                     voices=load(args.voices) if args.voices else None,
                     exposure=load(args.exposure) if args.exposure else None, image_cap=args.image_cap,
                     soundtrack=load(args.soundtrack) if args.soundtrack else None,resume=args.resume)
        print(json.dumps(result, indent=2))
        return
    elif args.command == 'image-plan':
        result = image_first_plan(load_brief(args.brief), load(args.story), args.image_cap, load(args.exposure) if args.exposure else None)
    elif args.command == 'check-dialogue-timing':
        result = validate_dialogue_alignment(args.wav, load(args.response), load(args.inputs))
    elif args.command == 'flow':
        result = offline_flow(load_brief(args.brief), load(args.story))
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
        result = writing_request(load_brief(args.brief), previous)
    elif args.command == 'validate-story':
        result = validate_story(load_brief(args.brief), load(args.story))
    elif args.command == 'references':
        result = reference_plan(load_brief(args.brief), load(args.episodes))
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
