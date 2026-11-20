# Isobar

**A daily ten-minute video briefing on the world's news, with every source shown.**
Published once a day on YouTube. Website: [isobar.news](https://isobar.news)

This repository is the whole pipeline, in the open, so anyone can check how stories are chosen.

## How stories are chosen

1. **Count outlets.** For each story we count the distinct news outlets that reported it.
   Aggregators and platforms (Kagi, Google News, YouTube, AllSides, Techmeme and similar) never count.
2. **Merge duplicates.** Reports that are clearly about the same event are counted once.
3. **Most covered (7 stories).** The World and USA stories with the most outlets, at most two per country.
   The count is shown on screen for every story.
4. **Below the Radar (3 stories).** Stories with less coverage, picked for impact using a published rubric:
   people affected, durability, precedent, and whether a primary source exists. The reason for each pick is
   shown on screen. Rules: [`ops/EDITORIAL.md`](ops/EDITORIAL.md).

The code for each step: [`isobar/rank.py`](isobar/rank.py) (the selection rule),
[`isobar/script.py`](isobar/script.py) (the script), [`isobar/render.py`](isobar/render.py) (the video).

## Daily run

| Time (UTC) | Step |
|---|---|
| 12:00 | Kagi News publishes its daily batch (sometimes later) |
| from 12:02 | `fetch_kagi.py` checks every minute until today's batch exists, until 12:45 |
| if no batch by 12:45 | `fetch_backup.py` reads outlets' own feeds and clusters the stories itself |
| then | `rank.py` and `script.py` build an automatic draft |
| then | the editorial step picks Below the Radar and rewrites for the voice (`ops/EDITORIAL.md`) |
| then | a draft video renders; the host records one take; the final video renders |
| 14:00 | publish |

Daily editions (stories, scripts, videos) are kept in a separate private repository.

## Run it yourself

```bash
pip install -r requirements.txt            # plus ffmpeg; festival + festvox-us-slt-hts for the draft voice
python -m isobar.fetch_kagi --base out     # or: python -m isobar.fetch_backup --base out
python -m isobar.rank --base out
python -m isobar.script --base out
python -m isobar.tts_draft out/editions/$(date -u +%F)
python isobar/render.py out/editions/$(date -u +%F) --audio audio_draft
```

## Sources, credit and licences

- **Kagi News** ([news.kagi.com](https://news.kagi.com)) is our primary source for story clustering and summaries.
  Its data is licensed [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/); it is fetched at run time
  and is **not** stored in this repository.
- The backup feed list (`data/kagi_core_feeds.py`) comes from Kagi's MIT-licensed
  [kite-public](https://github.com/kagisearch/kite-public) repository.
- Fonts: EB Garamond and Inter, both under the SIL Open Font License.
- Map data: Natural Earth via Basemap. Place lookup: GeoNames via `geonamescache` (CC BY 4.0).
- Code in this repository: MIT, © Emergent Inventions LLC.
