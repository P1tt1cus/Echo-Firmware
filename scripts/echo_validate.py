"""Validate Echo animation files, private icons, and partial-clone metadata."""

from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

import heatshrink2
from PIL import Image

from asset_packer import pack
from version import GitVersion

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT / "assets/dolphin/custom"
    anim = source / "Echo/Anims/Echo_Pulse_128x51"
    fields = dict(
        line.split(": ", 1)
        for line in (anim / "meta.txt").read_text().splitlines()
        if ": " in line
    )
    width, height = int(fields["Width"]), int(fields["Height"])
    order = list(map(int, fields["Frames order"].split()))
    assert 0 < width <= 128 and 0 < height <= 51
    assert (
        len(order)
        == int(fields["Passive frames"]) + int(fields["Active frames"])
        <= 255
    )
    assert set(order) == set(range(max(order) + 1))
    with tempfile.TemporaryDirectory() as temporary:
        pack(source, temporary, lambda _: None)
        for index in set(order):
            im = Image.open(anim / f"frame_{index}.png")
            assert im.mode == "1" and im.size == (width, height)
            data = (
                Path(temporary) / f"Echo/Anims/Echo_Pulse_128x51/frame_{index}.bm"
            ).read_bytes()
            if data[0] == 1:
                assert len(data) == 4 + int.from_bytes(data[2:4], "little")
                raw = heatshrink2.decompress(data[4:], window_sz2=8, lookahead_sz2=4)
            else:
                assert data[0] == 0
                raw = data[1:]
            assert len(raw) == ((width + 7) // 8) * height
            for y in range(height):
                for x in range(width):
                    assert bool(
                        raw[y * ((width + 7) // 8) + x // 8] & (1 << (x % 8))
                    ) == (im.getpixel((x, y)) == 0)
    api = (ROOT / "targets/f7/api_symbols.csv").read_text().splitlines()
    assert api[1] == "Version,+,87.1,,"
    icons = [line for line in api if ",I_Echo" in line]
    assert len(icons) == 5 and all(line.startswith("Variable,-,") for line in icons)
    for icon in (ROOT / "assets/icons/Echo").glob("*.png"):
        assert Image.open(icon).size == (10, 10)
    # Modern Git adds filter metadata to fetch lines in partial clones.
    responses = [
        "feature/echo-identity",
        subprocess.CalledProcessError(1, "git"),
        "origin\thttps://example.test/echo.git (fetch) [blob:none]\norigin\thttps://example.test/echo.git (push)",
    ]
    with patch.object(GitVersion, "_exec_git", side_effect=responses):
        assert GitVersion(ROOT)._get_git_origins() == {"https://example.test/echo.git"}
    print(
        "PASS: animation frame order, packed pixel round-trip, private icons/API 87.1, partial-clone origin"
    )


if __name__ == "__main__":
    main()
