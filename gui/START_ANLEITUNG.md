# oXs Konfig-GUI – Start unter Windows (ohne vorhandenes Python)

Eine fertige `.exe` konnte ich in meiner Umgebung leider nicht bauen (dazu bräuchte es ein
Windows-Python, das dort aus Sicherheitsgründen nicht ladbar ist). Dieser Weg kommt aber mit
**einem einmaligen Klick** aus und ist danach genauso bequem:

## In 2 Schritten starten

1. **Python einmal installieren** (falls noch nicht vorhanden):
   - **Microsoft Store** öffnen → nach **„Python 3.12"** suchen → **Installieren**.
     (Keine Adminrechte nötig, kein PATH-Gefummel.)
   - Alternativ von https://www.python.org/downloads/ – dort beim Setup **„Add python.exe to PATH"** anhaken.

2. **`run.bat` doppelklicken.**
   Beim ersten Start wird automatisch die kleine Bibliothek `pyserial` geladen (wenige Sekunden),
   danach öffnet sich die GUI. Ab dem zweiten Mal startet sie sofort.

Das war's – kein PyQt, keine große Installation. `tkinter` (die Oberfläche) ist in Python schon enthalten.

## Bedienung

1. **Ports suchen** → COM-Port des oXs wählen → **Verbinden** (115200, 8N1).
2. **Config vom oXs lesen** sendet `DUMP` und füllt die Felder.
3. Felder anpassen (ein Bereich ist aktiv, wenn sein Häkchen gesetzt ist; ausgeschaltete Bereiche
   werden beim Schreiben gezielt mit `=255` deaktiviert).
4. **Config zum oXs schreiben** überträgt die Einstellungen (flüchtig).
5. **Auf oXs speichern (SAVE)** macht sie dauerhaft. Der oXs **startet danach neu** — dabei fällt der
   USB-Port kurz weg. Die App fängt das ab (kein Fehler-Popup), zeigt „Reconnect …" und **verbindet
   sich nach wenigen Sekunden automatisch wieder** (mit „Trennen" kannst du das abbrechen).
6. **Als .ini speichern / Aus .ini laden** legt Configs auf dem PC ab.

Enthaltene Bereiche: **Protokoll** (S.Port / F.Bus / CRSF + PRI/SEC/TLM-Pin + CRSF-Baud), **Baro/Vario**
(SDA/SCL), **Spannungen V1/V2** (Pin/Scale/Offset), **GPS** (Tx/Rx/Typ).

Die Pins **PRI / SEC / TLM** werden **abhängig vom Protokoll** ein-/ausgeblendet, mit Hinweis, wohin
sie gehören (ausgeblendete Pins werden beim Schreiben als `=255` deaktiviert):

| Protokoll | PRI-Pin | SEC-Pin | TLM-Pin |
|---|---|---|---|
| C (ELRS) | TX von Rx1 | *entfällt* | RX von Rx1 |
| S (Frsky S.Port) | *entfällt* | *entfällt* | S.Port von Rx1 oder Rx2 |
| F (Frsky F.Bus) | F.Bus von Rx1 | Sbus von Rx2 | *entfällt* |

Bei **S.Port** braucht es kein PRI/SEC — wer S-Bus-Signale möchte, nimmt **F.Bus** (das vereint beides).

## Später doch eine .exe?

Wenn Python installiert ist, kannst du dir jederzeit selbst eine `.exe` bauen:

```
python -m pip install pyserial pyinstaller
pyinstaller --onefile --windowed --name oXs_config oXs_config_gui_tk.py
```

Ergebnis: `dist\oXs_config.exe` (deutlich kleiner als die PyQt-Variante, da nur tkinter + pyserial).

## Schaltplan / Pin-Belegung anzeigen

Der Button **„Schaltplan anzeigen"** öffnet ein Fenster mit dem **RP2040‑Zero** und den
**Verbindungslinien** der aktuell gewählten Pins:

- Signal-Pins (Protokoll/GPS/Baro) sind mit farbigen Leitungen zu beschrifteten Bausteinen geführt
  (z. B. `GP1: TLM → RX von Rx1`).
- Für **V1/V2** ist jeweils ein **Spannungsteiler ≈ 1:5** eingezeichnet (E12: **R1 = 39 kΩ**,
  **R2 = 10 kΩ**; bei 15 V ~3,06 V am Pin). Der genaue Faktor wird über den Kalibrier-Assistenten
  gemessen – die Widerstände müssen also nicht exakt 1:5 sein.

Nach Änderungen im Hauptfenster einfach **„Aktualisieren"** klicken.

## Spannungen V1/V2 kalibrieren (Assistent)

Neben jeder Spannung gibt es den Button **„Kalibrieren…"**. Er nimmt dir die Rechnerei ab
(2‑Punkt‑Kalibrierung). oXs rechnet intern:

> `gemeldete_mV = Rohwert × scale − offset`  (Rohwert = Pin‑Spannung in mV bei scale=1/offset=0)

**Wichtig:** Max. 15 V → du brauchst einen **Spannungsteiler**, damit am ADC‑Pin höchstens **3,3 V**
anliegen. Der **Offset** fängt das ADC‑Rauschen/den Nullpunkt ab (Punkt 1 = 0 V).

Ablauf im Dialog:
1. **Vorbereiten** – setzt scale=1 / offset=0 und speichert (oXs rebootet, App verbindet automatisch neu).
2. **Punkt 1:** Eingang auf 0 V (an GND) → „messen (FV)" liest den Rohwert. **Punkt 2:** bekannte
   Spannung anlegen (Multimeter, möglichst nah an deinem Maximum) → „messen (FV)".
3. Optional **Aufschlag (mV, + = Anzeige höher)** — z. B. `300`, wenn die Anzeige bewusst 300 mV
   höher sein soll (`0` = exakt).
4. **Berechnen**, dann **Übernehmen & speichern**.

Formel: `scale = (V₂−V₁)/(M₂−M₁)`, `offset = scale·M₁ − V₁ − Aufschlag` (V/M in mV).

Hinweis: V2 ist bei oXs intern der „Current"-Kanal – die Kalibrierung funktioniert identisch, der
Wert erscheint in der Telemetrie nur als Strom-Feld.

## Gültige Pins (laut oXs-Firmware)

| Funktion | Befehl | gültige GPIOs |
|---|---|---|
| Primary channels | `PRI` | 5, 9, 21, 25 |
| Secondary channels | `SEC` | 1, 13, 17, 29 |
| Telemetrie | `TLM` | 0 … 29 |
| GPS Tx / Rx | `GPS_TX` / `GPS_RX` | 0 … 29 |
| I²C SDA | `SDA` | 2, 6, 10, 14, 18, 22, 26 |
| I²C SCL | `SCL` | 3, 7, 11, 15, 19, 23, 27 |
| Spannung V1 / V2 | `V1` / `V2` | 26, 27, 28, 29 |

255 = deaktiviert. Auf dem Waveshare **RP2040-Zero** sind nicht alle GPIOs herausgeführt – bitte am
Board-Pinout prüfen.
