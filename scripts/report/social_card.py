"""Render assets/social-card.html (written by build_pages.py) to assets/social-card.jpg,
the 1200x630 share preview image named in both pages' Open Graph and Twitter card tags.

Firefox renders the card headless at twice the size (the card's ?scale=2 zoom), with a
throwaway profile, and ImageMagick scales it down to 1200x630, which is sharper than
rendering at 1x. The dark theme ships; --light writes assets/social-card-light.jpg for
comparison.

Run from the repository root, after build_pages.py:
    python3 -I scripts/report/social_card.py [--light]

Needs firefox and magick (ImageMagick 7) on the PATH. Check the result at about 400px
wide, the size it is mostly seen at, not at full size.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "assets" / "social-card.html"
W, H, SCALE = 1200, 630, 2


def main():
    light = "--light" in sys.argv[1:]
    out = ROOT / "assets" / ("social-card-light.jpg" if light else "social-card.jpg")
    for tool in ("firefox", "magick"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found on the PATH")
    if not SRC.exists():
        sys.exit(f"{SRC.relative_to(ROOT)} is missing: run build_pages.py first")
    with tempfile.TemporaryDirectory() as tmp:
        profile = Path(tmp) / "profile"
        profile.mkdir()
        shot = Path(tmp) / "card.png"
        # The card zooms itself by ?scale (headless Firefox ignores a device-pixel ratio
        # set in the profile), so the window is twice the card's size.
        url = SRC.as_uri() + f"?scale={SCALE}" + ("&theme=light" if light else "")
        subprocess.run(["firefox", "--headless", "--no-remote", "--profile", str(profile),
                        f"--window-size={W * SCALE},{H * SCALE}",
                        "--screenshot", str(shot), url],
                       check=True, capture_output=True, timeout=120)
        size = subprocess.run(["magick", "identify", "-format", "%wx%h", str(shot)],
                              check=True, capture_output=True, text=True).stdout
        if size != f"{W * SCALE}x{H * SCALE}":
            sys.exit(f"screenshot is {size}, expected {W * SCALE}x{H * SCALE}")
        # Dark grounds band under JPEG, so the quality is set high.
        subprocess.run(["magick", str(shot), "-filter", "Lanczos", "-resize", f"{W}x{H}!",
                        "-strip", "-interlace", "Plane", "-quality", "94", str(out)],
                       check=True)
    print(f"wrote {out.relative_to(ROOT)} ({W}x{H}) from {SRC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
