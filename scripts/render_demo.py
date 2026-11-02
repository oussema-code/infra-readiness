"""Render a condensed replay of recorded CLI results; requires optional Pillow."""

import json
import os
from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageFont

from infra_readiness.models import Result, Status
from infra_readiness.report import readable

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "docs/demo"
STAGES = [
    ("baseline", "Healthy deployment", "lab.yaml"),
    ("invalid-hostname", "Invalid hostname: report the resolver's evidence", "invalid-hostname.yaml"),
    ("delayed-response", "Delayed API: timeout is UNKNOWN", "delayed-response.yaml"),
    ("broken-proxy", "Wrong proxy upstream: direct API still passes", "lab.yaml"),
    ("proxy-recovered", "Configuration restored: all checks pass", "lab.yaml"),
]


def main():
    font_path = os.environ.get("DEMO_FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
    font = ImageFont.truetype(font_path, 19)
    title_font = ImageFont.truetype(font_path, 23)
    frames = []
    for index, (stage, title, config) in enumerate(STAGES, 1):
        report = json.loads((DEMO / "evidence" / f"{stage}.json").read_text())
        results = [Result(**{**entry, "status": Status(entry["status"])}) for entry in report["checks"]]
        frame = Image.new("RGB", (1200, 680), "#0d1117")
        draw = ImageDraw.Draw(frame)
        draw.rectangle((0, 0, 1200, 58), fill="#161b22")
        draw.text((30, 16), "Infrastructure Readiness & Recovery Lab", font=title_font, fill="#f0f6fc")
        draw.text((30, 84), f"{index}/5  {title}", font=title_font, fill="#79c0ff")
        draw.text((30, 130), f"$ infra-check run /config/{config}", font=font, fill="#d2a8ff")
        y = 176
        for line in readable(results).splitlines():
            color = "#c9d1d9"
            for prefix, value in {"PASS": "#7ee787", "FAIL": "#ff7b72", "UNKNOWN": "#e3b341"}.items():
                if line.startswith(prefix):
                    color = value
            for wrapped in textwrap.wrap(line, width=94, replace_whitespace=False, drop_whitespace=False):
                draw.text((30, y), wrapped, font=font, fill=color)
                y += 26
        if y > 586:
            raise ValueError(f"Recorded output is too long for demo frame: {stage}")
        draw.line((30, 606, 1170, 606), fill="#30363d", width=1)
        draw.text((30, 624), "Actual recorded results | condensed replay | local Docker lab", font=font, fill="#8b949e")
        frames.append(frame)
    frames[0].save(DEMO / "demo.gif", save_all=True, append_images=frames[1:],
                   duration=[5000, 5000, 5000, 6000, 5000], loop=0, optimize=True)
    print(f"Rendered {len(frames)} frames from recorded evidence: {DEMO / 'demo.gif'}")


if __name__ == "__main__":
    main()
