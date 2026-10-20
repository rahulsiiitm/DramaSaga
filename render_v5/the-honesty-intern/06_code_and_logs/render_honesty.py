                      
import json, os, re, subprocess, sys, time
import urllib.request
from pathlib import Path
import requests

BASE = "https://api.magichour.ai"
KEY = os.environ.get("MAGICHOUR_KEY", "")
assert KEY, "MAGICHOUR_KEY env missing"
WD = Path("/tmp/v3/honesty_render")
RUN = Path("/tmp/v3/honesty_run")
CAP = 4300
IMG_MODEL, IMG_COST = "nano-banana-2.1", 50
VID_MODEL, VID_RATE = "minimax-h3", 48         
RES, ASPECT = "720p", "9:16"
STYLE = ("Photoreal cinematic still, present-day Mumbai advertising agency Meridian, "
         "motivated natural light, mixed fluorescent and window daylight, candid documentary "
         "framing, slightly off-center, ordinary office clutter and wear, warm grounded tone, 9:16 vertical.")

def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
def H(): return {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

def post(path, payload, tries=2):
    for a in range(tries):
        try:
            r = requests.post(f"{BASE}{path}", headers=H(), json=payload, timeout=90)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(20 * (a + 1)); continue
            if r.status_code in (400, 402, 403):
                log(f"FATAL {r.status_code} on {path}: {r.text[:300]}")
                (WD / "PAUSED.json").write_text(json.dumps({"reason": f"api {r.status_code}", "body": r.text[:300]}))
                sys.exit(3)
            r.raise_for_status()
            return r.json()
        except (requests.ConnectionError, requests.Timeout):
            if a == tries - 1: raise
            time.sleep(15)
    r.raise_for_status()

def poll(kind, job_id, timeout_min=25):
    url = f"{BASE}/v1/{kind}-projects/{job_id}"
    for _ in range(timeout_min * 6):
        r = requests.get(url, headers=H(), timeout=30)
        if r.status_code == 200:
            d = r.json()
            if d.get("status") in ("complete", "error", "canceled"):
                return d
        time.sleep(10)
    raise TimeoutError(f"{kind} {job_id}")

def download(url, dest): urllib.request.urlretrieve(url, dest)
def ledger(rec):
    with open(WD / "credits_ledger.jsonl", "a") as f: f.write(json.dumps(rec) + "\n")
def ledger_sum():
    p = WD / "credits_ledger.jsonl"
    return sum(json.loads(l).get("credits", 0) for l in p.read_text().splitlines() if l.strip()) if p.exists() else 0
def check_cap():
    if ledger_sum() > CAP:
        (WD / "PAUSED.json").write_text(json.dumps({"reason": "cap exceeded", "total": ledger_sum()}))
        log(f"PAUSED: cap exceeded, total {ledger_sum()}"); sys.exit(2)

def upload_file(local, ext, typ):
    res = post("/v1/files/upload-urls", {"items": [{"extension": ext, "type": typ}]})
    item = res["items"][0]
    with open(local, "rb") as f:
        requests.put(item["upload_url"], data=f.read(), headers={"Content-Type": "application/octet-stream"}, timeout=120).raise_for_status()
    return item["file_path"]

def gen_image(prompt, name, inputs=None):
    if inputs:
        job = post("/v1/ai-image-editor", {"name": name, "model": IMG_MODEL, "assets": {"image_file_paths": inputs}, "style": {"prompt": prompt}})
    else:
        job = post("/v1/ai-image-generator", {"name": name, "image_count": 1, "model": IMG_MODEL, "aspect_ratio": ASPECT, "resolution": "1k", "style": {"prompt": prompt}})
    d = poll("image", job["id"])
    if d.get("status") != "complete": raise RuntimeError(f"image job {job['id']}: {d.get('status')}")
    return d

def gen_clip(frame_asset, prompt, seconds, name):
    job = post("/v1/image-to-video", {"name": name, "model": VID_MODEL, "resolution": RES,
                                      "audio": True, "end_seconds": seconds,
                                      "assets": {"image_file_path": frame_asset},
                                      "style": {"prompt": prompt}})
    d = poll("video", job["id"])
    if d.get("status") != "complete": raise RuntimeError(f"video job {job['id']}: {d.get('status')}")
    return d

CHARS = json.loads((RUN / "bible.json").read_text())["characters"]
LOCS = {
  "lobby": "Agency ground-floor glass lobby, security turnstile, elevator bank beyond, morning light through glass.",
  "elevator": "Office elevator interior, brushed steel, one mirrored panel, fluorescent ceiling light.",
  "office_floor": "Open-plan agency floor, rows of desks with dual monitors, a jammed printer, cold chai cups, Post-its, cluttered shelves.",
  "cabin": "CEO glass-walled cabin, clean desk with laptop, a photo frame lying face-down, blinds half-open, city haze outside.",
  "chai_stall": "Street chai stall downstairs, steaming kettle, glass tumblers, coin tin, crates and bins at the edges.",
  "pantry": "Small office pantry, chai machine, fridge with magnets, leftover birthday cake box on the counter.",
  "stairwell": "Bare concrete office stairwell, single tube light, painted railing, echo feel.",
}
LOC_MATCH = {
  "lobby": ["lobby", "turnstile", "security guard", "entrance"],
  "elevator": ["elevator", "lift"],
  "office_floor": ["open-plan", "desk", "printer", "stapl", "floor", "tracker", "laptop"],
  "cabin": ["cabin", "blinds", "intercom", "vikram's desk", "glass wall", "photo frame"],
  "chai_stall": ["chai stall", "stall", "vendor", "kettle"],
  "pantry": ["pantry", "fridge", "chai machine"],
  "stairwell": ["stairwell", "stairs"],
}

def main():
    for d in ("refs", "frames", "clips", "episodes"):
        (WD / d).mkdir(parents=True, exist_ok=True)
    manifest_p = WD / "refs" / "manifest.json"
    manifest = json.loads(manifest_p.read_text()) if manifest_p.exists() else {"chars": {}, "locs": {}}
    for c in CHARS:
        slug = re.sub(r"[^a-z0-9]+", "_", c["name"].lower()).strip("_")
        out = WD / "refs" / f"char_{slug}.png"
        if slug not in manifest["chars"]:
            d = gen_image(f"{STYLE} Character portrait: {c['name']}, {c['role']}, {c['physical']}. Neutral expression, face clearly visible.", f"ref-{slug}")
            download(d["downloads"][0]["url"], out)
            manifest["chars"][slug] = {"name": c["name"], "file": out.name, "credits": d.get("credits_charged", IMG_COST)}
            ledger({"job": f"ref_{slug}", "credits": d.get("credits_charged", IMG_COST), "est": IMG_COST})
            manifest_p.write_text(json.dumps(manifest, indent=1)); log(f"ref {slug} done ({d.get('credits_charged')} cr)"); check_cap()
    for slug, desc in LOCS.items():
        out = WD / "refs" / f"loc_{slug}.png"
        if slug not in manifest["locs"]:
            d = gen_image(f"{STYLE} Location plate, no people: {desc}", f"ref-{slug}")
            download(d["downloads"][0]["url"], out)
            manifest["locs"][slug] = {"file": out.name, "credits": d.get("credits_charged", IMG_COST)}
            ledger({"job": f"ref_{slug}", "credits": d.get("credits_charged", IMG_COST), "est": IMG_COST})
            manifest_p.write_text(json.dumps(manifest, indent=1)); log(f"ref {slug} done ({d.get('credits_charged')} cr)"); check_cap()
    assets_p = WD / "refs" / "mh_assets.json"
    assets = json.loads(assets_p.read_text()) if assets_p.exists() else {}
    for slug, rec in {**manifest["chars"], **manifest["locs"]}.items():
        if slug not in assets:
            assets[slug] = upload_file(WD / "refs" / rec["file"], "png", "image")
            assets_p.write_text(json.dumps(assets, indent=1)); log(f"uploaded ref {slug}")
                  
    script = json.loads((RUN / "ep01.v4.json").read_text())
    ep_spend, clip_paths, fails = 0, [], 0
    ep_done = WD / "episodes" / "HI_E01.mp4"
    if not ep_done.exists():
        for shot in script["shots"]:
            n = shot["n"]
            clip_p = WD / "clips" / f"HI_E01_S{n:02d}.mp4"
            frame_p = WD / "frames" / f"HI_E01_S{n:02d}.png"
            text = (shot["visual"] + " " + shot.get("camera", "") + " " + shot.get("micro_acting", "") + " " +
                    " ".join(d.get("character", "") for d in shot.get("dialogue", []))).lower()
            ref_inputs = [assets[s] for s in manifest["chars"]
                          if manifest["chars"][s]["name"].lower().split()[0] in text]
            for slug, kws in LOC_MATCH.items():
                if any(k in text for k in kws): ref_inputs.append(assets[slug]); break
            ref_inputs = ref_inputs[:3]
            try:
                if not frame_p.exists():
                    d = gen_image(f"{STYLE} {shot['visual']} Camera: {shot.get('camera','')}. Keep the referenced faces and wardrobe exactly consistent.",
                                  f"hi-e01s{n:02d}", inputs=ref_inputs or None)
                    download(d["downloads"][0]["url"], frame_p)
                    cr = d.get("credits_charged", IMG_COST); ep_spend += cr
                    ledger({"job": f"e01s{n:02d}_frame", "credits": cr, "est": IMG_COST})
                    log(f"E1 S{n} frame ({cr} cr)"); check_cap()
                frame_asset = upload_file(frame_p, "png", "image")
                dialogue = " ".join(f"{dd['character']} ({dd.get('voice','')}) says: \"{dd['line']}\"" for dd in shot.get("dialogue", []))
                vprompt = f"{shot['visual']} Camera: {shot.get('camera','')}. {dialogue} Photoreal grounded office drama, motivated natural light, natural lip sync dialogue audio.".strip()
                if not clip_p.exists():
                    d = gen_clip(frame_asset, vprompt, shot["seconds"], f"HI_E01_S{n:02d}")
                    download(d["downloads"][0]["url"], clip_p)
                    cr = d.get("credits_charged", shot["seconds"] * VID_RATE); ep_spend += cr
                    ledger({"job": f"e01s{n:02d}_clip", "credits": cr, "est": shot["seconds"] * VID_RATE})
                    log(f"E1 S{n} clip ({cr} cr)"); check_cap()
            except SystemExit: raise
            except Exception as e:
                fails += 1
                log(f"E1 S{n} FAILED: {type(e).__name__}: {str(e)[:200]}")
            clip_paths.append(clip_p)
        if fails > 3:
            (WD / "PAUSED.json").write_text(json.dumps({"reason": f"{fails} shot failures", "ep": 1}))
            log(f"PAUSED: {fails} shots failed"); sys.exit(2)
        have = [p for p in clip_paths if p.exists()]
        if len(have) == len(clip_paths):
            lst = WD / "clips" / "concat_e01.txt"
            lst.write_text("".join(f"file '{p}'\n" for p in have))
            subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(ep_done)],
                           check=True, capture_output=True)
            log(f"E1 stitched -> {ep_done.name}")
    (WD / "RENDER_DONE.json").write_text(json.dumps({"total_credits": ledger_sum()}))
    log(f"E1 DONE total {ledger_sum()} cr")

if __name__ == "__main__":
    main()

