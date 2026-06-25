import argparse
import numpy as np
from PIL import Image, ImageDraw

COLORS = {
    "red":    ("#e53935", "#3d1212"),
    "yellow": ("#f5c518", "#2d2200"),
    "green":  ("#28c93f", "#0d2e18"),
}
ORDER = ["green", "yellow", "red"]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--origin_x", type=int, default=10)
    p.add_argument("--origin_y", type=int, default=10)
    p.add_argument("--size_x",   type=int, default=40)
    p.add_argument("--size_y",   type=int, default=40)
    p.add_argument("--gap_x",    type=int, default=10)
    args = p.parse_args()

    base = Image.open("image.png").convert("RGBA")
    print(f"Loaded image.png  ({base.width}x{base.height})")

    for i, name in enumerate(ORDER):
        x = args.origin_x + i * (args.size_x + args.gap_x)
        y = args.origin_y
        crop = base.crop((x, y, x + args.size_x, y + args.size_y))
        crop.save(f"{name}.png")
        print(f"Saved {name}.png  crop=({x},{y},{x+args.size_x},{y+args.size_y})")

    # overlap: abs(a-b) + abs(b-c) + abs(c-a)
    crops = []
    for i, name in enumerate(ORDER):
        x = args.origin_x + i * (args.size_x + args.gap_x)
        crops.append(np.array(Image.open(f"{name}.png").convert("RGB"), dtype=np.int32))
    a, b, c = crops
    diff = np.abs(a - b) + np.abs(b - c) + np.abs(c - a)
    diff = np.clip(diff, 0, 255).astype(np.uint8)
    Image.fromarray(diff).save("overlap.png")
    print("Saved overlap.png")


if __name__ == "__main__":
    main()
