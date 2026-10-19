import hashlib
import json
from datetime import datetime, timezone

from . import config
from .ledgers import ledger_row

class PriceQuoteRequired(ValueError):
    pass

def price_for(model, resolution):
    try:
        return VIDEO_CR_PER_SEC[model][resolution]
    except KeyError:
        raise PriceQuoteRequired(f"no verified price for {model} at {resolution}; add it to VIDEO_CR_PER_SEC from a live source before spending")

VIDEO_CR_PER_SEC = {"ltx-2.5": {"480p": 24, "720p": 48, "1080p": 72}, "ltx-2.3": {"480p": 24, "720p": 48, "1080p": 72}, "minimax-h3": {"480p": 24, "720p": 48, "1080p": 72}, "wan-2.2": {"480p": 24, "720p": 48, "1080p": 72}, "wan-3.0": {"480p": 48, "720p": 96, "1080p": 144}, "kling-3.0": {"720p": 48, "1080p": 72}}
IMAGE_CR = {"flux-schnell": 5, "qwen-edit": 10}
LIPSYNC_CR_PER_FRAME = 1
FPS = 24

def estimate_episode_credits(shots, dialogue_seconds, n_images, model=None):
    model = model or config.MH_VIDEO_MODEL
    video = sum(shots) * price_for(model, config.RESOLUTION)
    images = n_images * IMAGE_CR[config.MH_IMAGE_MODEL]
    lipsync = int(dialogue_seconds * FPS) * LIPSYNC_CR_PER_FRAME
    return {"video": video, "images": images, "lipsync": lipsync, "total": video + images + lipsync}

class Spend:
    def __init__(self, workdir):
        self.workdir = workdir
        self.batch = 0
        self.episodes = {}

    def spend(self, job_desc, est_credits, fn, *a, ep=None, model="", **k):
        key = hashlib.sha256(f"{job_desc}|{est_credits}|{json.dumps(k, sort_keys=True, default=str)}".encode()).hexdigest()[:16]
        gj = self.workdir / "generation_jobs.csv"
        if gj.exists() and key in gj.read_text():
            return {"id": key, "status": "complete", "resumed": True, "credits_charged": 0}
        ep_spent = self.episodes.get(ep, 0)
        if ep is not None and ep_spent + est_credits > config.EPISODE_CAP_CREDITS:
            raise RuntimeError(f"episode cap: {job_desc} would push E{ep} over {config.EPISODE_CAP_CREDITS}")
        if self.batch + est_credits > config.BATCH_CAP_CREDITS:
            raise RuntimeError(f"batch cap: {job_desc} would push the batch over {config.BATCH_CAP_CREDITS}")
        ts = datetime.now(timezone.utc).isoformat()
        result = fn(*a, **k)
        charged = est_credits if config.DRY_RUN else (result.get("credits_charged", 0) if isinstance(result, dict) else 0)
        self.batch += charged
        if ep is not None:
            self.episodes[ep] = ep_spent + charged
        ledger_row(self.workdir, "generation_jobs.csv", [key, job_desc, "", "magichour", model or config.MH_VIDEO_MODEL, "render", key, key, "v3.3", "", "", "", "", "operator-supplied", est_credits, "credits", "complete", 100, ts, ts, ts, "", "", 0, 2, "", "", "", "", "pending"])
        ledger_row(self.workdir, "spend_ledger.csv", [key, job_desc, "magichour", model or config.MH_VIDEO_MODEL, "render", "", config.RESOLUTION, "", est_credits, charged, "credits", "", "complete", "", "", ts, ts, "operator-supplied", key, "", "", ts, ""])
        return result

