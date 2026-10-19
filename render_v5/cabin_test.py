                      
import json, os, subprocess, sys, time, urllib.request
from pathlib import Path
import requests

BASE="https://api.magichour.ai"; KEY=os.environ["MAGICHOUR_KEY"]
WD=Path("/tmp/v3/honesty_v5/render"); OLD=Path("/tmp/v3/honesty_render")
IMG_MODEL="nano-banana-2.1"; VID_MODEL="minimax-h3"; RES="720p"
STYLE=("Photoreal cinematic still, present-day Mumbai advertising agency Meridian, "
       "motivated natural light, mixed fluorescent and window daylight, candid documentary "
       "framing, slightly off-center, ordinary office clutter and wear, warm grounded tone, 9:16 vertical.")
LEDGER=WD/"credits_ledger.jsonl"
def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
def H(): return {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
def ledger(rec):
    with open(LEDGER,"a") as f: f.write(json.dumps(rec)+"\n")
def post(path, payload, tries=2):
    for a in range(tries):
        try:
            r=requests.post(f"{BASE}{path}", headers=H(), json=payload, timeout=90)
            if r.status_code in (429,500,502,503,504): time.sleep(20*(a+1)); continue
            if r.status_code in (400,402,403):
                log(f"FATAL {r.status_code} {path}: {r.text[:300]}"); sys.exit(3)
            r.raise_for_status(); return r.json()
        except (requests.ConnectionError, requests.Timeout):
            if a==tries-1: raise
            time.sleep(15)
def poll(kind, jid, timeout_min=25):
    for _ in range(timeout_min*6):
        d=requests.get(f"{BASE}/v1/{kind}-projects/{jid}", headers=H(), timeout=30).json()
        if d.get("status") in ("complete","error","canceled"): return d
        time.sleep(10)
    raise TimeoutError(jid)
def upload(local, ext, typ):
    res=post("/v1/files/upload-urls", {"items":[{"extension":ext,"type":typ}]})
    it=res["items"][0]
    with open(local,"rb") as f:
        requests.put(it["upload_url"], data=f.read(), headers={"Content-Type":"application/octet-stream"}, timeout=120).raise_for_status()
    return it["file_path"]
def download(url, dest): urllib.request.urlretrieve(url, dest)

sc = [x for x in json.load(open("/tmp/v3/honesty_v5/ep01.v5.json"))["scenes"] if x["n"]==4][0]
SECONDS = sc["seconds"] + 2                     
frame_p = WD/"frames"/"HI_E01_S04.png"
if not frame_p.exists():
    refs = [upload(OLD/"refs"/"char_anu_rao.png","png","image"),
            upload(OLD/"refs"/"char_vikram_sethi.png","png","image"),
            upload(OLD/"refs"/"loc_cabin.png","png","image")]
    kp = (f"{STYLE} {sc['keyframe_visual']} Camera: {sc['camera']}. "
          "Anu Rao wears the SAME outfit as her reference image (mustard kurti, navy blazer ON, canvas tote). "
          "Vikram Sethi wears the SAME outfit as his reference image. Keep both faces exactly consistent with the references. "
          "No readable text or numbers anywhere in the frame, no charts, no screens with legible content.")
    job=post("/v1/ai-image-editor", {"name":"hi-e01s04-v5","model":IMG_MODEL,"assets":{"image_file_paths":refs},"style":{"prompt":kp}})
    d=poll("image", job["id"])
    if d.get("status")!="complete": raise RuntimeError(f"image: {d.get('status')}")
    download(d["downloads"][0]["url"], frame_p)
    ledger({"job":"e01s04_frame_v5","credits":d.get("credits_charged",50)}); log(f"keyframe done ({d.get('credits_charged')} cr)")
clip_p = WD/"clips"/"HI_E01_S04_test.mp4"
if not clip_p.exists():
    fa = upload(frame_p,"png","image")
    dlg = " ".join(f"{dd['character']} ({dd['voice']}) says exactly: \"{dd['line']}\"" for dd in sc["dialogue"])
    vp = (f"{sc['keyframe_visual']} Camera: {sc['camera']}. {sc['micro_acting']}. "
          f"{dlg} These are the ONLY spoken lines - no other speech, no greetings, no added words. "
          "Photoreal grounded office drama, natural lip sync, natural emotion matching the lines, "
          "no readable on-screen text, no charts.")
    job=post("/v1/image-to-video", {"name":"HI_E01_S04_test","model":VID_MODEL,"resolution":RES,
        "audio":True,"end_seconds":SECONDS,"assets":{"image_file_path":fa},"style":{"prompt":vp}})
    log(f"clip job {job['id']} submitted ({SECONDS}s)")
    d=poll("video", job["id"])
    if d.get("status")!="complete": raise RuntimeError(f"video: {d.get('status')}")
    download(d["downloads"][0]["url"], clip_p)
    ledger({"job":"e01s04_clip_v5_test","credits":d.get("credits_charged",SECONDS*48)}); log(f"clip done ({d.get('credits_charged')} cr)")
probe=subprocess.run(["ffprobe","-v","quiet","-print_format","json","-show_format","-show_streams",str(clip_p)],capture_output=True,text=True).stdout
pq=json.loads(probe)
dur=float(pq["format"]["duration"]); has_audio=any(s["codec_type"]=="audio" for s in pq["streams"])
for t,tag in ((0.5,"start"),(dur/2,"mid"),(max(dur-2.5,1),"end")):
    subprocess.run(["ffmpeg","-y","-ss",str(t),"-i",str(clip_p),"-frames:v","1",str(WD/"qa"/f"S04_{tag}.png")],check=True,capture_output=True)
subprocess.run(["ffmpeg","-y","-i",str(clip_p),"-vn","-ac","1","-ar","16000",str(WD/"qa"/"S04.wav")],check=True,capture_output=True)
(WD/"qa"/"S04_probe.json").write_text(json.dumps({"duration":dur,"audio":has_audio,"expected":SECONDS}))
log(f"QA artifacts: dur={dur:.2f}s audio={has_audio}")
print("CABIN-TEST-DONE", flush=True)
