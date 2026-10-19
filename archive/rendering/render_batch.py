                      
import json, os, re, subprocess, sys, threading, time
import urllib.request
from pathlib import Path
import requests

BASE = "https://api.magichour.ai"
KEY = os.environ.get("MAGICHOUR_KEY", "")
assert KEY, "MAGICHOUR_KEY env missing"
WD = Path("/tmp/v3/honesty_render")
RUN = Path("/tmp/v3/honesty_run")
CAP = 41000
IMG_MODEL, IMG_COST = "nano-banana-2.1", 50
VID_MODEL, VID_RATE = "minimax-h3", 48
RES, ASPECT = "720p", "9:16"
WORKERS = int(os.environ.get("RB_WORKERS", "3"))
BATCH = os.environ.get("RB_BATCH", "2-5")                       
STYLE = ("Photoreal cinematic still, present-day Mumbai advertising agency Meridian, "
         "motivated natural light, mixed fluorescent and window daylight, candid documentary "
         "framing, slightly off-center, ordinary office clutter and wear, warm grounded tone, 9:16 vertical.")
WARDROBE = {
 "anu": "Anu Rao EXACT wardrobe: oversized dark blazer worn over a patterned kurti, shoulder-length wavy dark hair half-tied back, small gold studs, canvas tote, scuffed white sneakers, ID lanyard.",
 "vikram": "Vikram Sethi EXACT wardrobe: crisp pale-blue formal shirt, rimless glasses, expensive steel watch, silver-flecked short hair, 45 years old.",
 "priya": "Priya Nair EXACT wardrobe: neutral linen shirt, straight dark hair in a low bun, ID lanyard, 27 years old.",
 "arjun": "Arjun Malhotra EXACT wardrobe: slim-fit formal shirt, shiny ID lanyard, groomed stubble, gym-fit build, 28 years old.",
}
LOCS = {
  "lobby": ["lobby", "turnstile", "security guard", "entrance"],
  "elevator": ["elevator", "lift"],
  "office_floor": ["open-plan", "desk", "printer", "stapl", "floor", "tracker", "laptop"],
  "cabin": ["cabin", "blinds", "intercom", "vikram's desk", "glass wall", "photo frame"],
  "chai_stall": ["chai stall", "stall", "vendor", "kettle"],
  "pantry": ["pantry", "fridge", "chai machine"],
  "stairwell": ["stairwell", "stairs"],
}
_lock = threading.Lock()
def log(m):
    with _lock: print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
def H(): return {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

def post(path, payload, tries=2):
    for a in range(tries):
        try:
            r = requests.post(f"{BASE}{path}", headers=H(), json=payload, timeout=90)
            if r.status_code == 429:
                log(f"429 RATE LIMIT on {path}"); time.sleep(30 * (a + 1)); continue
            if r.status_code in (500, 502, 503, 504):
                time.sleep(20 * (a + 1)); continue
            if r.status_code in (400, 402, 403):
                log(f"FATAL {r.status_code} on {path}: {r.text[:300]}")
                (WD / "PAUSED.json").write_text(json.dumps({"reason": f"api {r.status_code}", "body": r.text[:300]}))
                os._exit(3)
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
    with _lock:
        with open(WD / "credits_ledger.jsonl", "a") as f: f.write(json.dumps(rec) + "\n")
def ledger_sum():
    p = WD / "credits_ledger.jsonl"
    return sum(json.loads(l).get("credits", 0) for l in p.read_text().splitlines() if l.strip()) if p.exists() else 0
def check_cap():
    if ledger_sum() > CAP:
        (WD / "PAUSED.json").write_text(json.dumps({"reason": "cap exceeded", "total": ledger_sum()}))
        log(f"PAUSED: cap exceeded {ledger_sum()}"); os._exit(2)

def upload_file(local, ext, typ):
    res = post("/v1/files/upload-urls", {"items": [{"extension": ext, "type": typ}]})
    item = res["items"][0]
    with open(local, "rb") as f:
        requests.put(item["upload_url"], data=f.read(), headers={"Content-Type": "application/octet-stream"}, timeout=120).raise_for_status()
    return item["file_path"]

def gen_image(prompt, name, inputs=None):
    payload = {"name": name, "model": IMG_MODEL, "style": {"prompt": prompt}}
    if inputs:
        payload["assets"] = {"image_file_paths": inputs}
        job = post("/v1/ai-image-editor", payload)
    else:
        payload.update({"image_count": 1, "aspect_ratio": ASPECT, "resolution": "1k"})
        job = post("/v1/ai-image-generator", payload)
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

def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-show_entries", "stream=codec_type", "-of", "json", str(path)],
                       capture_output=True, text=True)
    d = json.loads(r.stdout or "{}")
    dur = float(d.get("format", {}).get("duration", 0))
    has_audio = any(s.get("codec_type") == "audio" for s in d.get("streams", []))
    return dur, has_audio

