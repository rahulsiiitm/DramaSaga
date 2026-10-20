"""Validate dialogue timestamps against actual PCM WAV before captioning.

Energy detection is a guard, not forced word alignment or speech recognition.
"""
import math
import wave
from array import array
from pathlib import Path
from .core import finite, digest


def sound_span(wav_path, threshold_db=-40, window_ms=20):
    with wave.open(str(wav_path), 'rb') as audio:
        if audio.getsampwidth() != 2 or audio.getcomptype() != 'NONE':
            raise ValueError('Timing guard requires PCM16 WAV')
        rate, channels, frames = audio.getframerate(), audio.getnchannels(), audio.getnframes()
        samples = array('h', audio.readframes(frames))
    if __import__('sys').byteorder != 'little': samples.byteswap()
    step = max(1, round(rate * window_ms / 1000))
    threshold = 32768 * 10 ** (threshold_db / 20)
    active = []
    for start in range(0, frames, step):
        block = samples[start * channels:min(frames, start + step) * channels]
        rms = math.sqrt(sum(s * s for s in block) / max(1, len(block)))
        if rms > threshold: active.append((start / rate, min(frames, start + step) / rate))
    if not active:
        raise ValueError('No audible signal detected; cannot validate dialogue timing')
    return {'duration': frames / rate, 'sound_start': active[0][0], 'sound_end': active[-1][1]}


def validate_dialogue_alignment(wav_path, response, inputs, max_uncovered_sound=0.25):
    """Reject stale, incomplete or shifted timing. Passing is NOT proof of word sync."""
    max_uncovered_sound = finite(max_uncovered_sound, 'timing tolerance', 0)
    if max_uncovered_sound > 0.5:
        raise ValueError('Cannot loosen alignment guard beyond 0.5 seconds')
    span = sound_span(wav_path)
    alignment = response.get('alignment') or {}
    chars = alignment.get('characters', [])
    starts, ends = alignment.get('character_start_times_seconds', []), alignment.get('character_end_times_seconds', [])
    if not chars or len(chars) != len(starts) or len(chars) != len(ends):
        raise ValueError('Incomplete provider character alignment')
    if ''.join(chars) != ''.join(row['text'] for row in inputs):
        raise ValueError('Aligned text differs from exact submitted dialogue')
    previous = 0
    for start, end in zip(starts, ends):
        finite(start, 'character start'); finite(end, 'character end')
        if start < previous or end < start or end > span['duration'] + 0.05:
            raise ValueError('Nonmonotonic or out-of-range alignment')
        previous = start
    if span['sound_end'] - ends[-1] > max_uncovered_sound or starts[0] - span['sound_start'] > max_uncovered_sound:
        raise ValueError('Provider timestamps do not cover actual audible waveform; require forced alignment, not a global offset')
    segments = response.get('voice_segments', [])
    if len(segments) != len(inputs):
        raise ValueError('One validated segment per dialogue input required')
    cursor, previous_end = 0, 0
    for index, (segment, row) in enumerate(zip(segments, inputs)):
        end = cursor + len(row['text'])
        if segment.get('dialogue_input_index') != index or segment.get('voice_id') != row['voice_id'] or segment.get('character_start_index') != cursor or segment.get('character_end_index') != end:
            raise ValueError('Speaker/text segment binding mismatch')
        start_time = finite(segment['start_time_seconds'], 'segment start')
        end_time = finite(segment['end_time_seconds'], 'segment end')
        if start_time < previous_end or end_time <= start_time or end_time > span['duration'] + 0.05:
            raise ValueError('Invalid dialogue segment interval')
        previous_end, cursor = end_time, end
    return {'status': 'structural_and_waveform_guard_passed_not_word_sync_certified',
            'wav_sha256': digest(wav_path), **span,
            'next_check': 'Forced alignment of exact text to actual audio and spot-check audible words before publication.'}
