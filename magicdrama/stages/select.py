import json

from .. import config
from ..clients.nvidia import nvidia_chat

SELECT_CRITERIA = (
    "Character consistency: gender, ethnicity, age, facial features, body shape, outfit, hairstyle must match the reference description. "
    "Spatial consistency: relative positions of characters and scene layout must match the shot description. "
    "Description accuracy: key actions, objects and setting from the shot description must be present. "
    "Reject images with white borders, black edges or added framing."
)

def select_best_candidate(reference_desc, target_desc, candidates):
    if config.DRY_RUN:
        return {"best_image_index": 0, "reason": "dry run"}
    prompt = (
        "You are a visual assessment expert picking the best candidate image. "
        f"Criteria: {SELECT_CRITERIA} "
        f"Reference: {reference_desc}. Target: {target_desc}. "
        f"There are exactly {len(candidates)} candidates, indexed 0 to {len(candidates) - 1}. "
        'Return a single JSON object: {"best_image_index": int, "reason": str}. JSON only.'
    )
    out = nvidia_chat(config.NVIDIA_MODELS["vision_judge"], [{"role": "user", "content": prompt}], max_tokens=300, temperature=0.1)
    text = out["choices"][0]["message"]["content"]
    result = json.loads(text[text.index("{"): text.rindex("}") + 1])
    assert 0 <= result["best_image_index"] < len(candidates), "invented candidate index"
    return result

def generate_with_selection(spend, tag, reference_desc, target_desc, n_candidates=2):
    from ..clients.magichour import mh_image
    from ..governor import IMAGE_CR
    candidates = []
    for k in range(n_candidates):
        job = spend.spend(f"{tag}_candidate{k}", IMAGE_CR[config.MH_IMAGE_MODEL], mh_image, target_desc, model=config.MH_IMAGE_MODEL)
        candidates.append(job)
    pick = select_best_candidate(reference_desc, target_desc, candidates)
    return candidates[pick["best_image_index"]], pick

