                      
import json, os, re, subprocess, sys, time
import urllib.request
from pathlib import Path

import requests

BASE = "https://api.magichour.ai"
KEY = os.environ.get("MAGICHOUR_KEY", "")
assert KEY, "MAGICHOUR_KEY env missing"
WD = Path("/tmp/v3/neon_render")
LAB = Path("/tmp/v3/serieslab_run/series_lab/neon-shadows")
EP_CAP, BATCH_CAP = 3000, 30000
PLAN_E1, PLAN_EP = 2400, 2150
IMG_MODEL, IMG_COST = "nano-banana-2.1", 50
VID_MODEL, VID_RATE = "minimax-h3", 24
AB_MODEL = "ltx-2.5"
RES, ASPECT = "480p", "9:16"
STYLE = ("Photoreal cinematic still, cyberpunk noir, Neo-Osaka 2087, perpetual night, "
         "rain-slicked neon streets, palette of blues, pinks and harsh whites, 9:16 vertical.")

def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)

def H(): return {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

def post(path, payload, tries=3):
    for a in range(tries):
        try:
            r = requests.post(f"{BASE}{path}", headers=H(), json=payload, timeout=90)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(20 * (a + 1)); continue
            r.raise_for_status()
            return r.json()
        except (requests.ConnectionError, requests.Timeout) as e:
            if a == tries - 1: raise
            time.sleep(15 * (a + 1))
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

def download(url, dest):
    urllib.request.urlretrieve(url, dest)

def ledger(rec):
    with open(WD / "credits_ledger.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")

def ledger_sum():
    p = WD / "credits_ledger.jsonl"
    if not p.exists(): return 0
    return sum(json.loads(l).get("credits", 0) for l in p.read_text().splitlines() if l.strip())

def check_caps(ep_spend, ep):
    if ep_spend > EP_CAP or ledger_sum() > BATCH_CAP:
        (WD / "PAUSED.json").write_text(json.dumps({"reason": "cap exceeded", "ep": ep, "ep_spend": ep_spend, "total": ledger_sum()}))
        log(f"PAUSED: ep{ep} spend {ep_spend}, total {ledger_sum()}")
        sys.exit(2)

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
    if d.get("status") != "complete":
        raise RuntimeError(f"image job {job['id']}: {d.get('status')}")
    return d

def gen_clip(frame_asset, prompt, seconds, model, name):
    job = post("/v1/image-to-video", {"name": name, "model": model, "resolution": RES,
                                      "audio": True, "end_seconds": seconds,
                                      "assets": {"image_file_path": frame_asset},
                                      "style": {"prompt": prompt}})
    d = poll("video", job["id"])
    if d.get("status") != "complete":
        raise RuntimeError(f"video job {job['id']}: {d.get('status')}")
    return d

def main():
    for d in ("refs", "frames", "clips", "episodes", "code_snapshot"):
        (WD / d).mkdir(parents=True, exist_ok=True)
    concept = json.loads((LAB / ".." / "concepts.json").resolve().read_text())
    concept = [c for c in concept if c["slug"] == "neon-shadows"][0]
    chars = concept["characters"]
                                             
    manifest_p = WD / "refs" / "manifest.json"
    manifest = json.loads(manifest_p.read_text()) if manifest_p.exists() else {"chars": {}, "locs": {}}
    for c in chars:
        slug = re.sub(r"[^a-z0-9]+", "_", c["name"].lower()).strip("_")
        out = WD / "refs" / f"char_{slug}.png"
        if slug not in manifest["chars"]:
            d = gen_image(f"{STYLE} Character portrait: {c['name']}, {c['role']}, {c['physical']}. Neutral expression, face clearly visible.",
                          f"ref-{slug}")
            download(d["downloads"][0]["url"], out)
            manifest["chars"][slug] = {"name": c["name"], "file": out.name, "credits": d.get("credits_charged", IMG_COST)}
            ledger({"job": f"ref_{slug}", "credits": d.get("credits_charged", IMG_COST), "est": IMG_COST})
            manifest_p.write_text(json.dumps(manifest, indent=1))
            log(f"ref {slug} done ({d.get('credits_charged')} cr)")
    loc_defs = {
        "neon_street": "Rain-slicked neon megacity street at night, giant holographic ads, puddles reflecting pink and blue signs.",
        "clinic": "Clandestine back-alley memory clinic interior, neon tubing, surgical chair with neural headset, blue-white glare.",
        "office": "Corporate executive office high above the city at night, floor-to-ceiling windows over neon skyline, cold white light."}
    for slug, desc in loc_defs.items():
        out = WD / "refs" / f"loc_{slug}.png"
        if slug not in manifest["locs"]:
            d = gen_image(f"{STYLE} Location plate, no people: {desc}", f"ref-{slug}")
            download(d["downloads"][0]["url"], out)
            manifest["locs"][slug] = {"file": out.name, "credits": d.get("credits_charged", IMG_COST)}
            ledger({"job": f"ref_{slug}", "credits": d.get("credits_charged", IMG_COST), "est": IMG_COST})
            manifest_p.write_text(json.dumps(manifest, indent=1))
            log(f"ref {slug} done ({d.get('credits_charged')} cr)")
                                                     
    assets_p = WD / "refs" / "mh_assets.json"
    assets = json.loads(assets_p.read_text()) if assets_p.exists() else {}
    for slug, rec in {**{k: v for k, v in manifest["chars"].items()}, **manifest["locs"]}.items():
        if slug not in assets:
            assets[slug] = upload_file(WD / "refs" / rec["file"], "png", "image")
            assets_p.write_text(json.dumps(assets, indent=1))
            log(f"uploaded ref {slug}")
                            
    loc_match = {"neon_street": ["street", "alley", "rain", "road", "market", "neon sign", "holograph"],
                 "clinic": ["clinic", "surgical", "chair", "memory lab", "procedure"],
                 "office": ["office", "voss", "tower", "window", "skyline", "corporate"]}
    for ep in range(1, 11):
        ep_spend = 0
        script = json.loads((LAB / f"ep{ep:02d}.json").read_text())
        ep_done = WD / "episodes" / f"NS_E{ep:02d}.mp4"
        if ep_done.exists(): continue
        clip_paths, fails = [], 0
        for shot in script["shots"]:
            n = shot["n"]
            clip_p = WD / "clips" / f"NS_E{ep:02d}_S{n:02d}.mp4"
            frame_p = WD / "frames" / f"NS_E{ep:02d}_S{n:02d}.png"
            text = (shot["visual"] + " " + shot.get("camera", "") + " " +
                    " ".join(d.get("character", "") for d in shot.get("dialogue", []))).lower()
            ref_inputs = [assets[s] for s in manifest["chars"] if
                          manifest["chars"][s]["name"].lower().split()[0] in text or manifest["chars"][s]["name"].lower() in text]
            for slug, kws in loc_match.items():
                if any(k in text for k in kws):
                    ref_inputs.append(assets[slug]); break
            ref_inputs = ref_inputs[:3]
            try:
                if not frame_p.exists():
                    d = gen_image(f"{STYLE} {shot['visual']} Camera: {shot.get('camera','')}. Keep the referenced faces and wardrobe exactly consistent.",
                                  f"e{ep:02d}s{n:02d}", inputs=ref_inputs or None)
                    download(d["downloads"][0]["url"], frame_p)
                    cr = d.get("credits_charged", IMG_COST); ep_spend += cr
                    ledger({"job": f"e{ep:02d}s{n:02d}_frame", "credits": cr, "est": IMG_COST})
                    log(f"E{ep} S{n} frame ({cr} cr)")
                frame_asset = upload_file(frame_p, "png", "image")
                dialogue = " ".join(f"{dd['character']} says: \"{dd['line']}\"" for dd in shot.get("dialogue", []))
                vprompt = f"{shot['visual']} Camera: {shot.get('camera','')}. {dialogue} Photoreal cyberpunk noir, neon palette, natural lip sync dialogue audio.".strip()
                if not clip_p.exists():
                    d = gen_clip(frame_asset, vprompt, shot["seconds"], VID_MODEL, f"NS_E{ep:02d}_S{n:02d}")
                    download(d["downloads"][0]["url"], clip_p)
                    cr = d.get("credits_charged", shot["seconds"] * VID_RATE); ep_spend += cr
                    ledger({"job": f"e{ep:02d}s{n:02d}_clip", "credits": cr, "est": shot["seconds"] * VID_RATE})
                    log(f"E{ep} S{n} clip ({cr} cr)")
                if ep == 1 and n == 1:
                    ab_p = WD / "clips" / "NS_E01_S01_ltx25.mp4"
                    if not ab_p.exists():
                        d = gen_clip(frame_asset, vprompt, shot["seconds"], AB_MODEL, "NS_E01_S01_ltx25")
                        download(d["downloads"][0]["url"], ab_p)
                        cr = d.get("credits_charged", shot["seconds"] * VID_RATE); ep_spend += cr
                        ledger({"job": "e01s01_clip_ltx25", "credits": cr, "est": shot["seconds"] * VID_RATE})
                        log(f"E1 S1 A/B ltx-2.5 clip ({cr} cr)")
            except Exception as e:
                fails += 1
                log(f"E{ep} S{n} FAILED: {type(e).__name__}: {str(e)[:200]}")
            clip_paths.append(clip_p)
            check_caps(ep_spend, ep)
        if fails > 3:
            (WD / "PAUSED.json").write_text(json.dumps({"reason": f"{fails} shot failures", "ep": ep}))
            log(f"PAUSED: {fails} shots failed in E{ep}"); sys.exit(2)
        have = [p for p in clip_paths if p.exists()]
        if len(have) == len(clip_paths):
            lst = WD / "clips" / f"concat_e{ep:02d}.txt"
            lst.write_text("".join(f"file '{p}'\n" for p in have))
            subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(ep_done)],
                           check=True, capture_output=True)
            log(f"E{ep} stitched -> {ep_done.name}")
        check_caps(ep_spend, ep)
    (WD / "RENDER_DONE.json").write_text(json.dumps({"total_credits": ledger_sum()}))
    log(f"ALL DONE total {ledger_sum()} cr")

if __name__ == "__main__":
    main()

