import json, os, subprocess, sys, time, requests
BASE="https://api.magichour.ai"; KEY=os.environ["MAGICHOUR_KEY"]
def H(): return {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
WD="/tmp/v3/honesty_v5/render"; OLD="/tmp/v3/honesty_render"
def log(m): print(time.strftime("%H:%M:%S"),"[E02-kf4]",m,flush=True)
script=json.load(open("/tmp/v3/honesty_v5/ep02.v5.json"))
sc=script["scenes"][3]
STYLE="Photoreal cinematic still, 9:16 vertical, grounded Indian office drama, natural skin tones, soft fluorescent light."
refs=[]
for rf in ["char_arjun_malhotra.png","loc_cabin.png"]:
    r=requests.post(f"{BASE}/v1/files/upload-urls",headers=H(),json={"items":[{"extension":"png","type":"image"}]},timeout=90); r.raise_for_status()
    it=r.json()["items"][0]
    with open(f"{OLD}/refs/{rf}","rb") as f: requests.put(it["upload_url"],data=f.read(),headers={"Content-Type":"application/octet-stream"},timeout=120).raise_for_status()
    refs.append(it["file_path"]); log(f"uploaded {rf}")
kp=(f"{STYLE} {sc['keyframe_visual']} Camera: {sc['camera']}. "
    "Arjun: young Indian man, early 20s, tousled black hair, dark casual shirt, lanyard with badge. "
    "Keep faces exactly consistent with the reference images. Exactly the people described, no duplicates, no background lookalikes. "
    "No readable text or numbers anywhere, no charts, no legible screens. The wall clock hands are blurred and unreadable. "
    + os.environ.get("PROMPT_EXTRA_S4",""))
r=requests.post(f"{BASE}/v1/ai-image-editor",headers=H(),json={"name":"hi-e02s04-v5","model":"nano-banana","assets":{"image_file_paths":refs},"style":{"prompt":kp}},timeout=90); r.raise_for_status()
jid=r.json()["id"]; log(f"keyframe job {jid}")
while True:
    d=requests.get(f"{BASE}/v1/image-projects/{jid}",headers=H(),timeout=30).json()
    if d.get("status") in ("complete","error","canceled"): break
    time.sleep(10)
if d.get("status")!="complete": raise RuntimeError(d.get("status"))
img=requests.get(d["downloads"][0]["url"],timeout=120).content
open(f"{WD}/frames/HI_E02_S04.png","wb").write(img)
cr=d.get("credits_charged",50)
open(f"{WD}/credits_ledger.jsonl","a").write(json.dumps({"job":"e02s04_frame_v5","credits":cr,"ep":2})+"\n")
log(f"S4 keyframe done ({cr} cr)")
