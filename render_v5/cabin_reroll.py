                      
import json, os, subprocess, sys, time, urllib.request
from pathlib import Path
import requests
BASE="https://api.magichour.ai"; KEY=os.environ["MAGICHOUR_KEY"]
WD=Path("/tmp/v3/honesty_v5/render")
def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
def H(): return {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
def post(path, payload, tries=2):
    for a in range(tries):
        try:
            r=requests.post(f"{BASE}{path}", headers=H(), json=payload, timeout=90)
            if r.status_code in (429,500,502,503,504): time.sleep(20*(a+1)); continue
            if r.status_code in (400,402,403): log(f"FATAL {r.status_code}: {r.text[:300]}"); sys.exit(3)
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

sc=[x for x in json.load(open("/tmp/v3/honesty_v5/ep01.v5.json"))["scenes"] if x["n"]==4][0]
fa=upload(WD/"frames"/"HI_E01_S04.png","png","image")
dlg=" ".join(f"{dd['character']} ({dd['voice']}) says exactly: \"{dd['line']}\"" for dd in sc["dialogue"])
vp=("Continue this exact scene: Vikram seated behind the cabin desk, Anu across from him, a white envelope on the desk between them, a photo frame lying flat face-down beside the laptop. "
    "Camera: static medium through the glass wall, slow push in on her face, BOTH speakers stay visible enough to read their lips. "
    "ACTION BEATS IN ORDER: 1) Vikram speaks his first line, measured. 2) Anu answers, voice breaking, eyes down. 3) Vikram says the final line while he SLIDES the white envelope across the desk toward Anu. 4) Anu takes the envelope with BOTH hands and holds it, looking down at it. "
    f"{dlg} These are the ONLY spoken lines - no other speech, no greetings, no added words. "
    "EXPRESSIONS: Anu is ashamed and tearful throughout, eyes mostly down, voice breaks, NO smiling. Vikram is measured, stern but softening at the end. "
    "PROP RULE: the photo frame stays LYING FLAT on the desk, face-down, its plain back panel facing up toward the camera, for the entire clip - never upright, never turned over. "
    "Same people as the start frame, same wardrobe, no new people, no readable on-screen text, no charts. Photoreal grounded office drama, natural lip sync.")
job=post("/v1/image-to-video", {"name":"HI_E01_S04_v2","model":"minimax-h3","resolution":"720p","audio":True,"end_seconds":18,"assets":{"image_file_path":fa},"style":{"prompt":vp}})
log(f"reroll job {job['id']} (18s)")
d=poll("video", job["id"])
if d.get("status")!="complete": raise RuntimeError(d.get("status"))
urllib.request.urlretrieve(d["downloads"][0]["url"], WD/"clips"/"HI_E01_S04_v2.mp4")
with open(WD/"credits_ledger.jsonl","a") as f: f.write(json.dumps({"job":"e01s04_clip_v5_reroll","credits":d.get("credits_charged",864)})+"\n")
log(f"reroll done ({d.get('credits_charged')} cr)")
cp=WD/"clips"/"HI_E01_S04_v2.mp4"
pq=json.loads(subprocess.run(["ffprobe","-v","quiet","-print_format","json","-show_format","-show_streams",str(cp)],capture_output=True,text=True).stdout)
dur=float(pq["format"]["duration"])
for t,tg in ((0.5,"start"),(4,"vline1"),(8,"aline"),(12,"slide"),(15,"take"),(max(dur-1.5,1),"end")):
    subprocess.run(["ffmpeg","-y","-ss",str(t),"-i",str(cp),"-frames:v","1",str(WD/"qa"/f"S04v2_{tg}.png")],check=True,capture_output=True)
subprocess.run(["ffmpeg","-y","-i",str(cp),"-vn","-ac","1","-ar","16000",str(WD/"qa"/"S04v2.wav")],check=True,capture_output=True)
log(f"QA artifacts dur={dur:.2f}")
print("CABIN-REROLL-DONE", flush=True)
