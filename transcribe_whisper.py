import argparse
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('audio')
    parser.add_argument('--model', default='base')
    args = parser.parse_args()
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise SystemExit('Install the optional faster-whisper package first')
    model = WhisperModel(args.model, device='cpu', compute_type='int8')
    segments, _ = model.transcribe(args.audio, vad_filter=True)
    print(' '.join(segment.text.strip() for segment in segments))


if __name__ == '__main__':
    main()
