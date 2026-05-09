"""
Crossfade Zoom — transition between any images using zoom-in + crossfade.
Same CLI interface as infinite_zoom.py so the GUI can swap between modes.
"""
import cv2
import numpy as np
from pathlib import Path
import argparse
import sys

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}


def smoothstep(t):
    return t * t * (3 - 2 * t)


def load_images(folder: Path):
    files = sorted([f for f in folder.iterdir() if f.suffix.lower() in IMAGE_EXTS])
    images = []
    for f in files:
        img = cv2.imread(str(f))
        if img is not None:
            images.append((f.name, img))
    return images


def resize_fill(img, w, h):
    """Resize image to fill (w, h), center-cropping to maintain aspect ratio."""
    ih, iw = img.shape[:2]
    scale = max(w / iw, h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
    x = (nw - w) // 2
    y = (nh - h) // 2
    return resized[y:y + h, x:x + w]


def make_transition_frames(img_a, img_b, steps, w, h, zoom_factor):
    """
    Zoom into img_a while crossfading to img_b at full scale.
    Returns a list of uint8 BGR frames.
    """
    a = resize_fill(img_a, w, h).astype(np.float32)
    b = resize_fill(img_b, w, h).astype(np.float32)
    frames = []

    for i in range(steps):
        t = i / steps
        s = smoothstep(t)

        # Zoom into A by progressively center-cropping
        zoom = 1.0 + s * (zoom_factor - 1.0)
        crop_w = max(1, int(w / zoom))
        crop_h = max(1, int(h / zoom))
        x1 = (w - crop_w) // 2
        y1 = (h - crop_h) // 2
        a_zoomed = cv2.resize(
            a[y1:y1 + crop_h, x1:x1 + crop_w], (w, h),
            interpolation=cv2.INTER_LINEAR
        )

        # Blend: A fades out as B fades in (both at output resolution)
        frame = (a_zoomed * (1.0 - s) + b * s).clip(0, 255).astype(np.uint8)
        frames.append(frame)

    return frames


def make_hold_frames(img, count, w, h):
    f = resize_fill(img, w, h)
    return [f] * count


def main():
    parser = argparse.ArgumentParser(description="Crossfade Zoom — any images to zoom video")
    parser.add_argument("-i", "--Input",            dest="input_folder", required=True)
    parser.add_argument("-o", "--Output",           dest="output",       default="output.mp4")
    parser.add_argument("-zf", "--ZoomFactor",      dest="zoom_factor",  type=float, default=2.0)
    parser.add_argument("-zs", "--ZoomSteps",       dest="zoom_steps",   type=int,   default=100)
    parser.add_argument("-zc", "--ZoomCrop",        dest="zoom_crop",    type=float, default=0.8)
    parser.add_argument("-fps", "--FramesPerSecond",dest="fps",          type=float, default=60.0)
    parser.add_argument("-d",  "--Delay",           dest="delay",        type=float, default=0.0)
    parser.add_argument("-rev","--Reverse",         dest="reverse",      action="store_true")
    parser.add_argument("-as", "--AutoSort",        dest="auto_sort",    action="store_true")
    parser.add_argument("-dbg","--Debug",           dest="debug",        action="store_true")
    args = parser.parse_args()

    print("\n\nCrossfade Zoom Generator")
    print("------------------------")
    print(f" - input folder: \"{args.input_folder}\"")
    print(f" - output:       \"{args.output}\"")
    print(f" - fps:          {args.fps}")
    print(f" - zoom factor:  {args.zoom_factor}")
    print(f" - zoom steps:   {args.zoom_steps}")
    print(f" - delay:        {args.delay}")
    print(f" - reverse:      {args.reverse}")

    folder = Path(args.input_folder)
    named_images = load_images(folder)

    if len(named_images) < 2:
        print(f"\nError: need at least 2 images, found {len(named_images)}.")
        sys.exit(1)

    print(f"\n{len(named_images)} images loaded.")

    if args.reverse:
        named_images = list(reversed(named_images))

    # Determine output size from first image
    _, first = named_images[0]
    h, w = first.shape[:2]

    delay_frames = int(args.delay * args.fps)

    all_frames = []

    # Hold on first image
    if delay_frames:
        all_frames += make_hold_frames(first, delay_frames, w, h)

    # Transitions
    pairs = list(zip(named_images, named_images[1:]))
    for idx, ((name_a, img_a), (name_b, img_b)) in enumerate(pairs):
        print(f" - transition {idx + 1}/{len(pairs)}: {name_a} -> {name_b}")
        all_frames += make_transition_frames(img_a, img_b, args.zoom_steps, w, h, args.zoom_factor)

    # Hold on last image
    if delay_frames:
        _, last = named_images[-1]
        all_frames += make_hold_frames(last, delay_frames, w, h)

    # Write output
    output_ext = Path(args.output).suffix
    if output_ext == "":
        # Frame folder output
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"\nSaving {len(all_frames)} frames to {out_dir}")
        for i, frame in enumerate(all_frames):
            cv2.imwrite(str(out_dir / f"frame_{i:05d}.png"), frame)
    else:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(args.output, fourcc, args.fps, (w, h))
        print(f"\nWriting {len(all_frames)} frames -> {args.output}")
        for frame in all_frames:
            out.write(frame)
        out.release()

    print("\nDone!")


if __name__ == "__main__":
    main()
