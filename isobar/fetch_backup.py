"""Backup source: read outlets' own RSS feeds and cluster headlines into stories ourselves.

Feed list: Kagi's public, MIT-licensed core feed list (data/kagi_core_feeds.py,
from github.com/kagisearch/kite-public). Used only if Kagi has no fresh batch.
Clustering: TF-IDF over title + description, average-linkage clustering on cosine
distance. A story needs at least 3 distinct outlets.
"""
import argparse
import calendar
import datetime as dt
import html
import re
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import feedparser
import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer

from .common import ROOT, UA, edition_dir, norm_domain, save, today_utc, unique_outlets

CATEGORIES = ["World", "Business", "Science", "USA"]
WINDOW_H = 30
socket.setdefaulttimeout(20)


def feeds():
    ns = {}
    exec((ROOT / "data" / "kagi_core_feeds.py").read_text(), ns)
    f = ns["feeds"]
    return [(c, u) for c in CATEGORIES for u in f.get(c, [])]


def clean(t):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(t or ""))).strip()


def read(item):
    cat, url = item
    try:
        d = feedparser.parse(url, agent=UA)
    except Exception:
        return []
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=WINDOW_H)
    out = []
    for e in d.entries[:60]:
        t = e.get("published_parsed") or e.get("updated_parsed")
        if t and dt.datetime.fromtimestamp(calendar.timegm(t), dt.timezone.utc) < cutoff:
            continue
        link = e.get("link", "")
        out.append({"category": cat, "title": clean(e.get("title")), "desc": clean(e.get("summary"))[:400],
                    "link": link, "domain": norm_domain(urlparse(link).netloc or urlparse(url).netloc)})
    return out


def cluster(items, threshold=0.72):
    texts = [f"{i['title']} {i['title']} {i['desc']}" for i in items]
    X = TfidfVectorizer(stop_words="english", min_df=1, max_df=0.5, sublinear_tf=True).fit_transform(texts)
    labels = AgglomerativeClustering(n_clusters=None, metric="cosine", linkage="average",
                                     distance_threshold=threshold).fit_predict(X.toarray())
    stories = []
    for lab in set(labels):
        idx = np.where(labels == lab)[0]
        group = [items[i] for i in idx]
        names = unique_outlets([g["domain"] for g in group])
        if len(names) < 3:
            continue
        # headline closest to the cluster centre
        sub = X[idx]
        centre = np.asarray(sub.mean(axis=0))
        best = idx[int(np.argmax(sub @ centre.T))]
        cats = [g["category"] for g in group]
        stories.append({
            "id": f"backup-{lab}", "category": max(set(cats), key=cats.count),
            "title": items[best]["title"], "summary": items[best]["desc"], "points": [],
            "location": None, "domains": sorted({g["domain"] for g in group}),
            "outlets": names, "outlet_count": len(names),
            "headlines": [g["title"] for g in group][:12], "links": [g["link"] for g in group][:12],
        })
    return sorted(stories, key=lambda s: -s["outlet_count"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=".")
    ap.add_argument("--date", default=today_utc())
    a = ap.parse_args()
    with ThreadPoolExecutor(24) as ex:
        items = [i for batch in ex.map(read, feeds()) for i in batch if i["title"]]
    print(f"backup: {len(items)} headlines from outlet feeds")
    stories = cluster(items)
    save(edition_dir(a.base, a.date) / "stories.json",
         {"source": "backup", "created_at": dt.datetime.now(dt.timezone.utc).isoformat(), "stories": stories})
    print(f"backup: {len(stories)} stories with 3+ outlets")
    return 0 if stories else 3


if __name__ == "__main__":
    sys.exit(main())
