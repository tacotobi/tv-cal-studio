# Hårdvara och sondering

Fynd från läs-sonderingen 2026-11-14 (`scripts/detect_tv.sh` plus manuell granskning av två
systemappar) och skrivprovet 2026-11-15. Det enda som skrivits till TV:n är `Backlight` (skrivprov och svep 0–100), återställt till 30. Varje punkt är märkt **verifierat** (uppmätt eller avläst)
eller **overifierat** (slutsats från namn i kod, inte provad).

## TV

| | |
|---|---|
| Modell | Xiaomi `MiTV-MOEU0`, kodnamn `ladybird` |
| Android | 14 (SDK 34), firmware `V816.0.25.12.1.ULBMIXM`, build-typ `user` |
| SoC | MediaTek MT9689 (`ro.hardware=mt5896`), `armeabi-v7a` – 32-bitars appar |
| Panel | 3840×2160 @ 60 Hz, gränssnittet ritas i 1920×1080 |
| ADB | TCP 5555, skalet kör som `uid=2000 (shell)`, ingen root |

Allt i tabellen är verifierat.

## HDR och färg i Android-kedjan

- **Verifierat:** skärmen anmäler HDR-typerna 1–4 (Dolby Vision, HDR10, HLG, HDR10+).
- **Verifierat:** `supportedColorModes [0]` – gränssnittslagret har bara ett färgläge. En vanlig
  vy kan alltså inte begära brett färgomfång eller HDR.
- **Verifierat:** `mMaxLuminance=100.0` i `HdrCapabilities` är ett platshållarvärde. TV:ns egna
  ljusuppgifter får inte användas som referens.
- **Overifierat:** att HDR10-mönster via videoavkodning (HEVC 10 bitar, PQ, BT.2020) når panelen
  utan omräkning. Ska mätas innan något HDR-resultat redovisas.

## Bildinställningar

### Androids inställningstabell (verifierat, läsning)
`settings list global` innehåller `picture_mode=4`, `picture_backlight=49`, `picture_gamma=0`.
Skalet har rätt att skriva i tabellen, men det är **overifierat** om TV:n reagerar på en skrivning.

### MediaTeks bilddatabas `settingspqdb`
- **Verifierat:** leverantören `com.mediatek.tv.settingspqdb` ägs av `com.mediatek.tv.agent`
  (`.settingspqdb.PqProvider`).
- **Verifierat:** ADB-skalet nekas (`requires ...settingspqdb.permission.READ_DATA or WRITE_DATA`).
- **Verifierat:** båda behörigheterna har skyddsnivå `normal`, alltså sådana som en vanlig
  installerad app får genom att deklarera dem i sitt manifest.
- **Verifierat (namn i koden):** tabellen `pq` har kolumnerna `Source`, `PictureMode`, `HdrType`
  – värden lagras per ingång × bildläge × HDR-typ. Sökvägar som förekommer: `/general`, `/source`,
  `/stream`, `/stream_by_source`, `/hdr`, `/reset`, `/reset_by_item`, `/calman_mode`,
  samt fabrikstabeller (`/general_factory`, `/gamma_table_factory`, `/rgbw_coordinate_factory`).
- **Verifierat (namn i koden):** 2-punkts vitbalans per färgtemperatur
  (`Color_Temperature_<läge>_<Red|Green|Blue>_<Gain|Offset>`) och färghantering för R, G, B, C, M,
  Y och hudton (`CFG_FUSION_PIC_COLOR_TUNER_{HUE,SAT,BRI}_*`, samt `GAIN_*`/`OFFSET_*` för RGB).
- **Verifierat (läst med `spikes/pqprobe`):** en egen app med `READ_DATA` får behörigheten vid
  installation och kan läsa databasen. `/source` gav `mm` (inbyggda appar), `/hdr` gav `SDR`.
- **Verifierat:** `/general` läses med nyckelnamnet som projektion och svarar bara på det första
  namnet – en fråga per nyckel. Värdena gäller aktuell ingång och aktuellt bildläge.
