"""Find where each script section starts in the host's take, by matching the transcript to the script."""
import difflib
import re

from num2words import num2words


def _norm_tokens(text):
    out = []
    for raw in re.split(r"[\s\-–—/]+", text.lower().replace(",", "")):
        t = re.sub(r"[^a-z0-9']", "", raw)
        if not t:
            continue
        m = re.fullmatch(r"(\d+)(st|nd|rd|th)", t)
        if m:
            t = num2words(int(m.group(1)), to="ordinal", lang="en_GB")
        elif t.isdigit():
            t = num2words(int(t), lang="en_GB")
        out += [x for x in re.split(r"[\s\-]+", t.replace(",", "")) if x]
    return out


def section_starts(sections, words):
    """sections: [(name, text)]; words: [(start, end, word)] in order.
    Returns the time each section starts (seconds), or None if alignment is unreliable."""
    s_tok, s_bound = [], []
    for _, text in sections:
        s_bound.append(len(s_tok)); s_tok += _norm_tokens(text)
    t_tok, t_word = [], []
    for k, (_, _, w) in enumerate(words):
        for tok in _norm_tokens(w):
            t_tok.append(tok); t_word.append(k)
    sm = difflib.SequenceMatcher(None, s_tok, t_tok, autojunk=False)
    m = {}
    for a, b, n in sm.get_matching_blocks():
        for d in range(n):
            m[a + d] = b + d
    coverage = len(m) / max(1, len(s_tok))
    starts, prev_last = [], -1
    for k, sb in enumerate(s_bound):
        end = s_bound[k + 1] if k + 1 < len(s_bound) else len(s_tok)
        hit = next((m[i] for i in range(sb, min(end, sb + 12)) if i in m), None)
        if hit is None:
            return None, coverage
        wi = t_word[hit]
        # step back over any unmatched words at the start of the section (e.g. a misheard first word)
        back = min(2, next(i for i in range(sb, end) if i in m) - sb)
        wi = max(prev_last + 1, wi - back, 0)
        starts.append(wi)
        matched_here = [t_word[m[i]] for i in range(sb, end) if i in m]
        prev_last = max(matched_here) if matched_here else wi
    if any(b <= a for a, b in zip(starts, starts[1:])):
        return None, coverage
    times = [0.0]
    for wi in starts[1:]:
        prev_end, this_start = words[wi - 1][1], words[wi][0]
        times.append((prev_end + this_start) / 2 if this_start - prev_end < 1.2 else this_start - 0.4)
    return times, coverage
