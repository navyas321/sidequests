#!/usr/bin/env python3
"""
transcribe.py - Transcribe sung lyrics with faster-whisper. The lyrics are
then web-searched to identify the song (works for covers, since it's the
words, not the recording fingerprint).

Tips that matter:
  * Use --no-vad (default): Whisper's voice-activity filter often discards
    SINGING as "non-speech" and returns nothing.
  * Escalate model on garbled output: small (fast) -> medium -> large-v2.
    large-v2 is dramatically better at lyrics buried under instruments.
  * Feed it a cleaned track: extract_audio.py --eq, or separate_vocals.py.
  * Do NOT pass an initial_prompt describing the task - the model will just
    echo it ("A singer performing..."). Leave it empty.

Usage:
  python transcribe.py audio.wav                 # small, no VAD
  python transcribe.py vocals.wav --model large-v2
Requires: pip install faster-whisper
"""
import argparse
from faster_whisper import WhisperModel

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--model", default="small", help="small|medium|large-v2")
    ap.add_argument("--vad", action="store_true", help="enable VAD (usually hurts singing)")
    a = ap.parse_args()
    m = WhisperModel(a.model, device="cpu", compute_type="int8")
    segs, info = m.transcribe(a.audio, beam_size=5, vad_filter=a.vad,
                              condition_on_previous_text=False, temperature=0.0)
    print(f"lang={info.language} ({info.language_probability:.2f})")
    print("--- lyrics ---")
    for s in segs:
        print(f"[{s.start:6.1f}s] {s.text.strip()}")

if __name__ == "__main__":
    main()
