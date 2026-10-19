import json
import pathlib
import subprocess
import wave

from .. import config

FONT_SIZE = 34
MARGIN_V = 60

def _run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {p.stderr[-800:]}")
    return p

def _srt_time(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")

def write_srt(script, out_path):
    lines = []
    t = 0.0
    idx = 1
    for shot in script["shots"]:
        dur = shot["seconds"]
        for d in shot.get("dialogue", []):
            start = t + 0.3
            end = min(t + dur - 0.2, start + max(1.5, 0.35 * len(str(d["line"]).split())))
            lines.append(f"{idx}\n{_srt_time(start)} --> {_srt_time(end)}\n{d['character']}: {d['line']}\n")
            idx += 1
        t += dur
    out_path.write_text("\n".join(lines))
    return out_path

def synth_clip(shot, out_path, workdir):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dur = shot["seconds"]
    label = f"E{script_ep(workdir)} shot {shot['n']}"
    _run(["ffmpeg", "-y", "-f", "lavfi", "-i",
          f"testsrc2=size=720x1280:rate=24:duration={dur}",
          "-f", "lavfi", "-i", f"sine=frequency={180 + 40 * shot['n']}:duration={dur}",
          "-vf", f"drawtext=text='{label}':fontsize=48:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2",
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out_path)])
    return out_path

def script_ep(workdir):
    state = workdir / ".assembly_ep"
    return state.read_text().strip() if state.exists() else "1"

def collect_shot_clips(workdir, ep, script):
    vdir = workdir / "video" / f"ep{ep:02d}"
    clips = []
    for shot in script["shots"]:
        p = vdir / f"shot{shot['n']:02d}.mp4"
        if p.exists():
            clips.append(p)
        elif config.DRY_RUN:
            (workdir / ".assembly_ep").write_text(str(ep))
            clips.append(synth_clip(shot, p, workdir))
        else:
            raise RuntimeError(f"missing rendered clip for E{ep} shot {shot['n']}: {p}")
    return clips

def audio_tracks(workdir, ep):
    adir = workdir / "audio" / f"ep{ep:02d}"
    return sorted(adir.glob("*.wav")) if adir.exists() else []

def assemble_episode(workdir, brief, script, out_name=None):
    ep = script["ep"]
    clips = collect_shot_clips(workdir, ep, script)
    odir = workdir / "episodes"
    odir.mkdir(parents=True, exist_ok=True)
    concat_list = odir / f"ep{ep:02d}_concat.txt"
    concat_list.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    srt = write_srt(script, odir / f"ep{ep:02d}.srt")
    out = odir / (out_name or f"ep{ep:02d}.mp4")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list)]
    if srt.read_text().strip():
        style = f"FontSize={FONT_SIZE},MarginV={MARGIN_V},OutlineColour=&H80000000,BorderStyle=1,Outline=2"
        cmd += ["-vf", f"subtitles='{srt.resolve()}':force_style='{style}'"]
    cmd += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)]
    _run(cmd)
    return {"path": str(out), "srt": str(srt), "clips": len(clips)}

def probe_duration(path):
    p = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return float(p.stdout.strip())