- **Verifierat (lästa värden, bildläge `Movie`):**
  - Grund: `Backlight=30`, `Brightness=50`, `Contrast=50`, `Saturation=50`, `Hue=0`,
    `Gamma=Gamma22`, `Color_Temperature=Warm`, `Color_space=Auto`.
  - 2-punkts vitbalans: `Color_Temperature_{Red,Green,Blue}_Gain=1024` (aktiva värden) och
    förinställningen `Color_Temperature_Warm_*_Gain` = 1036/1024/976. Offset-nycklarna är tomma.
  - Flerpunkts vitbalans: `PQ_WB_11_Point_<0–11>_{Red,Green,Blue}`, alla 50, med
    `PQ_WB_11_Point_enabled=Off`. Tolv index trots namnet "11 Point".
  - Färghantering: `COLORTUNER_{H,S,Y}_{R,G,B,C,M,Y,F}` och `COLORTUNER_{R,G,B}_{GAIN,OFFSET}`,
    alla 50, med `COLORTUNER_SWITCH=Off`.
  - Mini-LED och dynamik: `LD_MODE=High`, `Global_Dimming=On`, `Local_Contrast=Middle`,
    `DLC_STRENGTH=Off`, `Peak_Bright=Off`, `HDR_Mode=Auto`, `TMO_Range=Off`, `Calman_Mode=Off`.
  - Fullständig lista: kör provappen, resultatet hamnar i `data/probe/<datum>/pqdb_general.txt`.
- **Verifierat (namn i koden):** en skrivning är `update` mot `/general` med nyckelnamnet som
  kolumn och värdet som sträng. Leverantören behandlar bara första nyckeln i anropet, svarar `1`
  direkt och lagrar värdet på en egen tråd.
- **Verifierat (skrivprov 2026-11-15, se nedan):** en egen app med `WRITE_DATA` får skriva, och
  en skrivning av `Backlight` ändrar ljuset direkt och går att ta tillbaka.
- **Verifierat:** `settings`-tabellens `picture_backlight=49` ändras inte när databasens
  `Backlight` skrivs. Databasen är den som når panelen; vad `picture_backlight` gör är oklart.
- **Overifierat:** värdeintervall, och att övriga nycklar beter sig som `Backlight`.

#### Skrivprov bakgrundsljus 2026-11-15
Helvit bild från provappens `PatternActivity`, bildläge `Movie`, SDR, `LD_MODE=High`,
`Global_Dimming=On`. Mätt med i1Display Pro och `spotread -e -x -O`, två avläsningar per steg.

| Steg | `Backlight` läst tillbaka | Luminans (cd/m²) | x, y |
|---|---|---|---|
| Före | 30 | 344,3 / 344,3 | 0,2983 / 0,3037 |
| Skrev 29 | 29 | 347,6 / 347,6 | 0,2982 / 0,3036 |
| Skrev 30 | 30 | 344,2 / 344,1 | 0,2983 / 0,3037 |

Svart bild gav 0 cd/m². Tre avläsningar på vitt före provet drev högst 0,25 cd/m², så steget på
3,3 cd/m² (knappt 1 %) kommer från skrivningen.

Värdet 29 gav *högre* luminans än 30. Svepet nedan visar att det är ett ojämnt steg just där,
inte en omvänd skala.

#### Svep bakgrundsljus 2026-11-15
Samma läge som skrivprovet. Vit ruta på 10 % av ytan mot svart respektive helvit bild
(`PatternActivity --ei window 10`), medel av två avläsningar per steg. Läst värde stämde med
skrivet i varje steg utom det sista (se nedan). Rådata i `data/probe/2026-11-15/backlight_sweep_*.csv`.

| `Backlight` | Fönster 10 % (cd/m²) | Helvit (cd/m²) |
|---|---|---|
| 0 | 157,2 | 151,2 |
| 10 | 225,2 | 222,8 |
| 20 | 297,8 | 287,5 |
| 25 | 324,2 | 325,0 |
| 28 | 347,3 | 340,9 |
| 29 | 347,0 | 349,9 |
| 30 | 357,6 | 346,8 |
| 31 | 364,3 | 355,6 |
| 32 | 369,0 | 367,4 |
| 35 | 388,9 | 382,2 |
| 40 | 419,4 | 420,4 |
| 50 | 481,2 | 484,9 |
| 75 | 622,1 | 635,5 |
| 100 | 754,5 | 784,7 |

