import json

from .. import config
from ..clients.magichour import mh_image, mh_image_to_video, mh_lipsync
from ..governor import IMAGE_CR, LIPSYNC_CR_PER_FRAME, FPS, price_for
from ..ledgers import ledger_row
from .script import episode_script
from ..validators import validate_script

STOCK_VOICES = {"mina": "voice_f_warm_01", "junho": "voice_m_soft_01", "taeyang": "voice_m_polished_01", "han": "voice_m_low_01", "ari": "voice_f_bright_01"}

def lock_voices(workdir, brief):
    p = workdir / "voice_bible.csv"
    existing = p.read_text()
    for c in brief["characters"]:
        if STOCK_VOICES[c["id"]] not in existing:
            ledger_row(workdir, "voice_bible.csv", [STOCK_VOICES[c["id"]], c["id"], "en", "neutral", "", "20s", "clear", "mid", "normal", "soft", "neutral", "small", "studio", "", "stock", "", ""])

def tts_line(character_id, text):
    if config.DRY_RUN:
        return {"dry": True, "character": character_id, "voice": STOCK_VOICES[character_id], "text": text}
    raise NotImplementedError("wire the chatterbox endpoint on the first real run")

def character_master(spend, workdir, c):
    master_dir = workdir / "character_masters"
    master_dir.mkdir(exist_ok=True)
    p = master_dir / f"{c['id']}.json"
    if p.exists():
        return json.loads(p.read_text())
    prompt = f"Photoreal portrait, 9:16, neutral light, plain background: {c['imagined']}. Korean drama cast photo."
    job = spend.spend(f"image_master_{c['id']}", IMAGE_CR[config.MH_IMAGE_MODEL], mh_image, prompt, model=config.MH_IMAGE_MODEL)
    rec = {"character": c["id"], "prompt": prompt, "job": job}
    p.write_text(json.dumps(rec, indent=2))
    return rec

def render_episode(spend, workdir, brief, ep, model=None, tag=None):
    model = model or config.MH_VIDEO_MODEL
    tag = tag or f"{ep:02d}"
    assert config.MASTERS_APPROVED or config.DRY_RUN, "character masters must be approved first"
    script = episode_script(workdir, brief, ep)
    errs = validate_script(script, brief)
    assert not errs, errs
    out_dir = workdir / f"E{tag}"
    out_dir.mkdir(exist_ok=True)
    from .select import generate_with_selection
    for shot in script["shots"]:
        if shot["n"] in (1, len(script["shots"])):
            reference = "; ".join(c["imagined"] for c in brief["characters"])
            generate_with_selection(spend, f"E{tag}_shot{shot['n']}", reference, shot["visual"])
        else:
            spend.spend(f"E{tag}_shot{shot['n']}_frame", IMAGE_CR[config.MH_IMAGE_MODEL], mh_image, shot["visual"], ep=tag, model=config.MH_IMAGE_MODEL)
        spend.spend(f"E{tag}_shot{shot['n']}_video", shot["seconds"] * price_for(model, config.RESOLUTION), mh_image_to_video, model, "dry_frame_path", shot["visual"], shot["seconds"], ep=tag, model=model)
        if shot["dialogue"]:
            for d in shot["dialogue"]:
                tts_line(next(c["id"] for c in brief["characters"] if c["name"] == d["character"]), d["line"])
            spend.spend(f"E{tag}_shot{shot['n']}_lipsync", int(shot["seconds"] * FPS) * LIPSYNC_CR_PER_FRAME, mh_lipsync, "dry_video_path", "dry_audio_path", shot["seconds"], ep=tag, model="lip-sync")
    return out_dir

def ab_render_e1(spend, workdir, brief):
    for model in config.AB_MODELS:
        tag = "01_ab_" + model.replace("-", "_")
        out_dir = render_episode(spend, workdir, brief, 1, model=model, tag=tag)
        print("A/B variant done:", model, "->", out_dir)

