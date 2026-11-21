# Isobar News pronunciation style

How the AI voice (Kokoro, "George", British English) should say things. This covers pronunciation only;
editorial rules live in EDITORIAL.md. Sources are in brackets; [house] means our own rule.

## 1. Names and places
- Use the established English form where one exists (Munich, Florence, Kyiv). [BBC Pronunciation Unit]
- Otherwise use the local pronunciation, anglicised only where a sound does not exist in English. [BBC Pronunciation Unit]
- Say people's names the way they say them themselves. [BBC Pronunciation Unit]
- Use the established English form of well-known foreign leaders' names: Xi = "shee". [house]
- No particular regional accent: standard British English. [BBC Pronunciation Unit]
- Consistency: once a name is in `pronunciations.json`, it is said the same way in every edition. [BBC Pronunciation Unit practice]

## 2. Abbreviations and acronyms
- Acronyms said as words: Nato, Nasa, Opec, Unesco, Unicef, Covid, Fifa, Uefa, Aids. The BBC writes these in
  upper and lower case to show they are said as words. [BBC News Styleguide]
- Initialisms are spelled out letter by letter: UN, EU, IMF, WHO, IAEA, UNHCR, BBC, NHS, IPO, AI. [BBC News Styleguide]
  The voice spells any word in capitals letter by letter unless it is on the said-as-a-word list in `tts_draft.py`.
- Markets: FTSE = "Footsie" ("the Footsie hundred"); S&P 500 = "S and P five hundred", run together. [Morningstar; house]
- Titles are said in full: Jr = Junior, Sr = Senior, Sen. = Senator, Rep. = Representative, Gen. = General. [house]

## 3. Numbers, money and dates as spoken
- Years: 2030 = "twenty thirty", 1998 = "nineteen ninety-eight", 2005 = "two thousand and five". [house, British usage]
- Percentages: "per cent". [BBC News Styleguide]
- Money: "£3m" = "three million pounds", "$6bn" = "six billion dollars", "£4.50" = "four pounds fifty". [house]
- Pence: "1p" = "one penny", "50p" = "fifty pence". [Guardian style guide]
- Dates: day before month, "the twenty-first of November". [BBC News Styleguide]

## 4. Words spelled the same but said differently (heteronyms)
The voice cannot always tell these apart, so check them in every script:
live (lɪv "to live" / laɪv "a live broadcast"), read, lead, close, wind, tear, wound, minute, record, present,
content, object, project, refuse, row, bow, desert, use, house, produce, permit, conduct.
"live" as a verb is handled automatically in lists and before in/on/with ("live, work or study").
If a sentence is still ambiguous, rephrase it ("people who live there" rather than "live, work") or add a
phrase to `pronunciations.json`. [house]

## 5. How the voice applies this (automatic)
1. Titles (Jr, Sr, Sen., ...) are expanded; money, pence and years are written out as spoken.
2. Heteronym rules fix "live" as a verb.
3. `pronunciations.json` entries override everything else, matched as whole words, case-sensitively.
4. Capitals are spelled out letter by letter unless they are acronyms said as words.
5. Everything else goes through espeak (en-gb).

Sources: BBC News Styleguide (A to Z, numbers, names); BBC Pronunciation Unit (BBC Editors blog
"You say tomato", 2006); Guardian and Observer style guide; Morningstar glossary (FTSE).
