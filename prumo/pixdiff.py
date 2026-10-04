"""Compare two screenshots and say what moved.

Prints the share of pixels that differ and the box that contains them.
A refactor that must not change the rendering is verified by capturing the
same scenario before and after and comparing: the suite says the page still
behaves, this says it still looks the same.

Different image sizes are a difference in themselves, and are reported as one.
Whatever the page generates fresh on every load, such as a timestamp, differs
between two runs of the same code and would be read as a regression. The
scenario reports those regions under a key in its log (`--ignore-from
LOG.json --ignore-key dynamic`, boxes as {x, y, width, height}) and they are
masked out. Needs Pillow.
"""
import json


def masked_boxes(log_path, key="dynamic", scale=2.0):
    """Regions the scenario reported as generated per load, in image pixels."""
    with open(log_path, encoding="utf-8") as log:
        boxes = json.load(log).get(key) or []
    return [(round(b["x"] * scale), round(b["y"] * scale),
             round((b["x"] + b["width"]) * scale), round((b["y"] + b["height"]) * scale))
            for b in boxes]


def compare(before_path, after_path, out_path=None, tolerance=0, ignore=()):
    try:
        from PIL import Image, ImageChops, ImageDraw
    except ImportError:
        raise SystemExit("prumo diff needs Pillow: pip install pillow") from None
    before = Image.open(before_path).convert("RGB")
    after = Image.open(after_path).convert("RGB")
    if before.size != after.size:
        print(f"size changed: {before.size} -> {after.size}")
        return 1

    diff = ImageChops.difference(before, after).convert("L")
    if ignore:
        mask = ImageDraw.Draw(diff)
        for box in ignore:
            mask.rectangle(box, fill=0)
    if tolerance:
        diff = diff.point(lambda value: 255 if value > tolerance else 0)

    box = diff.getbbox()
    histogram = diff.histogram()
    changed = sum(histogram[1:])
    total = before.size[0] * before.size[1]
    share = 100 * changed / total

    if not changed:
        print(f"identical: {total} pixels, {before.size[0]}x{before.size[1]}")
        return 0

    print(f"{changed} of {total} pixels differ ({share:.3f}%), inside {box}")
    if out_path:
        diff.save(out_path)
        print(f"diff written to {out_path}")
    return 1
