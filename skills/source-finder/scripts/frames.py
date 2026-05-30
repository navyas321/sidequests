#!/usr/bin/env python3
"""
frames.py - Extract still frames from a video so the agent can READ on-screen
clues: a streamer's name/branding, on-screen text, song-title overlays, or a
chat where viewers literally guess the song. Often the fastest path to the
answer when audio ID is hard.

  --crop right  also saves a 3-4x upscaled crop of the RIGHT side of the frame
                (where Twitch/YouTube-live chat usually sits) for legibility.

Saves JPGs to the output dir; the agent then Reads them.

Usage:
  python frames.py clip.mov                 # 4 frames spread across the video
  python frames.py clip.mov --n 6 --crop right
Requires: pip install opencv-python-headless
"""
import argparse, os
import cv2

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--crop", choices=["none", "right", "full"], default="none")
    ap.add_argument("--out", default="_frames")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    cap = cv2.VideoCapture(a.video)
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)); w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"video {w}x{h} {fps:.0f}fps {total/max(fps,1):.0f}s")
    for i in range(a.n):
        frac = (i + 0.5) / a.n
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * frac))
        ok, fr = cap.read()
        if not ok:
            continue
        cv2.imwrite(os.path.join(a.out, f"f{i}.jpg"), fr)
        if a.crop == "right":
            crop = fr[int(h*0.1):int(h*0.45), int(w*0.55):w]
            crop = cv2.resize(crop, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
            cv2.imwrite(os.path.join(a.out, f"f{i}_chat.jpg"), crop)
        elif a.crop == "full":
            big = cv2.resize(fr, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            cv2.imwrite(os.path.join(a.out, f"f{i}_2x.jpg"), big)
    cap.release()
    print(f"saved frames to {a.out}/  (Read them to look for on-screen clues)")

if __name__ == "__main__":
    main()
