"""Generate Echo's original monochrome pixel assets. Run with Pillow installed."""

from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
GLYPHS = {
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    " ": ["00000"] * 7,
}


def lettering(draw, text, x, y, scale=1):
    for char in text:
        for row, bits in enumerate(GLYPHS[char]):
            for col, bit in enumerate(bits):
                if bit == "1":
                    left, top = x + col * scale, y + row * scale
                    draw.rectangle(
                        (left, top, left + scale - 1, top + scale - 1), fill=0
                    )
        x += 6 * scale


def pulse(draw, x, y, radius):
    draw.ellipse((x - 1, y - 1, x + 1, y + 1), fill=0)
    for r in (radius - 8, radius):
        if r > 2:
            draw.arc((x - r, y - r, x + r, y + r), 225, 315, fill=0, width=1)
            draw.arc((x - r, y - r, x + r, y + r), 45, 135, fill=0, width=1)


def save(image, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def main():
    pack = ROOT / "assets/dolphin/custom/Echo/Anims"
    anim = pack / "Echo_Pulse_128x51"
    frames = []
    for index in range(8):
        im = Image.new("1", (128, 51), 1)
        draw = ImageDraw.Draw(im)
        pulse(draw, 25, 23, 5 + index * 2)
        if index >= 3:
            lettering(draw, "ECHO"[: min(4, index - 2)], 53, 17, 2)
        if index == 7:
            lettering(draw, "PRESS OK", 40, 41)
        save(im, anim / f"frame_{index}.png")
        frames.append(im)
    order = list(range(8)) + [7] * 32
    (anim / "meta.txt").write_text(
        "Filetype: Flipper Animation\nVersion: 1\n\nWidth: 128\nHeight: 51\n"
        f"Passive frames: {len(order)}\nActive frames: 0\nFrames order: "
        + " ".join(map(str, order))
        + "\nActive cycles: 0\nFrame rate: 8\n"
        "Duration: 3600\nActive cooldown: 0\nBubble slots: 0\n"
    )
    (pack / "manifest.txt").write_text(
        "Filetype: Flipper Animation Manifest\nVersion: 1\n\n"
        "Name: Echo_Pulse_128x51\nMin butthurt: 0\nMax butthurt: 14\n"
        "Min level: 1\nMax level: 30\nWeight: 1\n"
    )
    for name in ("Radio", "Remotes", "Sessions", "Tools", "Settings"):
        im = Image.new("1", (14, 14), 1)
        d = ImageDraw.Draw(im)
        if name == "Radio":
            pulse(d, 6, 7, 6)
        elif name == "Remotes":
            d.rounded_rectangle((3, 1, 10, 12), radius=2, outline=0)
            d.rectangle((5, 3, 8, 4), fill=0)
            for x, y in ((5, 7), (8, 7), (5, 10), (8, 10)):
                d.point((x, y), fill=0)
        elif name == "Sessions":
            d.line(
                [(1, 11), (1, 3), (5, 3), (7, 5), (12, 5), (12, 11), (1, 11)],
                fill=0,
            )
            d.line((3, 8, 10, 8), fill=0)
        elif name == "Tools":
            d.line((2, 2, 11, 11), fill=0, width=2)
            d.line((2, 11, 11, 2), fill=0, width=2)
            d.rectangle((1, 1, 3, 3), outline=0)
        else:
            for y, x in ((3, 4), (7, 9), (11, 5)):
                d.line((1, y, 12, y), fill=0)
                d.rectangle((x - 1, y - 1, x + 1, y + 1), fill=1, outline=0)
        save(im, ROOT / f"assets/icons/Echo/Echo{name}_14.png")
    icon = Image.new("1", (10, 10), 1)
    pulse(ImageDraw.Draw(icon), 4, 5, 4)
    save(icon, ROOT / "documentation/echo/echo-radio-10.png")
    preview = Image.new("1", (128 * 4, 51 * 2), 1)
    for index, im in enumerate(frames):
        preview.paste(im, ((index % 4) * 128, (index // 4) * 51))
    save(
        preview.resize((1024, 204), Image.Resampling.NEAREST),
        ROOT / "documentation/echo/pulse-preview.png",
    )


if __name__ == "__main__":
    main()
