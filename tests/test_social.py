import json, re
from isobar import social

LIM = {"x": 280, "bluesky": 300, "threads": 500, "instagram": 2200, "tiktok": 4000, "facebook": 5000, "linkedin": 3000}


def test_posts_fit_platform_limits(tmp_path):
    ed = tmp_path / "2026-01-05"; ed.mkdir()
    long = "A very long neutral headline about a summit that ends without an agreement on finance"
    stories = [{"id": f"s{i}", "segment": "top" if i < 7 else "radar", "headline": f"{long} {i}", "label": "Climate",
                "place": "Antalya, Turkey", "sources": 70 - i, "photo": None} for i in range(10)]
    (ed / "script.json").write_text(json.dumps({"source": "kagi", "stories": stories, "all_outlets": ["A", "B"]}))
    text = "The summit ended without an agreement, officials said. " * 6
    shorts = [{"slot": k, "hook": "The summit ended without an agreement, officials said today.",
               "parts": [{"id": f"s{k-1}", "text": text}]} for k in (1, 2, 3)]
    shorts.append({"slot": 4, "hook": "Three stories that got far less coverage today, but matter.",
                   "parts": [{"id": f"s{i}", "text": "Short."} for i in (7, 8, 9)]})
    (ed / "editorial.json").write_text(json.dumps({"shorts": shorts}))
    files = social.build(ed)
    assert len(files) == 8 and all(f.name.startswith("isobar-2026-01-05-social-") for f in files)
    for f in files:
        key = f.stem.rsplit("-", 1)[1]
        if key not in LIM: continue
        for block in re.split(r"\n\n(?====|\w+ reply)", f.read_text())[1:]:
            body = block.split("\n", 1)[1]
            n = social.x_len(body) if key == "x" else len(body)
            assert n <= LIM[key], (f.name, n, body)
