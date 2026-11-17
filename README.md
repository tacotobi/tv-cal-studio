# tv-cal-studio

Eget kalibreringsprogram för en Xiaomi Google TV. Det mäter med en i1Display Pro, visar mönster från
en egen app på TV:n och skriver bildinställningarna direkt i TV:ns bilddatabas – utan TV:ns
servicemeny eller Calman.

![Gråskala och färger före och efter kalibreringen 2026-11-16](docs/img/kalibrering-2026-11-16.png)

## TV:n

| | |
|---|---|
| Modell | Xiaomi `MiTV-MOEU0` (kodnamn `ladybird`), Google TV / Android 14 |
| Panel | QD-Mini LED, 3840×2160 @ 60 Hz |
| SoC | MediaTek MT9689 – inställningarna ligger i MediaTeks databas `settingspqdb` |
| Bildläge | `Movie`, SDR, inbyggda appar |

HDR och HDMI-källor (Xbox, Switch) är inte kalibrerade än.

## Mål

BT.709, vitpunkt D65, gamma 2,2 och vitt på 200 cd/m², med lokaldämpningen avstängd.

## Det här behövs

- X-Rite i1Display Pro och [ArgyllCMS](https://www.argyllcms.com/) (`spotread`)
- `adb` och en TV med nätverksfelsökning (ADB över TCP) påslagen, på samma nät som datorn
- Provappen `spikes/pqprobe` installerad på TV:n (`spikes/pqprobe/build.sh`)
- Python 3.14, inga andra paket

`scripts/install_arch.sh` installerar verktygen på Arch Linux och `scripts/check_hardware.sh <tv-ip>`
kontrollerar att allt hittas. Körningen sker helt lokalt, utan internet.

## Snabbstart

```bash
python3 -m tvcal.cli check                   # verktyg, mätare, TV och nuvarande inställningar
python3 -m tvcal.cli measure --colors        # mät gråskala och färger, skriver inget
python3 -m tvcal.cli calibrate all --keep    # hela kedjan, behåll resultatet
python3 -m tvcal.cli restore data/runs/<körning>/snapshot.json   # tillbaka till före
python3 -m unittest discover -s tests -t .   # tester mot en simulerad TV, ingen hårdvara
```

`--tv <ip>` väljer TV. Utan `--keep` återställs TV:n efter körningen. Rapporter och ögonblicksbilder
hamnar i `data/runs/`.

## Mer att läsa

- [`docs/TVCAL.md`](docs/TVCAL.md) – programmet, kalibreringsstegen och säkerheten
- [`docs/HARDWARE.md`](docs/HARDWARE.md) – sonderingen av TV:n och vad varje inställning gör, med mätvärden
