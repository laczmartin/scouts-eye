# Scout's Eye – rövid segédlet (magyar)

**Mi ez?** A *Scout's Eye* egy **teljesen szintetikus** U19-es torna utolsó, címdöntő meccsének (M12) megmagyarázható, élő feliratozása. Minden szám az eseményekből számolt tényekből jön; a szövegeket öt együttműködő ügynök írja és ellenőrzi (Microsoft Foundry + Microsoft Agent Framework). A csapatok és a játékosok kitaláltak, a helyszín semleges.

## Fülek és gombok

| elem | mit csinál |
|---|---|
| **Meccs** | 2D pálya az eseményekből, meccsóra futballos jelöléssel (45+3', 90+2'), eredményjelző, ▶ lejátszás, 1×/10×/60× sebesség, idővonal gól- és pillanat-jelölőkkel (kattintható). Jobbra a feliratok a meccsórához szinkronban. |
| Szurkolói / Elemzői / együtt | a felirat hangneme: *szurkolói* = kevés szám, érzelem; *elemzői* = metrikák, percentilisek, PPDA, field tilt; *együtt* = a kettő egymás mellett ugyanabból a tényből |
| HU / EN | a felület és a feliratok nyelve |
| Semleges / Northbridge / Vallora | klubnézet: a szurkolói feliratok az adott csapat szemszögéből |
| Játékosfókusz | egy játékost követ egész meccsen; fókusz-narráció a négy ★ tehetséghez készült, a többi játékosnál a profil nyitható meg |
| **Ügynök-nyomkövetés** | a kiválasztott felirat útja lépésenként: ténykártya → Match Analyst → Narrator-változatok → determinisztikus előszűrő → javítókör → Verifier → végső; hívásonként késés, token, kvóta-várakozás (429). Jobbra az összesítés és a szerepek ábrája. |
| **Játékosprofil** | 11 kategória sávokon, pozíció-pontszám, rang a poszton, percek, megbízhatóság, élő KPI-k az aktuális óráig |
| **Scouting** | rangsor posztonként (csak ≥ 180 perc), külön „kevés adat” lista, a 4 ★ tehetség, scouting-jegyzetek HU/EN |
| **Összefoglaló** | meccs utáni összefoglaló szurkolói/elemzői hangnemben, HU/EN |
| **Névjegy** | architektúra, adatnyilatkozat, dokumentáció |
| **▶ Demo** | 90 másodperces, kurált bemutató 6 lépésben |
| **?** | ez a segédlet röviden, HU/EN |

Billentyűk: szóköz = lejátszás/szünet, ← → = ±1 perc, Esc = ablak bezárása.

## A demó 3 lépésben

1. Nyomd meg a sárga **▶ Demo** gombot (jobb felül): korai gól → elemzői/szurkolói egymás mellett → bizonyíték → ügynök-nyomkövetés javítással → játékosfókusz → a 49' győztes gól és a cím.
2. Kattints bármelyik **feliratra**: alul megnyílik a bizonyíték- és a nyomkövető panel.
3. Nézd meg a **Scouting** fület: rangsorok, a 4 elrejtett tehetség (modell-rang és *Validation* rang), jegyzetek.

## Jelölések

- **★** – *kísérletben elrejtett tehetség: a modell nem tudja, ki az.* Négy fiatal (15–16 éves) játékos, akiket a szintetikus adatokba rejtettünk, hogy ellenőrizzük, megtalálja-e őket a rendszer. A **Validation** felirat a rejtett valós rangot mutatja, kizárólag ellenőrzésre; a modell ezt nem látja.
- **kevés adat** – 180 tornaperc alatt (élőben 20 perc alatt) a játékos nem kerül rangsorba, csak jelzést kap.
- **megbízhatóság** – a percek alapján: *very low* < 90, *low* 90–179, *medium* 180–359, *good* ≥ 360.
- **ténykártya (szaggatott keret)** – élőben azonnal, LLM nélkül, sablonból megjelenő tény („GÓL – Andreou (büntető), 49' – Vallora 3–2”); amikor az ügynökök szövege elkészül és a Verifier jóváhagyja, lecseréli („frissítve ténykártyáról”).
- **tartalék: ténykártya** – ehhez a változathoz nincs igazolt ügynök-szöveg (elutasították, vagy egy ügynökhívás az újrapróbálások után is hibás volt), ezért a ténykártya marad a képernyőn.
- **címke (determinisztikus)** – rövid felirat a játékos nevével, ha egy küszöböt átlép: nagyon nehéz sikeres passz, legalább 100 km/h-s lövés, vagy a meccs eddigi leggyorsabb futása. Az adatból számolva, AI nélkül. A pálya alatti eseménysor, a bizonyíték-panel és az élő játékoskártya mutatja a passz távját, nehézségét, a vonaltörő passzokat és a labda- / lövéssebességet.
- **↺ helyreállt** – egy lépés hibázott (olvashatatlan válasz vagy újrapróbált hívás), de ellenőrzött szöveg mégis készült. Az Ügynök-nyomkövetés fül egy „Failure recovery” lépésben és dobozban mutatja, mi történt.
- **1 ügynök vs. több ügynök** (Ügynök-nyomkövetés fül, jobb oszlop) – ugyanaz az első félidő egy ügynökkel és öt ügynökkel megírva, ugyanazzal az ellenőrzővel pontozva, a kézi átnézéssel és a korlátokkal.
- **igazolt · javítva** – a Verifier javította a szöveget (szám, név, állítás, óra vagy nyelv miatt).

## Bizonyíték- és nyomkövető panel

- **Bizonyíték:** a felirat forrás-eseményei (esemény-azonosítóval, perccel, típussal, játékossal), a felhasznált adatmezők, az alkalmazott **állítás-szabály** (pl. „uralja a meccset → field tilt ≥ 58 % vagy birtoklás ≥ 58 % vagy momentum ≥ 0,25”) és a Verifier ítélete, javításnál az **előtte/utána** szöveggel.
- **Nyomkövető:** melyik ügynök mit olvasott a közös állapotból és mit írt bele, hány másodpercet és tokent használt, hol bukott el az előszűrő (rossz szám, alaptalan állítás, rossz félidő-óra, hazai/vendég szöveg, nyelv), hol volt javítókör vagy elutasítás. A változatokra (szurkolói/elemzői, HU/EN, klubnézet) kattintva ugyanannak a pillanatnak a többi feliratát követheted.