- **Verifierat:** intervallet 0–100 tas emot, och skalan går åt rätt håll och är ungefär rak:
  cirka 6 cd/m² per steg. Värdet 0 släcker inte panelen (drygt 150 cd/m² på vitt).
- **Verifierat:** stegen är ojämna kring 28–30. På helvit bild ligger 29 över 30 (349,9 mot 346,8,
  samma ordning som i skrivprovet), på fönstret ligger 28 och 29 lika. Enskilda steg kan alltså
  inte användas för finjustering utan att mäta.
- **Verifierat:** helvit bild begränsas inte – vid 100 är den ljusare än fönstret.
- **Verifierat:** vitpunkten flyttar sig med bakgrundsljuset, x från 0,298 vid 0 till 0,290 vid
  100 på fönstret (y nästan oförändrat). Vitbalansen måste ställas vid det bakgrundsljus som ska gälla.
- **Verifierat:** `picture_backlight` låg kvar på 49 genom hela svepet.
- Upprepade mätningar av 30 på fönstret gav 358,6, 357,6 och 354,5 – drift på omkring 1 % under
  svepet, störst efter stegen på 75 och 100.
- **Oklart:** sista steget i helskärmssvepet (100 → 30) gick inte igenom; läst värde var kvar på
  100 och luminansen 774 cd/m². adb-anslutningen bröts kort i steget före, och svepskriptet
  kontrollerade inte att anropet nådde fram. En ny skrivning av 30 direkt efteråt gick igenom
  (342 cd/m² uppmätt). Det styrande programmet måste läsa tillbaka varje skrivning.

Fabrikstabellerna (`*_factory`) rörs inte av projektet.

### Inbyggd Calman-app
- **Verifierat:** `com.mediatek.calman` 1.0.30 (build 20231213) ligger i `/system_ext/app/Calman`,
  har `MainActivity` och håller `settingspqdb`-behörigheterna.
- **Verifierat (namn i koden):** appen öppnar en TCP-server och har kommandon för att läsa och
  sätta bakgrundsljus, ljusstyrka, kontrast, färg, ton, skärpa, gamma, färgtemperatur, RGB hög och
  låg, HDR och tonmappning, samt `WRITE_PRE1D`, `WRITE_POST1D`, `WRITE_3D`, `PERSIST` och
  `HDR_ENABLE`. Den har egna testmönster (`SPECIALTY`).
- **Overifierat:** om Xiaomi har aktiverat appen, vilken port den lyssnar på och hur paketen ser
  ut. Protokollet är Portrait Displays slutna format.

## Slutsats för automatisering

| Funktion | Bedömning |
|---|---|
| Identifiera TV, läsa egenskaper, installera och starta app | Fullt automatiserbart (verifierat) |
| Visa SDR-mönster från egen app | Fullt automatiserbart (appen ej byggd än) |
| Läsa och ändra bildinställningar | Automatiserbart via egen app med `settingspqdb`-behörighet (verifierat för `Backlight`, övriga nycklar oprovade) |
| HDR10-mönster | Delvis – signalvägen måste verifieras med mätning |
| LUT-skrivning via Calman-protokollet | Reserv, kräver omvänd ingenjörskonst |

Nästa prov: skriv en annan nyckel än `Backlight` (t.ex. vitbalansens gain) och mät att den slår igenom.

## Mätdator

- Arch Linux (Omarchy), Python 3.14.8, `uv` via mise.
- ArgyllCMS 3.5.0 från `extra`, udev-regeln `55-Argyll.rules` finns. Efter nyinstallation måste
  mätaren dras ur och i för att få rätt behörighet.
- `android-tools` 37.0.0 från `extra` ger `adb`.
- JDK 21 via mise och Android SDK (plattform 34, build-tools 34.0.0) i
  `~/.local/share/android-sdk`. `scripts/install_arch.sh` sätter upp allt på en ny dator,
  `scripts/check_hardware.sh <tv-ip>` kontrollerar verktyg, mätare och TV.
- Provappen signeras med en nyckel per dator. Byggs den på en annan dator måste den gamla
  avinstalleras först: `adb uninstall se.tvcal.pqprobe`.
