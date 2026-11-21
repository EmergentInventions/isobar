"""Find stumbles in the host's take: a phrase said, then said again.

We keep the last attempt. A repeat only counts if the script itself does not repeat that
phrase, so ordinary repetition in the copy ("Mr Musk ... Mr Musk") is never cut."""
from collections import Counter

from .align import _norm_tokens

MAX_SPAN = 40       # tokens between the start of the first attempt and the restart
MAX_SECONDS = 20.0


def _tokens(words):
    toks, owner = [], []
    for k, (_, _, w) in enumerate(words):
        for t in _norm_tokens(w):
            toks.append(t); owner.append(k)
    return toks, owner


def find(words, script_text):
    """words: [(start, end, word)]. Returns [(cut_from, cut_to)] in seconds."""
    S = _norm_tokens(script_text)
    grams = {n: Counter(tuple(S[i:i + n]) for i in range(len(S) - n + 1)) for n in (2, 3, 4)}
    T, own = _tokens(words)
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
                hit = j
                break
            if hit is not None:
                break
        if hit is not None:
            a, b = words[own[hit]][0] - 0.05, words[own[i]][0] - 0.05
            if drops and a < drops[-1][1]:
                a = drops[-1][0]; drops.pop()
            drops.append((a, b))
        i += 1
    return drops
