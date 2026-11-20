# Isobar editorial step (run daily by a Claude scheduled task)

Input: `editions/<DATE>/candidates.json` in `EmergentInventions/isobar-editions`.
Output: `editions/<DATE>/editorial.json`, committed and pushed. Pushing it triggers the draft render.

## 1. Pick Below the Radar (exactly 3 from `radar_pool`)
Score each candidate 0–3 on each of these, and pick the 3 highest totals:
- **People affected**: how many people's lives, money, health or rights it changes.
- **Durability**: will it still matter in a year? Decisions, laws, data, discoveries beat incidents.
- **Precedent**: a first, a reversal, or a new rule.
- **Primary source**: a study, ruling, official dataset or report exists.
Avoid celebrity, sport, single crimes without wider consequence, and anything already in the top 7.
Prefer different categories across the three. Do not pick stories about Anthropic or Claude
(conflict of interest): leave those to the host and mention them in `notes`.
`why`: one line, at most 110 characters, starting with the strongest criterion, e.g.
"Primary source: IEA World Energy Outlook 2026. Affects global power and climate targets".

## 2. Rewrite all 10 stories for the screen and the voice
Use only facts present in that story's `summary`, `points` and `headlines`. Never add facts.
- `headline`: at most 70 characters, neutral, no adjectives of judgement, no question marks.
- `facts`: exactly 3, each at most 90 characters, concrete (numbers, places, who did what).
- `narration`: 90–150 words, spoken style, British English, attribute every claim to who made it
  ("the ministry says", "according to the IEA"). No opinion, no speculation, no loaded words
  (e.g. "slammed", "shocking", "regime" unless quoting). Do not start with the ordinal; the
  pipeline adds "Second, covered by thirty-two outlets." itself.
- `category`: one or two words (e.g. "War in Ukraine", "Climate", "Energy", "Science").
- `place`: "City, Country" if the story has a single location, otherwise null.

## 3. editorial.json shape
```json
{
  "radar": [{"id": "<id from radar_pool>", "why": "<=110 chars"}, ...3],
  "stories": {"<id>": {"headline": "", "facts": ["", "", ""], "narration": "", "category": "", "place": null}},
  "notes": "anything the host should know (sensitive stories, close calls, Anthropic-related items)"
}
```
Then: `git add editions/<DATE>/editorial.json && git commit -m "Edition <DATE>: editorial" && git push`.
