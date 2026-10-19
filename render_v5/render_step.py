                      
import json, os, subprocess, sys, time, urllib.request
from pathlib import Path
import requests

EP=int(os.environ["EP"]); TAG=f"E{EP:02d}"
BASE="https://api.magichour.ai"; KEY=os.environ["MAGICHOUR_KEY"]
WD=Path("/tmp/v3/honesty_v5/render"); OLD=Path("/tmp/v3/honesty_render")
IMG_MODEL="nano-banana-2.1"; VID_MODEL="minimax-h3"; RES="720p"
STYLE=("Photoreal cinematic still, present-day Mumbai advertising agency Meridian, "
       "motivated natural light, mixed fluorescent and window daylight, candid documentary "
       "framing, slightly off-center, ordinary office clutter and wear, warm grounded tone, 9:16 vertical.")
LEDGER=WD/"credits_ledger.jsonl"
def log(m): print(f"{time.strftime('%H:%M:%S')} [{TAG}] {m}", flush=True)
def H(): return {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
def ledger(rec):
    rec["ep"]=EP
    with open(LEDGER,"a") as f: f.write(json.dumps(rec)+"\n")
def post(path, payload, tries=2):
    for a in range(tries):
        try:
            r=requests.post(f"{BASE}{path}", headers=H(), json=payload, timeout=90)
            if r.status_code == 429:
                log(f"429 RATE-LIMIT on {path} (attempt {a+1})")
                time.sleep(20*(a+1)); continue
            if r.status_code in (500,502,503,504): time.sleep(20*(a+1)); continue
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

script=json.load(open(f"/tmp/v3/honesty_v5/ep{EP:02d}.v5.json"))
CHAR_REFS={"Anu":"char_anu_rao.png","Vikram":"char_vikram_sethi.png","Priya":"char_priya_nair.png","Arjun":"char_arjun_malhotra.png"}
WARDROBE={"Anu":"Anu Rao wears the SAME outfit as her reference image (mustard kurti, navy blazer ON, canvas tote).",
          "Priya":"Priya Nair wears the SAME outfit as her reference image.",
          "Vikram":"Vikram Sethi wears the SAME outfit as his reference image.",
          "Arjun":"Arjun Malhotra wears the SAME outfit as his reference image."}
LOC_REF={"lobby":"loc_lobby.png","elevator":"loc_elevator.png","floor":"loc_office_floor.png","cabin":"loc_cabin.png","stairwell":"loc_stairwell.png","chai":"loc_chai_stall.png","pantry":"loc_pantry.png","corridor":"loc_office_floor.png"}
def loc_ref_for(sc):
    t=(sc["location"]+" "+sc["keyframe_visual"]).lower()
    for k,v in LOC_REF.items():
        if k in t: return v
    return "loc_office_floor.png"
def chars_in(sc):
    blob=json.dumps(sc)
    out=[c for c in CHAR_REFS if c in blob]
    if not out: out=["Anu"]
    return out[:2]

def make_keyframe(sc):
    fp=WD/"frames"/f"HI_{TAG}_S{sc['n']:02d}.png"
    if fp.exists(): return fp
    chars=chars_in(sc)
    refs=[upload(OLD/"refs"/CHAR_REFS[c],"png","image") for c in chars]
    refs.append(upload(OLD/"refs"/loc_ref_for(sc),"png","image"))
    kp=(f"{STYLE} {sc['keyframe_visual']} Camera: {sc['camera']}. "
        + " ".join(WARDROBE[c] for c in chars) +
        " Keep faces exactly consistent with the reference images. Exactly the people described, no duplicates, no background lookalikes. "
        "No readable text or numbers anywhere, no charts, no legible screens.")
    kx=os.environ.get("PROMPT_EXTRA","")
    if kx: kp=kp+" "+kx
    job=post("/v1/ai-image-editor", {"name":f"hi-{TAG.lower()}s{sc['n']:02d}-v5","model":IMG_MODEL,"assets":{"image_file_paths":refs[:3]},"style":{"prompt":kp}})
    d=poll("image", job["id"])
    if d.get("status")!="complete": raise RuntimeError(f"image: {d.get('status')}")
    download(d["downloads"][0]["url"], fp)
    ledger({"job":f"{TAG.lower()}s{sc['n']:02d}_frame_v5","credits":d.get("credits_charged",50)}); log(f"S{sc['n']} keyframe ({d.get('credits_charged')} cr)")
    return fp

def frame_at(clip, t, out):
    subprocess.run(["ffmpeg","-y","-ss",str(t),"-i",str(clip),"-frames:v","1",str(out)],check=True,capture_output=True)
    return out

def make_clip(sc, start_frame_path):
    cp=WD/"clips"/f"HI_{TAG}_S{sc['n']:02d}.mp4"
    if cp.exists(): return cp
    fa=upload(start_frame_path,"png","image")
    if sc["dialogue"]:
        dlg=" ".join(f"{dd['character']} ({dd['voice']}) says exactly: \"{dd['line']}\"" for dd in sc["dialogue"])
        speak=f"{dlg} These are the ONLY spoken lines - no other speech, no greetings, no added words."
    else:
        speak="No speech at all - ambient office sound only."
    beats=" ".join(f"{i+1}) {b.strip().rstrip('.')}." for i,b in enumerate(sc["micro_acting"].split(";")) if b.strip()) or "Actors hold the moment with small natural movement."
    chars=", ".join(sorted({dd["character"] for dd in sc["dialogue"]})) or "the actors"
    expr=f"Emotional state of each speaker ({chars}) must follow the action beats above."
    vp=(f"Continue this exact scene: {sc['keyframe_visual']} Camera: {sc['camera']}. "
        f"ACTION BEATS IN ORDER: {beats} {speak} "
        f"EXPRESSIONS: {expr} Expressions match each line's emotion exactly, no smiling unless the line is warm. "
        "PROP RULE: every object keeps the exact position and orientation it has in the start frame unless an action beat explicitly moves it; nothing flips, rotates, or changes hands off-screen. "
        "Same people as the start frame, same wardrobe, no new people, no readable on-screen text, no charts. "
        "Photoreal grounded office drama, natural lip sync, natural emotion matching the lines.")
    extra=os.environ.get("PROMPT_EXTRA","")
    if extra: vp=vp+" "+extra
    secs=sc["seconds"]+2
    job=post("/v1/image-to-video", {"name":f"HI_{TAG}_S{sc['n']:02d}","model":VID_MODEL,"resolution":RES,
        "audio":True,"end_seconds":secs,"assets":{"image_file_path":fa},"style":{"prompt":vp}})
    log(f"S{sc['n']} clip job {job['id']} ({secs}s)")
    d=poll("video", job["id"])
    if d.get("status")!="complete": raise RuntimeError(f"video S{sc['n']}: {d.get('status')}")
    download(d["downloads"][0]["url"], cp)
    ledger({"job":f"{TAG.lower()}s{sc['n']:02d}_clip_v5","credits":d.get("credits_charged",secs*48)}); log(f"S{sc['n']} clip ({d.get('credits_charged')} cr)")
    return cp

def qa_artifacts(sc, cp):
    pq=json.loads(subprocess.run(["ffprobe","-v","quiet","-print_format","json","-show_format","-show_streams",str(cp)],capture_output=True,text=True).stdout)
    dur=float(pq["format"]["duration"]); has_audio=any(s["codec_type"]=="audio" for s in pq["streams"])
    n=f"{TAG}_S{sc['n']:02d}"
    for t,tg in ((0.5,"start"),(dur/2,"mid"),(max(dur-2.5,1),"end")):
        subprocess.run(["ffmpeg","-y","-ss",str(t),"-i",str(cp),"-frames:v","1",str(WD/"qa"/f"{n}_{tg}.png")],check=True,capture_output=True)
    subprocess.run(["ffmpeg","-y","-i",str(cp),"-vn","-ac","1","-ar","16000",str(WD/"qa"/f"{n}.wav")],check=True,capture_output=True)
    (WD/"qa"/f"{n}_probe.json").write_text(json.dumps({"duration":dur,"audio":has_audio,"expected":sc["seconds"]+2}))
    log(f"{n} QA artifacts dur={dur:.2f} audio={has_audio}")

                                                                                                            
scenes=script["scenes"]
target=None
for i,sc in enumerate(scenes):
    if not (WD/"clips"/f"HI_{TAG}_S{sc['n']:02d}.mp4").exists():
        target=(i,sc); break
if target is None:
    print(f"{TAG}-ALL-SCENES-DONE", flush=True); sys.exit(0)
i,sc=target
                                                                                                                                                            
CHAIN={1:{2:True},2:set(),3:{2:True,3:True}}
if i==0 or sc["n"] not in CHAIN.get(EP,set()):
    start=make_keyframe(sc)
else:
    psc=scenes[i-1]
    pclip=WD/"clips"/f"HI_{TAG}_S{psc['n']:02d}.mp4"
    start=frame_at(pclip, psc["seconds"], WD/"frames"/f"HI_{TAG}_S{sc['n']:02d}_start.png")
cp=make_clip(sc, start)
qa_artifacts(sc, cp)
print(f"{TAG}-STEP-DONE-S{sc['n']:02d}", flush=True)
