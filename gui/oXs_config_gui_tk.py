#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Schlanke Konfigurations-GUI fuer oXs on RP2040  (tkinter-Version).

Braucht nur 'pyserial' als Zusatz (tkinter ist in Python enthalten):
    pip install pyserial
    python oXs_config_gui_tk.py

Funktionen:
  1. Protokoll: Frsky S.Port / Frsky F.Bus / CRSF (ELRS)  (+ Telemetrie-Pin, CRSF-Baudrate)
  2. Baro-/Vario-Sensor:  I2C SDA + SCL
  3. Zwei Spannungen:     V1 und V2 (Pin, Scale, Offset)
  4. GPS:                 GPS_TX, GPS_RX, GPS-Typ
USB: Verbinden/Trennen, Config lesen (DUMP), schreiben, SAVE, freies Terminal, .ini laden/speichern.
"""

VERSION = "1.0.0"

import re
import configparser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None


# --------------------------------------------------------------------------
# Zuordnungstabellen (Klartext <-> oXs-Code) und gueltige GPIOs
# --------------------------------------------------------------------------
PROTOCOL_NAMES = ["Frsky S.Port", "Frsky F.Bus", "CRSF (ELRS)"]
PROTOCOL_CODES = ["S", "F", "C"]
GPS_NAMES = ["Ublox (von oXs konfiguriert)", "Ublox (extern konfiguriert)", "CADIS"]
GPS_CODES = ["U", "E", "C"]
CRSF_BAUDS = ["115200", "400000", "420000", "921600", "1870000", "3750000", "5250000"]

OFF = 255
OFF_LABEL = "aus (255)"
PINS_PRI  = [5, 9, 21, 25]           # Primary channels input
PINS_SEC  = [1, 13, 17, 29]          # Secondary channels input
PINS_TLM  = list(range(0, 30))
PINS_GPS  = list(range(0, 30))
PINS_SDA  = [2, 6, 10, 14, 18, 22, 26]
PINS_SCL  = [3, 7, 11, 15, 19, 23, 27]
PINS_VOLT = [26, 27, 28, 29]

# Was PRI / SEC / TLM je Protokoll bedeuten (Hinweistext); None -> Pin wird nicht benutzt (ausgeblendet)
#  S.Port : nur TLM (fuer Sbus-Signale nimmt man F.Bus, das beides vereint)
#  CRSF   : PRI + TLM (kein SEC)
#  F.Bus  : PRI + SEC (kein TLM)
PIN_HINTS = {
    "C": {"PRI": "TX von Rx1",        "SEC": None,                "TLM": "RX von Rx1"},
    "S": {"PRI": None,                "SEC": None,                "TLM": "S.Port von Rx1 oder Rx2"},
    "F": {"PRI": "F.Bus von Rx1",     "SEC": "Sbus von Rx2",      "TLM": None},
}


def pin_values(pins, with_off=True):
    vals = [OFF_LABEL] if with_off else []
    return vals + [str(p) for p in pins]


def label_to_pin(text):
    if text == OFF_LABEL:
        return OFF
    try:
        return int(text)
    except ValueError:
        return OFF


def pin_to_label(value, with_off=True):
    if value == OFF:
        return OFF_LABEL if with_off else str(value)
    return str(value)


class OxsGui:
    def __init__(self, root):
        self.root = root
        self.ser = None
        root.title(f"oXs on RP2040 – Konfig-GUI (tkinter)  v{VERSION}")
        self._want = False        # True solange der Nutzer verbunden bleiben moechte
        self._reconnecting = False
        self._last_port = None
        self._reconnect_left = 0
        self._build()
        self.refresh_ports()
        self._set_state("disconnected")
        self._poll()  # startet die Empfangsschleife

    # ---------------------------------------------------------------- Aufbau
    def _build(self):
        pad = dict(padx=4, pady=3)
        main = ttk.Frame(self.root, padding=6)
        main.pack(fill="both", expand=True)

        # --- USB-Leiste ---
        usb = ttk.LabelFrame(main, text="USB-Verbindung", padding=6)
        usb.pack(fill="x")
        ttk.Label(usb, text="Port:").grid(row=0, column=0, **pad)
        self.cbPort = ttk.Combobox(usb, width=40, state="readonly")
        self.cbPort.grid(row=0, column=1, **pad)
        ttk.Button(usb, text="Ports suchen", command=self.refresh_ports).grid(row=0, column=2, **pad)
        self.btnConnect = ttk.Button(usb, text="Verbinden", command=self.connect)
        self.btnConnect.grid(row=0, column=3, **pad)
        self.btnDisconnect = ttk.Button(usb, text="Trennen", command=self.disconnect)
        self.btnDisconnect.grid(row=0, column=4, **pad)
        self.lblStatus = ttk.Label(usb, text="Getrennt", foreground="#b00000")
        self.lblStatus.grid(row=0, column=5, **pad)

        # --- 1) Protokoll ---
        proto = ttk.LabelFrame(main, text="1) Protokoll", padding=6)
        proto.pack(fill="x", pady=(6, 0))
        ttk.Label(proto, text="Protokoll:").grid(row=0, column=0, sticky="e", **pad)
        self.cbProtocol = ttk.Combobox(proto, values=PROTOCOL_NAMES, state="readonly", width=18)
        self.cbProtocol.current(0)
        self.cbProtocol.grid(row=0, column=1, sticky="w", **pad)
        self.cbProtocol.bind("<<ComboboxSelected>>", lambda e: self._on_protocol())
        self.lblCrsf = ttk.Label(proto, text="CRSF-Baudrate:")
        self.lblCrsf.grid(row=0, column=2, sticky="e", **pad)
        self.cbCrsfBaud = ttk.Combobox(proto, values=CRSF_BAUDS, state="readonly", width=10)
        self.cbCrsfBaud.set("420000")
        self.cbCrsfBaud.grid(row=0, column=3, sticky="w", **pad)

        # PRI / SEC / TLM Pins mit protokollabhaengigem Hinweistext
        self.lblPri = ttk.Label(proto, text="PRI-Pin:")
        self.lblPri.grid(row=1, column=0, sticky="e", **pad)
        self.cbPri = ttk.Combobox(proto, values=pin_values(PINS_PRI), state="readonly", width=10)
        self.cbPri.current(0)
        self.cbPri.grid(row=1, column=1, sticky="w", **pad)
        self.lblPriHint = ttk.Label(proto, text="", foreground="gray")
        self.lblPriHint.grid(row=1, column=2, columnspan=2, sticky="w", **pad)

        self.lblSec = ttk.Label(proto, text="SEC-Pin:")
        self.lblSec.grid(row=2, column=0, sticky="e", **pad)
        self.cbSec = ttk.Combobox(proto, values=pin_values(PINS_SEC), state="readonly", width=10)
        self.cbSec.current(0)
        self.cbSec.grid(row=2, column=1, sticky="w", **pad)
        self.lblSecHint = ttk.Label(proto, text="", foreground="gray")
        self.lblSecHint.grid(row=2, column=2, columnspan=2, sticky="w", **pad)

        self.lblTlm = ttk.Label(proto, text="TLM-Pin:")
        self.lblTlm.grid(row=3, column=0, sticky="e", **pad)
        self.cbTlm = ttk.Combobox(proto, values=pin_values(PINS_TLM), state="readonly", width=10)
        self.cbTlm.current(0)
        self.cbTlm.grid(row=3, column=1, sticky="w", **pad)
        self.lblTlmHint = ttk.Label(proto, text="", foreground="gray")
        self.lblTlmHint.grid(row=3, column=2, columnspan=2, sticky="w", **pad)

        # --- mittlere Reihe: V1 / V2 ---
        midrow = ttk.Frame(main)
        midrow.pack(fill="x", pady=(6, 0))
        self._build_volt(midrow, 1).pack(side="left", fill="both", expand=True, padx=(0, 3))
        self._build_volt(midrow, 2).pack(side="left", fill="both", expand=True, padx=(3, 0))

        # --- untere Reihe: Baro / GPS ---
        botrow = ttk.Frame(main)
        botrow.pack(fill="x", pady=(6, 0))
        self._build_baro(botrow).pack(side="left", fill="both", expand=True, padx=(0, 3))
        self._build_gps(botrow).pack(side="left", fill="both", expand=True, padx=(3, 0))

        # --- Aktionen ---
        act = ttk.LabelFrame(main, text="Aktionen", padding=6)
        act.pack(fill="x", pady=(6, 0))
        self.btnRead = ttk.Button(act, text="Config vom oXs lesen", command=self.read_from_oxs)
        self.btnWrite = ttk.Button(act, text="Config zum oXs schreiben", command=self.write_to_oxs)
        self.btnSaveOxs = ttk.Button(act, text="Auf oXs speichern (SAVE)", command=self.save_on_oxs)
        self.btnRead.pack(side="left", **pad)
        self.btnWrite.pack(side="left", **pad)
        self.btnSaveOxs.pack(side="left", **pad)
        ttk.Button(act, text="Schaltplan anzeigen", command=self.open_wiring).pack(side="left", padx=(20, 4))
        ttk.Button(act, text="Aus .ini laden", command=self.load_ini).pack(side="right", **pad)
        ttk.Button(act, text="Als .ini speichern", command=self.save_ini).pack(side="right", **pad)

        # --- Terminal ---
        term = ttk.LabelFrame(main, text="Terminal (oXs-Ausgabe)", padding=6)
        term.pack(fill="both", expand=True, pady=(6, 0))
        self.txt = tk.Text(term, height=14, wrap="none")
        self.txt.pack(fill="both", expand=True, side="top")
        sb = ttk.Scrollbar(self.txt, command=self.txt.yview)
        sb.pack(side="right", fill="y")
        self.txt.config(yscrollcommand=sb.set)
        sendrow = ttk.Frame(term)
        sendrow.pack(fill="x", pady=(4, 0))
        self.edCmd = ttk.Entry(sendrow)
        self.edCmd.pack(side="left", fill="x", expand=True)
        self.edCmd.bind("<Return>", lambda e: self.send_raw())
        self.btnSend = ttk.Button(sendrow, text="Senden", command=self.send_raw)
        self.btnSend.pack(side="left", padx=4)
        ttk.Button(sendrow, text="Leeren", command=lambda: self.txt.delete("1.0", "end")).pack(side="left")

        self._on_protocol()

    def _build_volt(self, parent, n):
        var = tk.BooleanVar(value=False)
        box = ttk.LabelFrame(parent, text="", padding=6)
        chk = ttk.Checkbutton(box, text=f"3) Spannung V{n}", variable=var,
                              command=lambda: self._toggle(f"volt{n}"))
        chk.grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(box, text="Pin:").grid(row=1, column=0, sticky="e", padx=4, pady=2)
        cbPin = ttk.Combobox(box, values=pin_values(PINS_VOLT, with_off=False), state="readonly", width=8)
        cbPin.current(0)
        cbPin.grid(row=1, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(box, text="Scale:").grid(row=2, column=0, sticky="e", padx=4, pady=2)
        eScale = ttk.Entry(box, width=10)
        eScale.insert(0, "1.0")
        eScale.grid(row=2, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(box, text="Offset:").grid(row=3, column=0, sticky="e", padx=4, pady=2)
        eOffset = ttk.Entry(box, width=10)
        eOffset.insert(0, "0.0")
        eOffset.grid(row=3, column=1, sticky="w", padx=4, pady=2)
        btnCal = ttk.Button(box, text="Kalibrieren…", command=lambda: self.open_calibration(n))
        btnCal.grid(row=4, column=0, columnspan=2, sticky="w", padx=4, pady=(4, 0))
        setattr(self, f"volt{n}Var", var)
        setattr(self, f"volt{n}Pin", cbPin)
        setattr(self, f"volt{n}Scale", eScale)
        setattr(self, f"volt{n}Offset", eOffset)
        setattr(self, f"volt{n}Widgets", [cbPin, eScale, eOffset, btnCal])
        self._toggle(f"volt{n}")
        return box

    def _build_baro(self, parent):
        var = tk.BooleanVar(value=False)
        box = ttk.LabelFrame(parent, text="", padding=6)
        ttk.Checkbutton(box, text="2) Baro / Vario (I2C-Sensor)", variable=var,
                        command=lambda: self._toggle("baro")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(box, text="SDA:").grid(row=1, column=0, sticky="e", padx=4, pady=2)
        self.cbSda = ttk.Combobox(box, values=pin_values(PINS_SDA, with_off=False), state="readonly", width=8)
        self.cbSda.current(0)
        self.cbSda.grid(row=1, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(box, text="SCL:").grid(row=2, column=0, sticky="e", padx=4, pady=2)
        self.cbScl = ttk.Combobox(box, values=pin_values(PINS_SCL, with_off=False), state="readonly", width=8)
        self.cbScl.current(0)
        self.cbScl.grid(row=2, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(box, text="MS5611 / SPL06 / BMP280 automatisch.",
                  foreground="gray").grid(row=3, column=0, columnspan=2, sticky="w", padx=4)
        self.baroVar = var
        self.baroWidgets = [self.cbSda, self.cbScl]
        self._toggle("baro")
        return box

    def _build_gps(self, parent):
        var = tk.BooleanVar(value=False)
        box = ttk.LabelFrame(parent, text="", padding=6)
        ttk.Checkbutton(box, text="4) GPS", variable=var,
                        command=lambda: self._toggle("gps")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(box, text="GPS_TX:").grid(row=1, column=0, sticky="e", padx=4, pady=2)
        self.cbGpsTx = ttk.Combobox(box, values=pin_values(PINS_GPS, with_off=False), state="readonly", width=8)
        self.cbGpsTx.current(0)
        self.cbGpsTx.grid(row=1, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(box, text="GPS_RX:").grid(row=2, column=0, sticky="e", padx=4, pady=2)
        self.cbGpsRx = ttk.Combobox(box, values=pin_values(PINS_GPS, with_off=False), state="readonly", width=8)
        self.cbGpsRx.current(0)
        self.cbGpsRx.grid(row=2, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(box, text="Typ:").grid(row=3, column=0, sticky="e", padx=4, pady=2)
        self.cbGpsType = ttk.Combobox(box, values=GPS_NAMES, state="readonly", width=26)
        self.cbGpsType.current(0)
        self.cbGpsType.grid(row=3, column=1, sticky="w", padx=4, pady=2)
        self.gpsVar = var
        self.gpsWidgets = [self.cbGpsTx, self.cbGpsRx, self.cbGpsType]
        self._toggle("gps")
        return box

    def _toggle(self, name):
        var = getattr(self, f"{name}Var")
        widgets = getattr(self, f"{name}Widgets")
        state = "readonly" if var.get() else "disabled"
        # Entry-Felder kennen kein 'readonly' fuer disabled -> normal/disabled
        for w in widgets:
            if isinstance(w, ttk.Combobox):
                w.config(state=state if var.get() else "disabled")
            else:
                w.config(state="normal" if var.get() else "disabled")

    def _on_protocol(self):
        code = PROTOCOL_CODES[self.cbProtocol.current()]
        is_crsf = code == "C"
        self.cbCrsfBaud.config(state="readonly" if is_crsf else "disabled")
        self.lblCrsf.config(foreground="black" if is_crsf else "gray")

        hints = PIN_HINTS[code]
        # PRI / SEC / TLM je nach Protokoll ein- oder ausblenden
        for prefix, key in (("Pri", "PRI"), ("Sec", "SEC"), ("Tlm", "TLM")):
            lbl = getattr(self, "lbl" + prefix)
            cb = getattr(self, "cb" + prefix)
            hint = getattr(self, "lbl" + prefix + "Hint")
            if hints[key]:
                lbl.grid(); cb.grid(); hint.grid()
                hint.config(text="→ " + hints[key])
            else:
                lbl.grid_remove(); cb.grid_remove(); hint.grid_remove()

    def _protocol_uses(self, key):
        return PIN_HINTS[PROTOCOL_CODES[self.cbProtocol.current()]][key] is not None

    # ------------------------------------------------------------- Serial
    def refresh_ports(self):
        ports = []
        if serial is not None:
            for info in serial.tools.list_ports.comports():
                label = info.device
                if info.description and info.description != "n/a":
                    label += f"  ({info.description})"
                ports.append((label, info.device))
        self._port_map = {lbl: dev for lbl, dev in ports}
        self.cbPort["values"] = [lbl for lbl, _ in ports]
        if ports:
            self.cbPort.current(0)

    def _open_port(self, dev):
        s = serial.Serial(port=dev, baudrate=115200, timeout=0,
                          bytesize=8, parity='N', stopbits=1)
        s.dtr = True
        s.rts = True
        return s

    def connect(self):
        if serial is None:
            self._error("pyserial ist nicht installiert.\nBitte:  pip install pyserial")
            return
        sel = self.cbPort.get()
        dev = getattr(self, "_port_map", {}).get(sel)
        if not dev:
            self._error("Kein COM-Port ausgewaehlt. Zuerst 'Ports suchen'.")
            return
        try:
            self.ser = self._open_port(dev)
        except Exception as e:
            self.ser = None
            self._error(f"Kann Port nicht oeffnen:\n{e}")
            return
        self._last_port = dev
        self._want = True
        self._reconnecting = False
        self._set_state("connected")

    def disconnect(self):
        # manuelles Trennen -> auch den Auto-Reconnect stoppen
        self._want = False
        self._reconnecting = False
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        self._set_state("disconnected")

    def _poll(self):
        if self.ser is not None:
            try:
                n = self.ser.in_waiting
                if n:
                    data = self.ser.read(n)
                    self.txt.insert("end", data.decode("utf-8", errors="replace"))
                    self.txt.see("end")
            except Exception:
                # unerwarteter Abbruch (z. B. Reboot nach SAVE) -> ohne Popup neu verbinden
                try:
                    self.ser.close()
                except Exception:
                    pass
                self.ser = None
                if self._want:
                    self._begin_reconnect()
                else:
                    self._set_state("disconnected")
        self.root.after(50, self._poll)

    # ----------------------------------------------------- Auto-Reconnect
    def _begin_reconnect(self):
        if self._reconnecting:
            return
        self._reconnecting = True
        self._reconnect_left = 20        # ~ Versuche (1/s)
        self._set_state("reconnecting")
        self.txt.insert("end", "\n[Verbindung verloren – versuche automatisch neu zu verbinden …]\n")
        self.txt.see("end")
        self.root.after(3000, self._try_reconnect)   # erst nach Reboot/USB-Enumeration

    def _try_reconnect(self):
        if not self._want or not self._reconnecting:
            return
        dev = self._pick_reconnect_port()
        if dev:
            try:
                self.ser = self._open_port(dev)
                self._last_port = dev
                self._reconnecting = False
                self._set_state("connected")
                self.txt.insert("end", f"[wieder verbunden auf {dev}]\n")
                self.txt.see("end")
                return
            except Exception:
                self.ser = None
        self._reconnect_left -= 1
        if self._reconnect_left > 0 and self._want:
            self.root.after(1000, self._try_reconnect)
        else:
            self._reconnecting = False
            self._set_state("disconnected")
            self.txt.insert("end", "[Reconnect fehlgeschlagen – bitte manuell verbinden]\n")
            self.txt.see("end")

    def _pick_reconnect_port(self):
        devs = []
        if serial is not None:
            devs = [info.device for info in serial.tools.list_ports.comports()]
        if self._last_port in devs:
            return self._last_port
        if len(devs) == 1:
            return devs[0]          # nur ein Port da -> vermutlich der oXs (evtl. neue Nummer)
        return self._last_port      # sonst den alten trotzdem versuchen

    def _write(self, text):
        if self.ser is None:
            self._error("Keine USB-Verbindung. Zuerst 'Verbinden'.")
            return False
        try:
            self.ser.write((text + "\r\n").encode("utf-8"))
            return True
        except Exception as e:
            self._error(f"Fehler beim Senden:\n{e}")
            self.disconnect()
            return False

    def send_raw(self):
        cmd = self.edCmd.get().strip()
        if cmd and self._write(cmd):
            self.edCmd.delete(0, "end")

    def _set_state(self, state):
        # state: "connected" | "disconnected" | "reconnecting"
        txt = {"connected": "Verbunden", "disconnected": "Getrennt",
               "reconnecting": "Reconnect …"}[state]
        col = {"connected": "#008000", "disconnected": "#b00000",
               "reconnecting": "#c07000"}[state]
        self.lblStatus.config(text=txt, foreground=col)
        connected = state == "connected"
        for b in (self.btnRead, self.btnWrite, self.btnSaveOxs, self.btnSend):
            b.config(state="normal" if connected else "disabled")
        # Verbinden nur wenn wirklich getrennt; Trennen auch waehrend Reconnect (zum Abbrechen)
        self.btnConnect.config(state="normal" if state == "disconnected" else "disabled")
        self.btnDisconnect.config(state="normal" if state in ("connected", "reconnecting") else "disabled")

    # ----------------------------------------------------- Befehl bauen
    def build_command(self):
        parts = ["PROTOCOL=" + PROTOCOL_CODES[self.cbProtocol.current()]]
        if self.cbProtocol.current() == PROTOCOL_CODES.index("C"):
            parts.append("CRSFBAUD=" + self.cbCrsfBaud.get())
        # PRI / SEC / TLM: nur senden was das Protokoll nutzt, sonst =255 (deaktiviert)
        for key, cb in (("PRI", self.cbPri), ("SEC", self.cbSec), ("TLM", self.cbTlm)):
            if self._protocol_uses(key):
                parts.append(f"{key}=" + str(label_to_pin(cb.get())))
            else:
                parts.append(f"{key}=255")

        if self.baroVar.get():
            parts.append("SDA=" + str(label_to_pin(self.cbSda.get())))
            parts.append("SCL=" + str(label_to_pin(self.cbScl.get())))
        else:
            parts += ["SDA=255", "SCL=255"]

        for n in (1, 2):
            if getattr(self, f"volt{n}Var").get():
                parts.append(f"V{n}=" + str(label_to_pin(getattr(self, f"volt{n}Pin").get())))
                parts.append(f"SCALE{n}=" + self._fmt(getattr(self, f"volt{n}Scale").get(), 1.0))
                parts.append(f"OFFSET{n}=" + self._fmt(getattr(self, f"volt{n}Offset").get(), 0.0))
            else:
                parts.append(f"V{n}=255")

        if self.gpsVar.get():
            parts.append("GPS_TX=" + str(label_to_pin(self.cbGpsTx.get())))
            parts.append("GPS_RX=" + str(label_to_pin(self.cbGpsRx.get())))
            parts.append("GPS=" + GPS_CODES[self.cbGpsType.current()])
        else:
            parts += ["GPS_TX=255", "GPS_RX=255"]
        return "; ".join(parts)

    def write_to_oxs(self):
        cmd = self.build_command()
        self.txt.insert("end", "\n>>> " + cmd + "\n")
        self.txt.see("end")
        self._write(cmd)

    def save_on_oxs(self):
        if self._write("SAVE"):
            self.txt.insert("end", "\n>>> SAVE  (oXs startet danach neu – die App verbindet sich automatisch wieder)\n")
            self.txt.see("end")

    def read_from_oxs(self):
        self.txt.delete("1.0", "end")
        if self._write("DUMP"):
            self.root.after(1200, self._parse_now)

    def _parse_now(self):
        self.apply_config_dict(self._parse_dump(self.txt.get("1.0", "end")))

    # ----------------------------------------------------- Parsing / apply
    @staticmethod
    def _parse_dump(text):
        d = {}
        for key, val in re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^;\n\r]+)', text):
            d[key.strip().upper()] = val.strip()
        return d

    def apply_config_dict(self, d):
        if d.get("PROTOCOL") in PROTOCOL_CODES:
            self.cbProtocol.current(PROTOCOL_CODES.index(d["PROTOCOL"]))
        if "CRSFBAUD" in d:
            self.cbCrsfBaud.set(str(self._to_int(d["CRSFBAUD"], 420000)))
        if "PRI" in d:
            self._set_combo_pin(self.cbPri, self._to_int(d["PRI"], OFF), True)
        if "SEC" in d:
            self._set_combo_pin(self.cbSec, self._to_int(d["SEC"], OFF), True)
        if "TLM" in d:
            self._set_combo_pin(self.cbTlm, self._to_int(d["TLM"], OFF), True)
        self._on_protocol()

        has_baro = "SDA" in d or "SCL" in d
        self.baroVar.set(has_baro)
        self._toggle("baro")
        if "SDA" in d:
            self._set_combo_pin(self.cbSda, self._to_int(d["SDA"], PINS_SDA[0]), False)
        if "SCL" in d:
            self._set_combo_pin(self.cbScl, self._to_int(d["SCL"], PINS_SCL[0]), False)

        for n in (1, 2):
            present = f"V{n}" in d
            getattr(self, f"volt{n}Var").set(present)
            self._toggle(f"volt{n}")
            if present:
                self._set_combo_pin(getattr(self, f"volt{n}Pin"),
                                    self._to_int(d[f"V{n}"], PINS_VOLT[0]), False)
            if f"SCALE{n}" in d:
                self._set_entry(getattr(self, f"volt{n}Scale"), self._fmt(d[f"SCALE{n}"], 1.0))
            if f"OFFSET{n}" in d:
                self._set_entry(getattr(self, f"volt{n}Offset"), self._fmt(d[f"OFFSET{n}"], 0.0))

        has_gps = "GPS_TX" in d or "GPS_RX" in d
        self.gpsVar.set(has_gps)
        self._toggle("gps")
        if "GPS_TX" in d:
            self._set_combo_pin(self.cbGpsTx, self._to_int(d["GPS_TX"], PINS_GPS[0]), False)
        if "GPS_RX" in d:
            self._set_combo_pin(self.cbGpsRx, self._to_int(d["GPS_RX"], PINS_GPS[0]), False)
        if d.get("GPS") in GPS_CODES:
            self.cbGpsType.current(GPS_CODES.index(d["GPS"]))

    # --------------------------------------------------------- .ini
    def save_ini(self):
        fname = filedialog.asksaveasfilename(defaultextension=".ini",
                                             initialfile="oXs_config.ini",
                                             filetypes=[("INI", "*.ini")])
        if not fname:
            return
        cfg = configparser.ConfigParser()
        cfg["oXs"] = {}
        for token in self.build_command().split(";"):
            token = token.strip()
            if "=" in token:
                k, v = token.split("=", 1)
                cfg["oXs"][k.strip()] = v.strip()
        cfg["oXs"]["_baro"] = str(self.baroVar.get())
        cfg["oXs"]["_v1"] = str(self.volt1Var.get())
        cfg["oXs"]["_v2"] = str(self.volt2Var.get())
        cfg["oXs"]["_gps"] = str(self.gpsVar.get())
        try:
            with open(fname, "w", encoding="utf-8") as fh:
                cfg.write(fh)
            self.txt.insert("end", f"\n[gespeichert: {fname}]\n")
        except Exception as e:
            self._error(f"Kann Datei nicht speichern:\n{e}")

    def load_ini(self):
        fname = filedialog.askopenfilename(filetypes=[("INI", "*.ini")])
        if not fname:
            return
        cfg = configparser.ConfigParser()
        try:
            cfg.read(fname, encoding="utf-8")
        except Exception as e:
            self._error(f"Kann Datei nicht lesen:\n{e}")
            return
        if "oXs" not in cfg:
            self._error("Datei enthaelt keine [oXs]-Sektion.")
            return
        d = {k.upper(): v for k, v in cfg["oXs"].items()}
        self.apply_config_dict(d)
        for flag, var in (("_BARO", "baroVar"), ("_V1", "volt1Var"),
                          ("_V2", "volt2Var"), ("_GPS", "gpsVar")):
            if flag in d:
                getattr(self, var).set(d[flag].lower() == "true")
        for name in ("baro", "volt1", "volt2", "gps"):
            self._toggle(name)
        self.txt.insert("end", f"\n[geladen: {fname}]\n")

    # ------------------------------------------------------- Helpers
    def _set_combo_pin(self, cb, value, with_off):
        cb.set(pin_to_label(value, with_off))

    def _set_entry(self, entry, text):
        state = entry.cget("state")
        entry.config(state="normal")
        entry.delete(0, "end")
        entry.insert(0, text)
        entry.config(state=state)

    @staticmethod
    def _fmt(s, default):
        try:
            return f"{float(s):g}"
        except (ValueError, TypeError):
            return f"{default:g}"

    @staticmethod
    def _to_int(s, default):
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return default

    def _error(self, msg):
        messagebox.showwarning("Hinweis", msg)

    # ----------------------------------------------------- Kalibrier-Assistent
    @staticmethod
    def _calc_scale_offset(v1, m1, v2, m2, bias_mv=0.0):
        """v1,v2 in Volt, m1,m2 in mV (FV-Rohwerte). bias_mv = Aufschlag (+ = Anzeige höher).
        Liefert (scale, offset_mV)."""
        if m2 == m1:
            raise ValueError("Die beiden Rohwerte sind gleich – Punkte müssen sich unterscheiden.")
        scale = (v2 * 1000.0 - v1 * 1000.0) / (m2 - m1)
        offset = scale * m1 - v1 * 1000.0 - bias_mv
        return scale, offset

    def open_calibration(self, n):
        pin = label_to_pin(getattr(self, f"volt{n}Pin").get())
        dlg = tk.Toplevel(self.root)
        dlg.title(f"V{n} kalibrieren (2-Punkt)")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        frm = ttk.Frame(dlg, padding=10)
        frm.pack(fill="both", expand=True)
        info = (
            f"V{n} an GPIO {pin}.  Max. 15 V → Spannungsteiler nötig (ADC-Pin max. 3,3 V!).\n\n"
            "1) »Vorbereiten« setzt scale=1 / offset=0 und speichert (oXs rebootet, verbindet neu).\n"
            "2) Bekannte Spannung anlegen, Multimeter-Wert eintragen, »messen (FV)« liest den Rohwert.\n"
            "   Tipp: Punkt 1 = 0 V (Eingang auf GND) fängt den Nullpunkt ab.\n"
            "3) »Berechnen«, dann »Übernehmen & speichern«."
        )
        ttk.Label(frm, text=info, justify="left").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        ttk.Button(frm, text="1) Vorbereiten: scale=1 / offset=0 → schreiben & speichern",
                   command=lambda: self._prepare_calibration(n)).grid(row=1, column=0, columnspan=4, sticky="we", pady=(0, 8))
        ttk.Label(frm, text="Spannung (V)").grid(row=2, column=1)
        ttk.Label(frm, text="Rohwert (mV)").grid(row=2, column=2)
        e = {}
        for i, (pt, vd) in enumerate([("Punkt 1", "0"), ("Punkt 2", "12")]):
            r = 3 + i
            ttk.Label(frm, text=pt + ":").grid(row=r, column=0, sticky="e", padx=(0, 4), pady=2)
            ev = ttk.Entry(frm, width=10); ev.insert(0, vd); ev.grid(row=r, column=1, padx=2, pady=2)
            em = ttk.Entry(frm, width=10); em.grid(row=r, column=2, padx=2, pady=2)
            ttk.Button(frm, text="messen (FV)", command=lambda ent=em: self._read_fv_raw(n, ent)).grid(row=r, column=3, padx=2)
            e[i] = (ev, em)
        ttk.Label(frm, text="Aufschlag (mV, + = Anzeige höher):").grid(row=5, column=0, columnspan=2, sticky="e", padx=(0, 4), pady=(6, 2))
        eBias = ttk.Entry(frm, width=10); eBias.insert(0, "0"); eBias.grid(row=5, column=2, padx=2, pady=(6, 2))
        lblResult = ttk.Label(frm, text="scale = –   offset = – mV", foreground="#00008b")
        lblResult.grid(row=6, column=0, columnspan=4, sticky="w", pady=(6, 6))
        result = {}

        def do_calc():
            try:
                v1 = float(e[0][0].get()); m1 = float(e[0][1].get())
                v2 = float(e[1][0].get()); m2 = float(e[1][1].get())
                bias = float(eBias.get())
                scale, offset = self._calc_scale_offset(v1, m1, v2, m2, bias)
            except ValueError as ex:
                self._error(f"Bitte gültige Zahlen eingeben.\n{ex}")
                return
            result["scale"], result["offset"] = scale, offset
            lblResult.config(text=f"scale = {scale:.4f}    offset = {offset:.1f} mV")

        def do_apply():
            if "scale" not in result:
                do_calc()
            if "scale" in result:
                self._apply_calibration(n, result["scale"], result["offset"])

        btns = ttk.Frame(frm)
        btns.grid(row=7, column=0, columnspan=4, sticky="we", pady=(6, 0))
        ttk.Button(btns, text="Berechnen", command=do_calc).pack(side="left")
        ttk.Button(btns, text="Übernehmen & speichern", command=do_apply).pack(side="left", padx=6)
        ttk.Button(btns, text="Schließen", command=dlg.destroy).pack(side="right")

    def _prepare_calibration(self, n):
        self._set_entry(getattr(self, f"volt{n}Scale"), "1")
        self._set_entry(getattr(self, f"volt{n}Offset"), "0")
        getattr(self, f"volt{n}Var").set(True); self._toggle(f"volt{n}")
        self.write_to_oxs(); self.save_on_oxs()

    def _apply_calibration(self, n, scale, offset):
        self._set_entry(getattr(self, f"volt{n}Scale"), f"{scale:g}")
        self._set_entry(getattr(self, f"volt{n}Offset"), f"{offset:g}")
        getattr(self, f"volt{n}Var").set(True); self._toggle(f"volt{n}")
        self.write_to_oxs(); self.save_on_oxs()

    def _read_fv_raw(self, n, entry):
        if self.ser is None:
            self._error("Nicht verbunden – zuerst 'Verbinden' und 'Vorbereiten'.")
            return
        self._fv_target = (n, entry)
        self._write("FV")
        self.root.after(800, self._fill_fv_raw)

    def _fill_fv_raw(self):
        n, entry = getattr(self, "_fv_target", (None, None))
        if entry is None:
            return
        text = self.txt.get("1.0", "end")
        if n == 1:
            matches = re.findall(r"Volt 1 = (-?\d+) mVolt", text)
        else:
            matches = re.findall(r"Current \(Volt 2\) = (-?\d+) mA", text)
        if matches:
            self._set_entry(entry, matches[-1])
        else:
            self._error("Konnte den Rohwert nicht lesen.\nIst 'Vorbereiten' erfolgt (scale=1/offset=0) "
                        "und liegt eine Spannung an?")

    # ----------------------------------------------------- Schaltplan / Pin-Belegung
    def _current_assignments(self):
        """Liste der belegten Pins: [{gpio, label, color}], aus dem aktuellen UI-Zustand."""
        col = {"TLM": "#1f77b4", "PRI": "#ff7f0e", "SEC": "#2ca02c",
               "SDA": "#9467bd", "SCL": "#8c564b", "V1": "#d62728",
               "V2": "#e6308a", "GPS_TX": "#0aa0b0", "GPS_RX": "#b0a000"}
        out = []
        code = PROTOCOL_CODES[self.cbProtocol.current()]
        hints = PIN_HINTS[code]
        for key, cb in (("PRI", self.cbPri), ("SEC", self.cbSec), ("TLM", self.cbTlm)):
            if self._protocol_uses(key):
                p = label_to_pin(cb.get())
                if p != OFF:
                    out.append({"gpio": p, "label": f"{key} → {hints[key]}", "color": col[key]})
        if self.baroVar.get():
            out.append({"gpio": label_to_pin(self.cbSda.get()), "label": "SDA → Baro-Sensor", "color": col["SDA"]})
            out.append({"gpio": label_to_pin(self.cbScl.get()), "label": "SCL → Baro-Sensor", "color": col["SCL"]})
        for n in (1, 2):
            if getattr(self, f"volt{n}Var").get():
                p = label_to_pin(getattr(self, f"volt{n}Pin").get())
                out.append({"gpio": p, "label": f"V{n} → Spannung (über Teiler!)", "color": col[f"V{n}"]})
        if self.gpsVar.get():
            out.append({"gpio": label_to_pin(self.cbGpsTx.get()), "label": "GPS_TX → GPS (RX)", "color": col["GPS_TX"]})
            out.append({"gpio": label_to_pin(self.cbGpsRx.get()), "label": "GPS_RX → GPS (TX)", "color": col["GPS_RX"]})
        return out

    @staticmethod
    def _rp2040zero_coords():
        """GPIO-Nummer -> (x, y, seite) auf dem gezeichneten Board (nur Randpins, keine SMD-Pads)."""
        xL, xR = 350, 510
        ys = [95 + i * 28 for i in range(9)]
        xy = {}
        for g, y in zip([0, 1, 2, 3, 4, 5, 6, 7, 8], ys):
            xy[g] = (xR, y, "e")                       # rechte Spalte
        for g, y in zip([29, 28, 27, 26, 15, 14], ys[3:]):
            xy[g] = (xL, y, "w")                       # linke Spalte (unten)
        for g, x in zip([13, 12, 11, 10, 9], [368, 403, 438, 473, 500]):
            xy[g] = (x, 345, "s")                      # untere Kante
        return xy

    def open_wiring(self):
        win = tk.Toplevel(self.root)
        win.title("Schaltplan / Verdrahtung – RP2040-Zero")
        win.transient(self.root)
        cv = tk.Canvas(win, width=920, height=600, bg="white", highlightthickness=0)
        cv.pack(fill="both", expand=True)
        bar = ttk.Frame(win); bar.pack(fill="x")
        ttk.Label(bar, text="Verbindungslinien der aktuell gewählten Pins. »Aktualisieren« nach Änderungen.",
                  foreground="gray").pack(side="left", padx=6, pady=4)
        ttk.Button(bar, text="Aktualisieren", command=lambda: self._draw_wiring(cv)).pack(side="right", padx=6, pady=4)
        self._draw_wiring(cv)

    def _draw_board(self, cv, xy, assigned):
        cv.create_text(430, 30, text="RP2040-Zero", font=("TkDefaultFont", 13, "bold"))
        cv.create_rectangle(350, 70, 510, 330, outline="#2b6cb0", width=2, fill="#eaf2fb")
        cv.create_rectangle(425, 55, 475, 72, outline="#888", fill="#cfcfcf")   # USB-C
        cv.create_text(450, 63, text="USB-C", font=("TkDefaultFont", 7))
        for lbl, y in zip(["5V", "GND", "3V3"], [95, 123, 151]):
            cv.create_oval(350 - 5, y - 5, 350 + 5, y + 5, fill="#ffd700", outline="#a07800")
            cv.create_text(350 - 12, y, text=lbl, anchor="e", font=("TkDefaultFont", 8))
        for g, (x, y, side) in xy.items():
            a = assigned.get(g)
            r = 7 if a else 5
            cv.create_oval(x - r, y - r, x + r, y + r, fill=(a["color"] if a else "#c9c9c9"), outline="#333")
            if side == "w":
                cv.create_text(x - 12, y, text=str(g), anchor="e", font=("TkDefaultFont", 8))
            elif side == "e":
                cv.create_text(x + 12, y, text=str(g), anchor="w", font=("TkDefaultFont", 8))
            else:
                cv.create_text(x, y + 12, text=str(g), anchor="n", font=("TkDefaultFont", 8))

    def _draw_divider(self, cv, dx, dy, a, pad, midx):
        """Zeichnet einen Spannungsteiler ~1:5 (E12: 39k/10k) links und verdrahtet ihn zum V-Pin."""
        c = a["color"]; px, py, _ = pad
        tag = a["label"].split(" ")[0]           # "V1" / "V2"
        cv.create_text(dx, dy - 64, text=f"Vin+ ({tag}, max 15 V)", font=("TkDefaultFont", 8))
        cv.create_line(dx, dy - 56, dx, dy - 42, width=2)                      # zu R1
        cv.create_rectangle(dx - 10, dy - 42, dx + 10, dy - 14, outline="#333", fill="white")
        cv.create_text(dx - 16, dy - 28, text="R1", anchor="e", font=("TkDefaultFont", 8))
        cv.create_text(dx + 16, dy - 28, text="39k", anchor="w", font=("TkDefaultFont", 8))
        cv.create_line(dx, dy - 14, dx, dy, width=2)                            # R1 -> Knoten
        cv.create_oval(dx - 3, dy - 3, dx + 3, dy + 3, fill="#333")             # Knoten
        cv.create_line(dx, dy, dx, dy + 14, width=2)                            # Knoten -> R2
        cv.create_rectangle(dx - 10, dy + 14, dx + 10, dy + 42, outline="#333", fill="white")
        cv.create_text(dx - 16, dy + 28, text="R2", anchor="e", font=("TkDefaultFont", 8))
        cv.create_text(dx + 16, dy + 28, text="10k", anchor="w", font=("TkDefaultFont", 8))
        cv.create_line(dx, dy + 42, dx, dy + 56, width=2)                       # R2 -> GND
        for i, w in enumerate((15, 9, 3)):                                      # GND-Symbol
            cv.create_line(dx - w, dy + 56 + i * 4, dx + w, dy + 56 + i * 4, width=2)
        cv.create_text(dx, dy + 74, text="GND", font=("TkDefaultFont", 8))
        # farbige Leitung vom Knoten (orthogonal) zum V-Pin
        cv.create_line(dx, dy, midx, dy, midx, py, px, py, fill=c, width=2)
        cv.create_text((midx + px) / 2, py - 8, text=tag, fill=c, font=("TkDefaultFont", 9, "bold"))

    def _draw_wiring(self, cv):
        cv.delete("all")
        xy = self._rp2040zero_coords()
        alist = [a for a in self._current_assignments() if a["gpio"] != OFF and a["gpio"] in xy]
        assigned = {a["gpio"]: a for a in alist}
        self._draw_board(cv, xy, assigned)

        volts = [a for a in alist if a["label"].startswith("V")]
        others = [a for a in alist if not a["label"].startswith("V")]

        # --- Signal-Leitungen nach rechts zu beschrifteten Bausteinen ---
        others.sort(key=lambda a: xy[a["gpio"]][1])
        bx, bw, bh, gap = 590, 300, 22, 8
        prev = 78
        for a in others:
            g = a["gpio"]; px, py, side = xy[g]
            boxy = max(py - bh // 2, prev)
            prev = boxy + bh + gap
            cv.create_line(px, py, px + 20, py, bx, boxy + bh // 2, fill=a["color"], width=2)
            cv.create_rectangle(bx, boxy, bx + bw, boxy + bh, outline=a["color"], fill="#f7f7f7", width=2)
            cv.create_text(bx + 6, boxy + bh // 2, text=f"GP{g}: {a['label']}", anchor="w",
                           font=("TkDefaultFont", 9))

        # --- Spannungsteiler links (nach Pin-Höhe sortiert, damit die Leitungen nicht kreuzen) ---
        volts.sort(key=lambda a: xy[a["gpio"]][1])
        dys = [150, 350]
        midxs = [235, 255]
        for i, a in enumerate(volts[:2]):
            self._draw_divider(cv, 140, dys[i], a, xy[a["gpio"]], midxs[i])

        # --- Hinweise ---
        if not alist:
            cv.create_text(590, 90, text="(noch nichts gewählt)", anchor="w", fill="gray")
        cv.create_text(140, 470,
                       text="Spannungsteiler ≈ 1:5  (E12: 39k / 10k)\n"
                            "→ bei 15 V ~3,06 V am Pin.\n"
                            "Exakte Skalierung setzt die Kalibrierung.",
                       justify="center", fill="#a00", font=("TkDefaultFont", 8))
        cv.create_text(590, 560,
                       text="Empfänger / GPS zusätzlich an 5V (oder 3V3) + GND anschließen.",
                       anchor="w", fill="#555", font=("TkDefaultFont", 8))


def main():
    root = tk.Tk()
    OxsGui(root)
    root.geometry("820x760")
    root.mainloop()


if __name__ == "__main__":
    main()
