#!/usr/bin/env python3
import re
import xml.etree.ElementTree as ET
from datetime import timedelta
from pathlib import Path
from tkinter import Tk, Label, Entry, Button, filedialog, IntVar, messagebox

# ——— Utilitarios ———
def parse_time(ts):
    h, m, rest = ts.split(":")
    s, ms      = rest.split(",")
    return timedelta(hours=int(h), minutes=int(m), seconds=int(s), milliseconds=int(ms))

def leer_srt(path):
    text    = Path(path).read_text(encoding="utf-8")
    bloques = re.findall(
        r"\d+\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+)",
        text
    )
    return [{"inicio": parse_time(a), "fin": parse_time(b), "texto": c} for a, b, c in bloques]

def leer_markers(path, fps):
    tree    = ET.parse(path)
    root    = tree.getroot()
    markers = []
    for m in root.iter("marker"):
        el_in    = m.find("in")
        el_start = m.find("start")
        if el_in is not None and el_in.text:
            el = el_in
        elif el_start is not None and el_start.text:
            el = el_start
        else:
            continue
        try:
            frame_num = int(el.text)
        except ValueError:
            continue
        markers.append(timedelta(seconds=frame_num / fps))
    if not markers:
        raise ValueError(f"No encontré markers válidos en {path!r}.")
    return sorted(markers)

def generar_bloques_por_pares(markers, subs):
    bloques = []
    for i in range(0, len(markers), 2):
        if i + 1 >= len(markers): break
        ini, fin = markers[i], markers[i+1]
        grupo = [s for s in subs if not (s['fin'] <= ini or s['inicio'] >= fin)]
        if grupo:
            bloques.append((ini, fin, grupo))
    return bloques

def generar_timeline(bloques):
    timeline = []
    cnt      = 1
    for ini, fin, subs in bloques:
        for idx, s in enumerate(subs):
            offset     = s['inicio'].total_seconds()
            if idx < len(subs) - 1:
                next_start = subs[idx+1]['inicio']
                duration   = (next_start - s['inicio']).total_seconds()
            else:
                duration   = (fin - s['inicio']).total_seconds()
            timeline.append({
                'archivo':  f"{cnt}.png",
                'offset_s': offset,
                'dur_s':    duration
            })
            cnt += 1
    return timeline

# ——— Exportar EDL con gap inicial ———
def exportar_edl(tl, imgs_dir, output, fps):
    img_folder = Path(imgs_dir)
    def sort_key(p):
        m = re.search(r"(\d+)(?=\.png$)", p.name)
        return int(m.group(1)) if m else p.name
    pngs = sorted(img_folder.glob("*.png"), key=sort_key)
    if len(pngs) < len(tl):
        raise ValueError(f"Encontré {len(pngs)} PNGs, pero necesito {len(tl)}.")

    def s_to_tc(sec):
        frames = round(sec * fps)
        hh     = frames // (fps*3600)
        mm     = (frames % (fps*3600)) // (fps*60)
        ss     = (frames % (fps*60))   // fps
        ff     = frames % fps
        return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"

    lines = ["TITLE:  AUTOSEQ", "FCM: NON-DROP FRAME\n"]
    # GAP inicial: dura hasta el primer offset
    if tl:
        first_offset = tl[0]['offset_s']
        gap_in     = '00:00:00:00'
        gap_out    = s_to_tc(first_offset)
        lines.append(f"001  BL  V  C   {gap_in} {gap_out} {gap_in} {gap_out}")
        lines.append("")
    # Eventos de imágenes
    for idx, clip in enumerate(tl, start=2 if tl else 1):
        src     = pngs[idx-2]  # desplazado 1 si hubo gap
        in_tc   = '00:00:00:00'
        out_tc  = s_to_tc(clip['dur_s'])
        rec_in  = s_to_tc(clip['offset_s'])
        rec_out = s_to_tc(clip['offset_s'] + clip['dur_s'])
        reel    = src.name
        lines.append(f"{idx:03d}  {reel}  V  C   {in_tc} {out_tc} {rec_in} {rec_out}")
        lines.append(f"* SOURCE FILE: {src.resolve()}")
        lines.append("")

    Path(output).write_text("\n".join(lines), encoding="utf-8")

# ——— GUI ———
class App:
    def __init__(self, root):
        root.title("Auto Premiere Sequence")
        Label(root, text="FPS:").grid(row=0, column=0)
        self.fps = IntVar(value=30)
        Entry(root, textvariable=self.fps).grid(row=0, column=1)
        Button(root, text=".srt",             command=self.sel_srt).grid(row=1, column=0, columnspan=2, sticky="ew")
        Button(root, text="XML markers",      command=self.sel_xml).grid(row=2, column=0, columnspan=2, sticky="ew")
        Button(root, text="Carpeta imágenes", command=self.sel_imgs).grid(row=3, column=0, columnspan=2, sticky="ew")
        Button(root, text="Destino EDL",      command=self.sel_dest).grid(row=4, column=0, columnspan=2, sticky="ew")
        Button(root, text="Generar EDL",      command=self.run).grid(row=5, column=0, columnspan=2, sticky="ew")
        self.paths = {'srt': None, 'xml': None, 'imgs': None, 'dest': None}

    def sel_srt(self):  self.paths['srt']  = filedialog.askopenfilename(filetypes=[('SRT','*.srt')])
    def sel_xml(self):  self.paths['xml']  = filedialog.askopenfilename(filetypes=[('XML','*.xml')])
    def sel_imgs(self): self.paths['imgs'] = filedialog.askdirectory()
    def sel_dest(self): self.paths['dest'] = filedialog.asksaveasfilename(defaultextension='.edl', filetypes=[('EDL','*.edl')])

    def run(self):
        try:
            fps     = self.fps.get()
            subs    = leer_srt(self.paths['srt'])
            markers = leer_markers(self.paths['xml'], fps)
            bloques = generar_bloques_por_pares(markers, subs)
            tl      = generar_timeline(bloques)
            out     = self.paths.get('dest') or 'secuencia.edl'
            exportar_edl(tl, self.paths['imgs'], out, fps)
            messagebox.showinfo('¡Listo!','Importa "{}" en Premiere (Archivo > Importar…)'.format(out))
        except Exception as e:
            messagebox.showerror('Error', str(e))

if __name__ == '__main__':
    root = Tk(); root.geometry('320x260')
    App(root)
    root.mainloop()