def do_shot(ep, shot, assets, manifest):
    n, secs = shot["n"], shot["seconds"]
    clip_p = WD / "clips" / f"HI_E{ep:02d}_S{n:02d}.mp4"
    frame_p = WD / "frames" / f"HI_E{ep:02d}_S{n:02d}.png"
    text = (shot["visual"] + " " + shot.get("camera", "") + " " + shot.get("micro_acting", "") + " " +
            " ".join(d.get("character", "") for d in shot.get("dialogue", []))).lower()
    chars_in = [s for s in ("anu", "vikram", "priya", "arjun") if s in text]
    ref_inputs = [assets[f"{s}_rao" if s == "anu" else f"{s}_sethi" if s == "vikram" else f"{s}_nair" if s == "priya" else f"{s}_malhotra"] for s in chars_in]
    for slug, kws in LOCS.items():
        if any(k in text for k in kws): ref_inputs.append(assets[slug]); break
    ref_inputs = ref_inputs[:3]
    wardrobe = " ".join(WARDROBE[s] for s in chars_in)
    attempts = 0
    while True:
        attempts += 1
        try:
            if not frame_p.exists() or attempts > 1:
                d = gen_image(f"{STYLE} {shot['visual']} Camera: {shot.get('camera','')}. {wardrobe} Keep the referenced faces, ages and wardrobe exactly consistent with the reference images.",
                              f"hi-e{ep:02d}s{n:02d}", inputs=ref_inputs or None)
                download(d["downloads"][0]["url"], frame_p)
                cr = d.get("credits_charged", IMG_COST)
                ledger({"job": f"e{ep:02d}s{n:02d}_frame", "credits": cr, "est": IMG_COST})
                log(f"E{ep} S{n} frame ({cr} cr) try{attempts}"); check_cap()
            frame_asset = upload_file(frame_p, "png", "image")
            dialogue = " ".join(f"{dd['character']} ({dd.get('voice','')}) says: \"{dd['line']}\"" for dd in shot.get("dialogue", []))
            vprompt = f"{shot['visual']} Camera: {shot.get('camera','')}. {dialogue} {wardrobe} Photoreal grounded office drama, motivated natural light, natural lip sync dialogue audio.".strip()
            d = gen_clip(frame_asset, vprompt, secs, f"HI_E{ep:02d}_S{n:02d}")
            download(d["downloads"][0]["url"], clip_p)
            cr = d.get("credits_charged", secs * VID_RATE)
            ledger({"job": f"e{ep:02d}s{n:02d}_clip", "credits": cr, "est": secs * VID_RATE})
            dur, has_audio = probe(clip_p)
            log(f"E{ep} S{n} clip ({cr} cr, {dur:.1f}s, audio={has_audio}) try{attempts}"); check_cap()
            if not has_audio or dur < secs - 1.5:
                raise RuntimeError(f"bad probe dur={dur:.1f} audio={has_audio}")
            with _lock:
                manifest[f"S{n:02d}"] = {"frame": frame_p.name, "clip": clip_p.name, "credits": cr, "dur": dur, "audio": has_audio}
            return True
        except SystemExit: raise
        except Exception as e:
            log(f"E{ep} S{n} FAILED try{attempts}: {type(e).__name__}: {str(e)[:180]}")
            if attempts >= 2:
                with _lock: manifest[f"S{n:02d}"] = {"error": str(e)[:200], "tries": attempts}
                return False
            frame_p.unlink(missing_ok=True)                             
            time.sleep(10)

