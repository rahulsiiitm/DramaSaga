import os
import pathlib

DRY_RUN = os.environ.get("MAGICDRAMA_DRY_RUN", "1") != "0"
BALANCE_CREDITS = int(os.environ.get("MAGICDRAMA_BALANCE_CREDITS", "0"))
EPISODE_CAP_CREDITS = 3000
BATCH_CAP_CREDITS = 30000
WORKDIR = pathlib.Path(os.environ.get("MAGICDRAMA_WORKDIR", "microdrama_out"))

NVIDIA_BASE = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_MODELS = {
    "writer": os.environ.get("MD_WRITER_MODEL", "nvidia/nemotron-3-super-120b-a12b"),
    "judge": os.environ.get("MD_JUDGE_MODEL", "nvidia/nemotron-3-ultra-550b-a55b"),
    "vision_judge": os.environ.get("MD_VISION_JUDGE_MODEL", "meta/llama-3.2-90b-vision-instruct"),
    "tts": "magpie-tts-multilingual",
}
MH_BASE = "https://api.magichour.ai"
MH_VIDEO_MODEL = "ltx-2.5"
AB_MODELS = ["ltx-2.5", "minimax-h3"]
MH_IMAGE_MODEL = "flux-schnell"
MH_IMAGE_EDIT_MODEL = "qwen-edit"
RESOLUTION = "480p"
ASPECT = "9:16"
EP_SECONDS = 64
SHOT_SECONDS = [5, 6, 6, 6, 6, 7, 6, 7, 8, 7]
EPISODES_TOTAL = 50
EPISODES_RENDER = 10
CANON_LAST_EP = 10
MASTERS_APPROVED = False

