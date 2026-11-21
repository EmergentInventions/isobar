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
  (e.g. "slammed", "shocking", "regime" unless quoting). Start straight into the story: no rank
  ("Second, ..."), no outlet count. The intro explains the ranking and the screen shows the numbers.
- `category`: one or two words (e.g. "War in Ukraine", "Climate", "Energy", "Science").
- `place`: "City, Country" if the story has a single location, otherwise null.
- `country`: when `place` is null but the story happens in one country, that country (e.g. "Yemen"),
  shown under the panel instead of a map. Omit it when the story spans several countries.

## 3. editorial.json shape
```json
{
  "radar": [{"id": "<id from radar_pool>", "why": "<=110 chars"}, ...3],
  "stories": {"<id>": {"headline": "", "facts": ["", "", ""], "narration": "", "category": "", "place": null, "country": null}},
  "notes": "anything the host should know (sensitive stories, close calls, Anthropic-related items)"
}
```
Then: `git add editions/<DATE>/editorial.json && git commit -m "Edition <DATE>: editorial" && git push`.

## 4. Pronunciation check (the AI voice)
The draft voice reads `pronunciations.json` at the root of `isobar-editions`. After writing editorial.json,
list the names and unusual words in today's 10 narrations (people, places, organisations, acronyms read as words).
For each one not already in the file, check how espeak says it:
`python3 -c "from kokoro_onnx import Kokoro; k=Kokoro('$HOME/.cache/kokoro/kokoro-v1.0.onnx','$HOME/.cache/kokoro/voices-v1.0.bin'); print(k.tokenizer.phonemize('NAME','en-gb'))"`
(download the two model files from https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0 into ~/.cache/kokoro if missing).
If it is wrong for a British news reader (wrong stress, Anglicised foreign names, letters read as a word), add
`"Name": "phonemes"` in the same IPA style. Use the established English pronunciation where one exists
(Xi = ʃˈiː, Pentagon = pˈɛntəɡɒn). Prefer the short "a" for Arabic names (Riyadh = ɹɪjˈad): "ɑː" sounds like "ar". Years are converted automatically (2030 = "twenty thirty"). Keep entries; never delete one without a reason. Commit it with editorial.json.