def stitch(ep, script):
    lst = WD / "clips" / f"concat_e{ep:02d}.txt"
    trimmed = []
    for shot in script["shots"]:
        n, secs = shot["n"], shot["seconds"]
        src = WD / "clips" / f"HI_E{ep:02d}_S{n:02d}.mp4"
        dst = WD / "clips" / f"HI_E{ep:02d}_S{n:02d}_trim.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-t", str(secs),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(dst)],
                       check=True, capture_output=True)
        trimmed.append(dst)
    lst.write_text("".join(f"file '{p}'\n" for p in trimmed))
    out = WD / "episodes" / f"HI_E{ep:02d}.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)],
                   check=True, capture_output=True)
    dur, has_audio = probe(out)
    log(f"E{ep} stitched -> {out.name} ({dur:.1f}s, audio={has_audio})")
    return out, dur

def contact_sheet(ep):
    frames = sorted((WD / "frames").glob(f"HI_E{ep:02d}_S*.png"))
    if len(frames) < 10: return None
    out = WD / "frames" / f"HI_E{ep:02d}_contact.jpg"
    subprocess.run(["ffmpeg", "-y", "-v", "error"] + [a for f in frames for a in ("-i", str(f))] +
                   ["-filter_complex", f"concat=n={len(frames)}:v=1:a=0,fps=1,scale=360:-1,tile=5x2", "-frames:v", "1", str(out)],
                   check=True, capture_output=True)
    return out

def main():
    for d in ("refs", "frames", "clips", "episodes"):
        (WD / d).mkdir(parents=True, exist_ok=True)
    assets = json.loads((WD / "refs" / "mh_assets.json").read_text())
    a, b = (int(x) for x in BATCH.split("-"))
    reroll = os.environ.get("RB_REROLL", "")                  
    reroll_shots = {}
    for part in filter(None, reroll.split(",")):
        e, s = part.split(":"); reroll_shots.setdefault(int(e), set()).add(int(s))
    for ep in range(a, b + 1):
        script = json.loads((RUN / f"ep{ep:02d}.v4.json").read_text())
        man_p = WD / f"qc_e{ep:02d}.json"
        manifest = json.loads(man_p.read_text()) if man_p.exists() else {}
        shots = script["shots"]
        if reroll_shots.get(ep):
            shots = [s for s in shots if s["n"] in reroll_shots[ep]]
            for s in shots:
                (WD / "clips" / f"HI_E{ep:02d}_S{s['n']:02d}.mp4").unlink(missing_ok=True)
                (WD / "frames" / f"HI_E{ep:02d}_S{s['n']:02d}.png").unlink(missing_ok=True)
        todo = [s for s in shots if not (WD / "clips" / f"HI_E{ep:02d}_S{s['n']:02d}.mp4").exists() or s["n"] in reroll_shots.get(ep, set())]
        if todo:
            log(f"E{ep}: {len(todo)} shots to render")
            results = []
            tl = threading.Lock()
            def worker():
                while True:
                    with tl:
                        if not todo: return
                        s = todo.pop(0)
                    results.append(do_shot(ep, s, assets, manifest))
                    man_p.write_text(json.dumps(manifest, indent=1))
            threads = [threading.Thread(target=worker) for _ in range(WORKERS)]
            for t in threads: t.start()
            for t in threads: t.join()
        ok = sum(1 for s in script["shots"] if (WD / "clips" / f"HI_E{ep:02d}_S{s['n']:02d}.mp4").exists())
        cs = contact_sheet(ep)
        log(f"E{ep} shots present {ok}/10, contact sheet: {cs}")
        if ok == 10 and not reroll_shots.get(ep):
            out, dur = stitch(ep, script)
            (WD / f"qc_e{ep:02d}.json").write_text(json.dumps({**manifest, "episode": out.name, "dur": dur}, indent=1))
    log(f"BATCH {BATCH} done, total ledger {ledger_sum()} cr")

if __name__ == "__main__":
    main()
