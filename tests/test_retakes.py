"""Run: python -m pytest tests  (or python tests/test_retakes.py)"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from isobar.retakes import find, confirmed


def mk(said):
    out, t = [], 0.0
    for w in said.split():
        if w == "|":
            t += 0.6; continue
        out.append((t, t + 0.3, " " + w)); t += 0.35
    return out


CASES = [
    ("And third | Third, reported by ten outlets.", "And third, reported by ten outlets.", "third"),
    ("The president said the deal | the president said the deal was done.", "The president said the deal was done.", "The president said the deal"),
    ("It is not yet co- | It is not yet confirmed whether", "It is not yet confirmed whether", "It is not yet co-"),
    ("two nearby buildings- | and two nearby buildings on", "and two nearby buildings on", "two nearby buildings-"),
    ("and two nearby buildings- | and two nearby buildings on", "and two nearby buildings on", "and two nearby buildings-"),
    ("the Kerch | the Kerch | the Kerch Bridge linking", "the Kerch Bridge linking", "the Kerch the Kerch"),
    ("Mr Musk said no. Mr Musk said yes.", "Mr Musk said no. Mr Musk said yes.", None),
    ("it was very very good", "it was very very good", None),
    ("covered by eight outlets. Second, covered by eight outlets.", "covered by eight outlets. Second, covered by eight outlets.", None),
    ("and threatened a more peaceful and more pit | and threatened a more painful response", "and threatened a more painful response", "and threatened a more peaceful and more pit"),
]


def test_cases():
    for said, script, expected in CASES:
        w = mk(said)
        cuts = confirmed(find(w, script), w, script)
        got = " ".join(x.strip() for a, b in cuts for s, e, x in w if a <= s < b) or None
        assert got == expected, (said, got)


if __name__ == "__main__":
    test_cases(); print("ok")
