# tvcal – programmet

Kalibrerar gråskalan på Xiaomi `MiTV-MOEU0` (bildläge `Movie`, inbyggda appar, SDR) med
i1Display Pro. Vägen till bildinställningarna och varför den valdes: beslut 0001 i Cortex.
Mätfakta som stegen bygger på: `docs/HARDWARE.md`.

## Kommandon
```bash
python3 -m unittest discover -s tests -t .        # alla tester, ingen hårdvara behövs
python3 -m tvcal.cli check                        # verktyg, TV och nuvarande bildinställningar
python3 -m tvcal.cli measure                      # gråskala 5–100 % mot målet; skriver inget
python3 -m tvcal.cli calibrate all                # hela kedjan, mät före och efter, återställ sedan
python3 -m tvcal.cli calibrate all --keep         # som ovan men behåll resultatet
python3 -m tvcal.cli calibrate backlight --target-y 200   # ett steg
python3 -m tvcal.cli restore data/runs/<körning>/snapshot.json
```
`--tv <ip>` väljer TV (standard 192.168.1.50), `--ccss <fil>` ger mätaren spektralkorrigering; standard är `ccss/qd-miniled-tcl-50c7k.ccss`, `--ccss none` mäter utan.
`measure --colors` mäter också färgerna 100 % och 75 % mot BT.709.

Mål: D65, ren potens gamma 2,2 relativt uppmätt vitt, vitt 200 cd/m² (`--target-y`). Allt mäts
på en ruta på 10 % av ytan som video, eftersom bildbehandlingen bara verkar på videoplanet.

## Säkerhet
- `calibrate` sparar en ögonblicksbild av alla nycklar den kan skriva (`snapshot.json` i
  körmappen) innan något skrivs, och återställer från den efteråt – också vid fel och Ctrl+C –
  om inte `--keep` anges. Återställningen laddar alltid om färgtemperaturläget, så att HAL:en
  får förinställningens gain.
- Provappen på TV:n tar bara emot nycklarna och intervallen i sin `WRITABLE`-lista.
- Varje skrivning läses tillbaka; tre försök innan felet rapporteras.

## Stegen (`tvcal/calibrate.py`)
| Steg | Gör | Mätningar (simulerat) |
|---|---|---|
| `dimming` | `LD_MODE=Off` och `Local_Contrast=Off`: lokaldämpningen släcker 5 % och trycker ner 10–20 %, den lokala kontrasten flyttar mellantonerna 2–3 %, båda beroende på bilden | 0 |
| `backlight` | Sekantsökning på `Backlight` mot målets Y på vitt, sedan grannarna; närmaste uppmätta väljs eftersom stegen är ojämna | 4–7 |
| `whitepoint` | Vitt till D65 via `Color_Temperature_Warm_<färg>_Gain` och omladdning av läget. En kanal hålls på taket (1024, rött 1036), de två andra räknas fram med Newton-iteration | cirka 5 |
| `gamma` | Väljer det förval (`Gamma18`–`Gamma26`) som ligger närmast målet på 70–90 %, där ingen punkt kan rätta | 15 |
| `multipoint` | `PQ_WB_11_Point_enabled=On`; varje punkt (nivå 5 % × (i+1)) ställs mot målets XYZ med linjär lösning från provsteg | cirka 60 |
| `colors` | `COLORTUNER_SWITCH=On`; nyans, mättnad och ljus (`COLORTUNER_H/S/Y_<färg>`) per färg R, G, B, C, M, Y mot BT.709. Felet är medel-ΔE00 på 100 % och 75 % (ställt bara på 100 % blev 75 % sämre). Mönstersökning (±4, sedan ±2, ±1), eftersom reglagen har en knyck vid 50 där en linjär lösning spårar ur | högst 20 prov × 2 per färg |
| `measure` | Gråskalan och färgerna efter | 32 |

`all` kör `dimming`, `backlight`, `whitepoint`, `backlight` igen (sänkt gain ger mindre ljus), `gamma`,
`multipoint`, `colors` och `measure`, med mätning av gråskala och färger före.

Vitt ställs som standard halvvägs mot 80 %-tonen (`compromise_white`), eftersom 65–95 % ligger
högre i y än vitt och ingen punkt når dit. `--no-white-compromise` ställer vitt exakt på D65.

Ovanför 60 % finns ingen egen punkt, så 65–95 % följer gain och gamma.

## Delar
| Fil | Innehåll |
|---|---|
| `tvcal/color.py` | xyY/XYZ/Lab, ΔE2000 (testad mot Sharma m.fl. 2005), målvärden |
| `tvcal/meter.py` | `spotread` med två avläsningar, tredje vid drift |
| `tvcal/tv.py` | adb och provappen via `am start` (2–3 s per anrop) |
| `tvcal/patterns.py` | grå mönstervideor via `scripts/make_pattern.sh`, sparade i `data/patterns/` |
| `tvcal/snapshot.py` | ögonblicksbild och återställning |
| `tvcal/sim.py` | simulerad TV byggd på mätningarna, för tester |
| `tvcal/measure.py` | gråskalemätning och rapport |
| `tvcal/cli.py` | kommandoraden |

Körningar sparas i `data/runs/<datum>_<tid>/` (inte i git).

## Kända begränsningar
- CCSS:en kommer från en annan QD-Mini LED-panel. Vitpunkten i absoluta tal är därför osäker med cirka ±0,0015 i y; relativa ändringar stämmer.
- Simuleringen är en förenkling (gain som potens 2,6, punktskala 0,016 per steg, färghanteringen
  anpassad till svepen av rött). Den fångar fel i looparna men ersätter inte prov på TV:n.
- Färghanteringen når inte BT.709 för alla färger: panelens rött ligger åt orange, och nyansen
  kan bara vrida det åt ena hållet.
- `am start` per anrop gör en hel körning lång. Byggplanen har ett socketprotokoll i en egen app
  som nästa steg när det behövs.
