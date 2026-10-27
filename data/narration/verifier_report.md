# Verifier report

Items (text variants) processed: **174** · verified ok: 100 · repaired by the Verifier LLM: 57 · rejected (fact card stays): 17

## Failure recovery

* status of the 174 text variants: verified 145 · recovered 12 · fallback to the fact card 17
* recovered = a step failed (unreadable answer, retried call) but a checked text was still produced; fallback = no verified text, the deterministic fact card stays

| agent / step | what happened | count |
|---|---|---|
| pre-check | rejected | 17 |
| pre-check | stock_phrase_trimmed | 12 |
| verifier | invalid_json | 1 |

## Deterministic pre-check (before the Verifier LLM)

* first narrator text failed the pre-check: 84 of 174 (48 %); sent back to the Narrator once: 84
* unsupported numbers: 2 · unknown names: 0 · overlay longer than 90 characters: 0

## Professional claims (config/claim_rules.json)

* texts containing a rule-matched claim: 95 · with at least one unsupported claim: 35 · of those kept after repair: 27, dropped: 8

| rule | supported | unsupported |
|---|---|---|
| chaos | 35 | 0 |
| control_regime | 0 | 1 |
| dominance | 15 | 19 |
| elite_player | 4 | 5 |
| high_press | 54 | 4 |
| turnaround | 0 | 10 |

### Examples of claim repairs

* **analyst/hu, 2'** – claim "letámad" (rule high_press) not supported by {"minute": 2, "regime": "balanced", "control_index": -0.073, "teams": {"T1": {"tilt": 100.0, "possession": 50.0, "ppda": null, "momentum": 0.4}}}
  * before: _Korai gól: Mathis Byrne vezetést szerez a 2. percben_ / Mathis Byrne jobb lábbal 10,6 méterről lőtt gólt 98,1 km/h sebességgel, amivel a Northbridge FC U19 megszerezte a vezetést 0-1-re. A találat várható gól értéke 0,198 volt, a csapat pedig intenzívebb letámadás és 100%-os területi fölény mellett dominál a pályán a mérkőzés elején.
  * after: _Mathis Byrne góljával vezet a Northbridge FC U19 a 2. percben_ / Mathis Byrne jobb lábbal 10,6 méterről, 98,1 km/h-s erős lövéssel szerzett vezetést a Northbridge FC U19-nek (0-1). A találat után a mérkőzés kiegyenlített labdabirtoklás mellett a Northbridge FC U19 fokozottan nyomásgyakorlást alkalmaz és jobb passzpontosságot mutat.
* **fan/hu, 2'** – claim "nyomást gyakorol" (rule high_press) not supported by {"minute": 2, "regime": "balanced", "control_index": -0.073, "teams": {"T1": {"tilt": 100.0, "possession": 50.0, "ppda": null, "momentum": 0.4}}}
  * before: _Mathis Byrne góljával 0-1 a 2. percben_ / Mathis Byrne már a 2. percben vezetéshez juttatta a Northbridge FC U19-et. A találat 10,6 méterről, jobblábbal, 98,1 km/h sebességgel született.
  * after: _Mathis Byrne góljával vezet Northbridge_ / Mathis Byrne már a 2. percben betalált, így Northbridge szerezte meg a vezetést 0-1-re. Az irányítás eddig kiegyenlített, 50-50 százalék a labdabirtoklás.
* **fan/hu, 2'** – claim "letámad" (rule high_press) not supported by {"minute": 2, "regime": "balanced", "control_index": -0.073, "teams": {"T1": {"tilt": 100.0, "possession": 50.0, "ppda": null, "momentum": 0.4}}}
  * before: _Mathis Byrne góljával 0-1 a Northbridge FC U19-nek_ / Mathis Byrne már a 2. percben betalált, és ezzel megszerezte a vezetést csapatának. A mérkőzés kiegyenlített, de Northbridge dominál a játékmezőnyben és a letámadásban.
  * after: _Mathis Byrne gyors góljával vezet Northbridge FC U19_ / Már a 2. percben Mathis Byrne megszerezte a vezetést Northbridge FC U19 számára. Egy lendületes, 10,6 méterről jobb lábbal leadott lövés hozta meg az előnyt.

### Examples of number / name repairs

* **fan/hu, 38'** – bad numbers ['10'], bad names []
  * before: _Szymon Winther nagy helyzete kimaradt 38'-nál_ / Szymon Winther közel járt az egyenlítéshez, de 6 méterről mellé lőtt. Vallora United 2-1-re vezet, de a meccs nagyon kiegyenlített maradt.
  * after: _Szymon Winther nagy helyzete kimaradt a 38. percben_ / Szymon Winther közel járt az egyenlítéshez, de 6 méterről mellé lőtt. Vallora United 2-1-re vezet, de a meccs továbbra is nagyon kiegyenlített.
* **fan/en, 70'** – bad numbers ['20'], bad names []
  * before: _Northbridge trails 3-2 at 70', fighting for the title_ / Northbridge FC U19 are behind by a single goal at 70 minutes but have held decent control through much of the match. The intense pressing from Northbridge is clear, though Vallora currently carries a bit more momentum in this chaotic endgame.
  * after: _Northbridge trails 3-2 at 70', fighting for the title_ / Northbridge FC U19 are behind by one goal at 70 minutes but have managed to keep good control for much of the match. Their pressing is intense, although Vallora has slightly more momentum in this chaotic phase.

### Rejected items (the fact card stays on screen)

* fan/hu 10' (fan): ['pre-check failed after repair']
* analyst/hu 15' (focus): ['pre-check failed after repair']
* analyst/hu 30' (focus): ['pre-check failed after repair']
* analyst/hu 31' (analyst): ['pre-check failed after repair']
* analyst/hu 40' (focus): ['pre-check failed after repair']
* analyst/hu 41' (analyst): ['pre-check failed after repair']
* analyst/hu 59' (analyst): ['pre-check failed after repair']
* fan/en 60' (fan): ['pre-check failed after repair']
* fan/hu 60' (fan): ['pre-check failed after repair']
* analyst/en 63' (analyst): ['pre-check failed after repair']

## Language spot-check (5 lines per language)

### hu
* 2' [analyst] Mathis Byrne góljával vezet a Northbridge FC U19 a 2. percben
* 2' [fan] Mathis Byrne gyors góljával vezet Northbridge FC U19
* 5' [analyst] 5': Northbridge vezetés, kaotikus játék és területi fölény
* 10' [analyst] Kiegyenlített irányítás, de 1-0-ra vezet a Northbridge FC U19
* 15' [analyst] Kiegyensúlyozott játék, Vallora nagyobb területi fölénnyel és intenzívebb letámadással

### en
* 2' [analyst] Byrne's goal gives Northbridge early lead and full field tilt
* 2' [fan] Mathis Byrne scores early for Northbridge
* 5' [analyst] Chaotic match: Northbridge FC U19 lead 1-0 at 5'
* 10' [analyst] Northbridge leads 1-0, balanced control, Vallora pressing with intensity
* 10' [fan] Northbridge leads 1-0, Vallora pressing intensely

