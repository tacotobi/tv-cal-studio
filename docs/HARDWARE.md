# Hårdvara och sondering

Fynd från läs-sonderingen 2026-11-14 (`scripts/detect_tv.sh` plus manuell granskning av två
systemappar). Inget skrevs till TV:n. Varje punkt är märkt **verifierat** (uppmätt eller avläst)
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
- **Overifierat:** exakta nyckelnamn och värdeintervall i databasen, och att en skrivning slår
  igenom i bilden direkt.

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
| Läsa och ändra bildinställningar | Troligen automatiserbart via egen app med `settingspqdb`-behörighet (overifierat) |
| HDR10-mönster | Delvis – signalvägen måste verifieras med mätning |
| LUT-skrivning via Calman-protokollet | Reserv, kräver omvänd ingenjörskonst |

Nästa prov: en minimal app som läser `settingspqdb` och gör en enda omvändbar skrivning
(bakgrundsljus 49 → 48 → 49) medan mätaren kontrollerar att ljuset ändras.

## Mätdator

- Arch Linux (Omarchy), Python 3.14.8, `uv` via mise.
- ArgyllCMS 3.5.0 från `extra`, udev-regeln `55-Argyll.rules` finns. Efter nyinstallation måste
  mätaren dras ur och i för att få rätt behörighet.
- `android-tools` 37.0.0 från `extra` ger `adb`.
- Saknas ännu: JDK och Android SDK (build-tools, plattform 34) för att bygga appen.
