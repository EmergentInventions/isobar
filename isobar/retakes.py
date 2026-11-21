"""Find stumbles in the host's take: a phrase said, then said again.

We keep the last attempt. A repeat only counts if the script itself does not repeat that
phrase, so ordinary repetition in the copy ("Mr Musk ... Mr Musk") is never cut."""
import difflib
from collections import Counter

from .align import _norm_tokens

MAX_SPAN = 40       # tokens between the start of the first attempt and the restart
MAX_SECONDS = 20.0


FILLERS = {"uh", "um", "umm", "uhm", "er", "erm", "ah", "hmm", "mm"}


def _tokens(words):
    toks, owner = [], []
    for k, (_, _, w) in enumerate(words):
        for t in _norm_tokens(w):
            if t not in FILLERS:
                toks.append(t); owner.append(k)
    return toks, owner


def _heard(S, T):
    return sum(n for _, _, n in difflib.SequenceMatcher(None, S, T, autojunk=False).get_matching_blocks())


def _safe(S, T, j, i, base):
    """Cutting T[j:i] must not lose script words: the restart has to say them again."""
    return _heard(S, T[:j] + T[i:]) >= base


def find(words, script_text):
    """words: [(start, end, word)]. Returns [(cut_from, cut_to)] in seconds."""
    S = _norm_tokens(script_text)
    grams = {n: Counter(tuple(S[i:i + n]) for i in range(len(S) - n + 1)) for n in (2, 3, 4)}
    T, own = _tokens(words)
    base = _heard(S, T)
    doubled = {(a, b) for a, b in zip(S, S[1:]) if a == b}
    drops, i = [], 0
    while i < len(T):
        hit = None
        for j in range(max(0, i - MAX_SPAN), i - 1):      # j = start of the earlier attempt, i = restart
            for n in (4, 3, 2):
                g = tuple(T[i:i + n])
                if len(g) < n or tuple(T[j:j + n]) != g:
                    continue
                c = grams[n].get(g, 0)
                if c != 1:                    # not in the script (misheard) or the script repeats it
                    continue
                if n == 2 and (i - j > 6 or words[own[i]][0] - words[own[i - 1]][1] < 0.15):
                    continue                  # two-word restarts only when short and after a stop
                if own[j] == own[i] or words[own[i]][0] - words[own[j]][0] > MAX_SECONDS:
                    continue
                hit, used = j, n
                break
            if hit is not None:
                break
        # a single word said twice after a stop ("third... third"), unless the script doubles it
        if hit is None and i > 0 and T[i] == T[i - 1] and len(T[i]) >= 3 and (T[i], T[i]) not in doubled \
                and own[i] != own[i - 1] and words[own[i]][0] - words[own[i - 1]][1] >= 0.1:
            hit, used = i - 1, 1
        r = i
        if hit is not None:
            # the second attempt may begin a word or two earlier ("buildings- and two nearby buildings")
            r = next((x for x in (i, i - 1, i - 2) if x > hit and own[x] != own[hit] and _safe(S, T, hit, x, base)), None)
            if r is None:
                print(f"retakes: kept {' '.join(T[hit:i])!r} (cutting it would lose script words)")
                hit = None
        if hit is not None:
            a, b = words[own[hit]][0] - 0.05, words[own[r]][0] - 0.05
            if drops and a < drops[-1][1]:     # overlaps the previous cut: a restart of a restart
                a, b = min(a, drops[-1][0]), max(b, drops[-1][1]); drops.pop()
            drops.append((a, b))
            i += max(1, used)
            continue
        i += 1
    return drops


def confirmed(drops, words, script_text):
    """Keep only cuts that lose no script words in this (independent) transcript."""
    S = _norm_tokens(script_text)
    T, own = _tokens(words)
    base = _heard(S, T)
    keep = []
    for a, b in sorted(drops):
        # drop words that lie mostly inside the cut
        inside = lambda k: min(b, words[k][1]) - max(a, words[k][0]) > 0.5 * max(0.01, words[k][1] - words[k][0])
        T2 = [t for t, k in zip(T, own) if not inside(k)]
        if _heard(S, T2) >= base:
            keep.append((a, b))
        else:
            print(f"retakes: kept {a:.1f}s to {b:.1f}s (cutting it would lose script words)")
    merged = []
    for a, b in keep:
        if merged and a <= merged[-1][1] + 0.05:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return merged
