#!/usr/bin/env python3
"""Convert a dark-on-light logo PNG into the standby-screen logo.

The EEZ UI draws img_logo as LV_IMG_CF_ALPHA_8BIT recoloured to NiceWhite, so
only alpha carries the picture. Dark source pixels become opaque (shown white),
light/transparent ones become transparent. --gamma below 1 lifts the
partially-covered pixels (fine hatching reads grey on the small screen)
while leaving solid lines and the background alone; alpha under 8 is dropped
so the lift doesn't turn paper texture into haze.

Writes both the C array the firmware compiles and the black+alpha PNG embedded
in eez-ui/gaggimate.eez-project, so regenerating from EEZ Studio keeps the logo.

    python3 scripts/logo_to_eez.py icons/stephen_logo.png --gamma 0.5
"""
import argparse
import base64
import io
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
C_FILE = ROOT / "src/display/ui/default/eez/images/ui_image_logo.c"
PROJECT = ROOT / "eez-ui/gaggimate.eez-project"


def main(src: str, gamma: float) -> None:
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    px = im.tobytes()
    alpha = bytes(
        a * (255 - (r * 299 + g * 587 + b * 114) // 1000) // 255
        for r, g, b, a in zip(px[0::4], px[1::4], px[2::4], px[3::4])
    )
    if gamma != 1.0:
        alpha = bytes(0 if v < 8 else round(255 * (v / 255) ** gamma) for v in alpha)

    # C array: keep upstream's preamble, replace the data and the descriptor.
    text = C_FILE.read_text()
    head = text[: text.index("uint8_t img_logo_map[] = {") + len("uint8_t img_logo_map[] = {")]
    rows = [
        "    " + ", ".join(f"0x{v:02x}" for v in alpha[i : i + 21]) + ","
        for i in range(0, len(alpha), 21)
    ]
    C_FILE.write_text(
        head
        + "\n"
        + "\n".join(rows)
        + "\n};\n\nconst lv_img_dsc_t img_logo = {\n"
        + "    .header.cf = LV_IMG_CF_ALPHA_8BIT,\n"
        + "    .header.always_zero = 0,\n"
        + "    .header.reserved = 0,\n"
        + f"    .header.w = {w},\n"
        + f"    .header.h = {h},\n"
        + f"    .data_size = {len(alpha)},\n"
        + "    .data = img_logo_map,\n"
        + "};\n"
    )

    # EEZ project bitmap: black pixels with the same alpha.
    mask = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    mask.putalpha(Image.frombytes("L", (w, h), alpha))
    buf = io.BytesIO()
    mask.save(buf, format="PNG")
    uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    raw = PROJECT.read_text()
    project = json.loads(raw)
    old = next(b["image"] for b in project["bitmaps"] if b["name"] == "logo")
    PROJECT.write_text(raw.replace(old, uri, 1))
    print(f"logo {w}x{h} gamma {gamma} -> {C_FILE.relative_to(ROOT)}, {PROJECT.relative_to(ROOT)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("--gamma", type=float, default=1.0, help="alpha gamma; <1 brightens partial pixels")
    args = ap.parse_args()
    main(args.src, args.gamma)
