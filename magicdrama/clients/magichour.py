import time
import requests

from .. import config
from ..retry import call_with_retries

def mh_post(path, payload):
    if config.DRY_RUN:
        return {"dry": True, "id": "dry-job", "credits_charged": 0, "status": "complete", "downloads": []}
    key = _key()
    r = call_with_retries(lambda: requests.post(f"{config.MH_BASE}{path}", headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json=payload, timeout=60))
    r.raise_for_status()
    return r.json()

def _key():
    from .nvidia import get_key
    key = get_key("MAGICHOUR_KEY")
    assert key, "MAGICHOUR_KEY missing"
    return key

def mh_poll(poll_url, job_id):
    if config.DRY_RUN:
        return {"status": "complete", "downloads": [{"url": "dry://example"}], "credits_charged": 0}
    for _ in range(240):
        r = call_with_retries(lambda: requests.get(f"{config.MH_BASE}{poll_url}/{job_id}", headers={"Authorization": f"Bearer {_key()}"}, timeout=30))
        r.raise_for_status()
        data = r.json()
        if data.get("status") in ("complete", "error", "canceled"):
            return data
        time.sleep(5)
    raise TimeoutError(job_id)

def mh_image(prompt, count=1):
    return mh_post("/v1/ai-image-generator", {"image_count": count, "orientation": "portrait", "model": config.MH_IMAGE_MODEL, "style": {"prompt": prompt}})

def mh_image_to_video(model, image_path, prompt, seconds):
    return mh_post("/v1/image-to-video", {"model": model, "resolution": config.RESOLUTION, "aspect_ratio": config.ASPECT, "end_seconds": seconds, "name": "microdrama", "image": {"file_path": image_path}, "style": {"prompt": prompt}})

def mh_lipsync(video_path, audio_path, seconds):
    return mh_post("/v1/lip-sync", {"name": "microdrama-lipsync", "assets": {"video_file_path": video_path, "audio_file_path": audio_path}, "start_seconds": 0, "end_seconds": seconds})

def verify_models():
    if config.DRY_RUN:
        return {"dry": True, "note": "model list check runs on the first real run"}
    try:
        r = call_with_retries(lambda: requests.get(f"{config.MH_BASE}/v1/models", headers={"Authorization": f"Bearer {_key()}"}, timeout=30))
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e), "note": "no list endpoint answered; confirm slugs with a 1-second test job per AB model before rendering"}

