import csv

LEDGERS = {
    "story_memory.csv": ["fact_id","series_id","episode_id","entity_type","entity_id","relation","target","valid_from","valid_to","source_span","adaptation_status","audience_knows_from","character_knows_from","reveal_status","continuity_priority","conflict_status","resume_cursor","canonical_decision"],
    "continuity.csv": ["block_id","scene_id","status","accepted_parent_clip","location","time_weather","axis_screen_direction","character_identity","wardrobe_or_surface","pose_action","prop_state","phone_or_prop_orientation","wetness_damage","light_direction","voice_ids","audio_in","audio_out","open_motion_vectors","physical_contact_points","entry_state","exit_state","observed_exit_state","tail_frame","reanchor_source","notes","canonical_prop_ids","prop_state_ids","text_plate_ids"],
    "voice_bible.csv": ["voice_id","character_id","language","accent","pronunciation_list","perceived_age_gender","timbre","pitch_center_range","speaking_rate","breath_intensity","emotional_baseline","allowed_variation","microphone_room","reference_asset","rights_status","forbidden_cross_bindings","qa_notes"],
    "shot_plan.csv": ["shot_id","scene_id","block_id","edit_beat","start_s","end_s","narrative_job","directorial_intention","value_before","value_after","subject_action","listener_or_world_reaction","shot_size","camera_start","camera_path","camera_motivation","camera_end","subject_endpoint","screen_direction","reference_authority","dialogue_or_sound","audio_in","audio_out","physical_contact_points","transition_in","transition_out","status","notes","canonical_prop_ids","prop_state_ids","text_plate_ids","physical_start_state","control_input","world_motion_vector","screen_motion_vector","physical_phase_sequence","physical_end_state","impact_role","impact_pattern","gag_setup","visible_cause","audience_advantage","reaction_hold","payoff","story_consequence","speaker_binding","non_speaker_mouth_state","performance_exaggeration","prop_count_state"],
    "generation_jobs.csv": ["job_id","block_id","parent_job_id","provider","exact_model_id","mode","request_fingerprint","idempotency_key","prompt_version","params_version","reference_digest","dependency_jobs","context_path","authorization_scope_id","quoted_cost","currency","status","progress","submitted_at","last_checked_at","completed_at","output_uri","error_class","retry_count","max_retries","changed_variable","cancellation_state","recovery_note","accepted_ranges","qa_status"],
    "spend_ledger.csv": ["request_id","block_id","provider","model","mode","duration_s","resolution","candidate_purpose","quoted_cost","actual_cost","currency","retry_parent","status","accepted_seconds","reason","submitted_at","completed_at","approval_scope_id","prompt_fingerprint","params_fingerprint","reference_digest","schema_checked_at","task_recovery_note"],
}

def ensure_ledgers(workdir):
    for name, header in LEDGERS.items():
        p = workdir / name
        if not p.exists():
            with open(p, "w", newline="") as f:
                csv.writer(f).writerow(header)

def ledger_row(workdir, name, row):
    with open(workdir / name, "a", newline="") as f:
        csv.writer(f).writerow(row)

def seed_canon(workdir, canon, canon_facts):
    import json
    arc_p = workdir / "season_arc.json"
    arc = json.loads(arc_p.read_text()) if arc_p.exists() else {"episodes": []}
    existing = {e["ep"] for e in arc["episodes"]}
    for e in canon:
        if e["ep"] not in existing:
            arc["episodes"].append(dict(e, canon=True))
    arc["episodes"].sort(key=lambda e: e["ep"])
    arc_p.write_text(json.dumps(arc, indent=2))
    sm = workdir / "story_memory.csv"
    have = sm.read_text() if sm.exists() else ""
    with open(sm, "a", newline="") as f:
        w = csv.writer(f)
        for row in canon_facts:
            if row[0] not in have:
                w.writerow(row)
    return arc

