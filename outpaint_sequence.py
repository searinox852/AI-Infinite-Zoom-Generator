"""
outpaint_sequence.py
Generate an outpainted zoom sequence from a single image via ComfyUI.

Each level: resize current image to half target size, pad back to full size,
inpaint the border. Produces a folder of images for infinite_zoom.py.
"""
import argparse
import json
import os
import sys
import time
import random
import shutil
from pathlib import Path

import cv2
import numpy as np
import requests

COMFYUI_HOST = "http://127.0.0.1:8188"
DEFAULT_MODEL = "juggernautXL_v9Rdphoto2Lightning.safetensors"
DEFAULT_NEGATIVE = "low quality, blurry, watermark, text, border, frame, duplicate"


def api(path, method="GET", json_body=None):
    url = COMFYUI_HOST + path
    if method == "POST":
        r = requests.post(url, json=json_body, timeout=30)
    else:
        r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json() if r.content else {}


def upload_image(image_path: str) -> str:
    """Upload a local image to ComfyUI input/ and return its filename."""
    with open(image_path, "rb") as f:
        data = f.read()
    filename = Path(image_path).name
    r = requests.post(
        COMFYUI_HOST + "/upload/image",
        files={"image": (filename, data, "image/png")},
        data={"overwrite": "true"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["name"]


def download_image(filename: str, subfolder: str = "") -> bytes:
    params = {"filename": filename, "type": "output"}
    if subfolder:
        params["subfolder"] = subfolder
    r = requests.get(COMFYUI_HOST + "/view", params=params, timeout=60)
    r.raise_for_status()
    return r.content


def build_workflow(uploaded_filename: str, positive: str, model: str,
                   target_size: int, seed: int) -> dict:
    half = target_size // 2
    pad = target_size // 4  # each side: half → full means +quarter each side

    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": model}
        },
        "2": {
            "class_type": "LoadImage",
            "inputs": {"image": uploaded_filename}
        },
        "3": {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["2", 0],
                "upscale_method": "lanczos",
                "width": half,
                "height": half,
                "crop": "center"
            }
        },
        "4": {
            "class_type": "ImagePadForOutpaint",
            "inputs": {
                "image": ["3", 0],
                "left": pad,
                "top": pad,
                "right": pad,
                "bottom": pad,
                "feathering": 32
            }
        },
        "5": {
            "class_type": "VAEEncodeForInpaint",
            "inputs": {
                "pixels": ["4", 0],
                "vae": ["1", 2],
                "mask": ["4", 1],
                "grow_mask_by": 8
            }
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": positive, "clip": ["1", 1]}
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": DEFAULT_NEGATIVE, "clip": ["1", 1]}
        },
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
                "seed": seed,
                "steps": 6,
                "cfg": 1.5,
                "sampler_name": "euler",
                "scheduler": "sgm_uniform",
                "denoise": 1.0
            }
        },
        "9": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["8", 0], "vae": ["1", 2]}
        },
        "10": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["9", 0],
                "filename_prefix": "outpaint_seq"
            }
        }
    }


def wait_for_job(prompt_id: str, timeout: int = 300) -> dict:
    """Poll until job completes. Returns history entry."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(2)
        history = api(f"/history/{prompt_id}")
        if prompt_id in history:
            entry = history[prompt_id]
            status = entry.get("status", {})
            if status.get("completed"):
                return entry
            if status.get("status_str") == "error":
                msgs = status.get("messages", [])
                raise RuntimeError(f"ComfyUI job failed: {msgs}")
    raise TimeoutError(f"Job {prompt_id} did not complete within {timeout}s")


def run_outpaint_level(current_image_path: str, positive: str, model: str,
                       target_size: int) -> bytes:
    """Run one outpaint level. Returns PNG bytes of result."""
    uploaded = upload_image(current_image_path)
    seed = random.randint(0, 2**31)
    workflow = build_workflow(uploaded, positive, model, target_size, seed)

    result = api("/prompt", method="POST", json_body={"prompt": workflow})
    prompt_id = result["prompt_id"]
    print(f"   queued: {prompt_id}")

    entry = wait_for_job(prompt_id)
    outputs = entry.get("outputs", {})

    # Find SaveImage output (node "10")
    node_out = outputs.get("10", {})
    images = node_out.get("images", [])
    if not images:
        raise RuntimeError("No images in ComfyUI output")

    img_info = images[0]
    return download_image(img_info["filename"], img_info.get("subfolder", ""))


def resize_image(path: str, size: int) -> np.ndarray:
    img = cv2.imread(path)
    if img is None:
        raise ValueError(f"Cannot read image: {path}")
    return cv2.resize(img, (size, size), interpolation=cv2.INTER_LANCZOS4)


def main():
    parser = argparse.ArgumentParser(description="Generate outpaint zoom sequence via ComfyUI")
    parser.add_argument("-i", "--input",   required=True,  help="Input image path")
    parser.add_argument("-o", "--output",  required=True,  help="Output folder for sequence")
    parser.add_argument("-n", "--levels",  type=int, default=4, help="Number of zoom-out levels to generate")
    parser.add_argument("-p", "--prompt",  default="highly detailed, 8k, cinematic",
                        help="Positive prompt for outpainting")
    parser.add_argument("-m", "--model",   default=DEFAULT_MODEL, help="Checkpoint model name")
    parser.add_argument("-s", "--size",    type=int, default=1024,
                        help="Target image size in pixels (default 1024)")
    parser.add_argument("--host",          default="http://127.0.0.1:8188", help="ComfyUI host URL")
    args = parser.parse_args()

    global COMFYUI_HOST
    COMFYUI_HOST = args.host.rstrip("/")

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Verify ComfyUI is reachable
    try:
        api("/system_stats")
    except Exception as e:
        print(f"Cannot reach ComfyUI at {COMFYUI_HOST}: {e}")
        sys.exit(1)

    print(f"\nOutpaint Sequence Generator")
    print(f"---------------------------")
    print(f" input:   {args.input}")
    print(f" output:  {args.output}")
    print(f" levels:  {args.levels}")
    print(f" model:   {args.model}")
    print(f" size:    {args.size}x{args.size}")
    print(f" prompt:  {args.prompt}")

    # Save level 0: original image resized to target size
    img0 = resize_image(args.input, args.size)
    level0_path = str(out_dir / "0001_original.png")
    cv2.imwrite(level0_path, img0)
    print(f"\nLevel 0 saved: {level0_path}")

    current_path = level0_path

    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="outpaint_tmp_")

    try:
        for level in range(1, args.levels + 1):
            print(f"\nGenerating level {level}/{args.levels}...")
            png_bytes = run_outpaint_level(current_path, args.prompt, args.model, args.size)

            # Save result
            out_path = str(out_dir / f"{level + 1:04d}_level{level}.png")
            with open(out_path, "wb") as f:
                f.write(png_bytes)
            print(f"   saved: {out_path}")

            # Use as input for next level
            current_path = out_path

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    total = args.levels + 1
    print(f"\nDone! {total} images saved to {args.output}")
    print(f"Use this folder with Outpaint Sequence mode and zoom_factor=2.0")


if __name__ == "__main__":
    main()
