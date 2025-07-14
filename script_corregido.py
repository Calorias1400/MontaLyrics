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
        bloque_clips = []
        for idx, s in enumerate(subs):
            offset = s['inicio'].total_seconds()
            # CAMBIO: Todos los clips del bloque terminan al final del bloque
            duration = (fin - s['inicio']).total_seconds()
            bloque_clips.append({
                'archivo':  f"{cnt}.png",
                'offset_s': offset,
                'dur_s':    duration,
                'bloque_fin': fin.total_seconds()  # Para referencia
            })
            cnt += 1
        timeline.extend(bloque_clips)
    return timeline

# ——— Exportar XML para Premiere Pro ———
def exportar_xml(tl, imgs_dir, output, fps):
    img_folder = Path(imgs_dir)
    def sort_key(p):
        m = re.search(r"(\d+)(?=\.png$)", p.name)
        return int(m.group(1)) if m else p.name
    pngs = sorted(img_folder.glob("*.png"), key=sort_key)
    if len(pngs) < len(tl):
        raise ValueError(f"Encontré {len(pngs)} PNGs, pero necesito {len(tl)}.")

    def s_to_frames(sec):
        return int(round(sec * fps))
    
    # Detectar bloques analizando gaps en el timeline
    bloques = []
    bloque_actual = []
    
    if tl:
        for i, clip in enumerate(tl):
            if i == 0:
                bloque_actual = [clip]
            else:
                # Si hay un gap grande (>1 segundo) entre clips, es un nuevo bloque
                gap = clip['offset_s'] - (tl[i-1]['offset_s'] + tl[i-1]['dur_s'])
                if gap > 1.0:  # Nuevo bloque
                    bloques.append(bloque_actual)
                    bloque_actual = [clip]
                else:
                    bloque_actual.append(clip)
        
        if bloque_actual:
            bloques.append(bloque_actual)

    # CAMBIO: Determinar pistas por bloque (cada bloque reinicia desde V1)
    max_pistas_por_bloque = max(len(bloque) for bloque in bloques) if bloques else 1
    
    # Calcular duración total
    total_duration = s_to_frames(max(clip['offset_s'] + clip['dur_s'] for clip in tl) if tl else 0)
    
    # Construir XML línea por línea
    xml_content = []
    xml_content.append('<?xml version="1.0" encoding="UTF-8"?>')
    xml_content.append('<!DOCTYPE xmeml>')
    xml_content.append('<xmeml version="1">')
    xml_content.append('<project>')
    xml_content.append('<' + 'name' + '>Auto Premiere Sequence</' + 'name' + '>')
    xml_content.append('<children>')
    xml_content.append('<sequence id="autoseq">')
    xml_content.append('<' + 'name' + '>Auto Sequence</' + 'name' + '>')
    xml_content.append(f'<duration>{total_duration}</duration>')
    xml_content.append('<rate>')
    xml_content.append(f'<timebase>{fps}</timebase>')
    xml_content.append('<ntsc>FALSE</ntsc>')
    xml_content.append('</rate>')
    xml_content.append('<timecode>')
    xml_content.append('<rate>')
    xml_content.append(f'<timebase>{fps}</timebase>')
    xml_content.append('<ntsc>FALSE</ntsc>')
    xml_content.append('</rate>')
    xml_content.append('<string>00:00:00:00</string>')
    xml_content.append('<frame>0</frame>')
    xml_content.append('<source>source</source>')
    xml_content.append('<displayformat>NDF</displayformat>')
    xml_content.append('</timecode>')
    xml_content.append('<media>')
    xml_content.append('<video>')

    # CAMBIO: Crear pistas según el máximo por bloque
    for track_num in range(1, max_pistas_por_bloque + 1):
        xml_content.append('<track>')
        xml_content.append('<enabled>TRUE</enabled>')
        xml_content.append('<locked>FALSE</locked>')
        
        # CAMBIO: Agregar clips a la pista actual, reiniciando por bloque
        png_index = 0
        for bloque_idx, bloque in enumerate(bloques):
            if track_num <= len(bloque):
                clip = bloque[track_num - 1]  # track_num es 1-indexed dentro del bloque
                
                if png_index < len(pngs):
                    src_file = pngs[png_index]
                    start_frame = s_to_frames(clip['offset_s'])
                    end_frame = s_to_frames(clip['offset_s'] + clip['dur_s'])
                    duration_frames = s_to_frames(clip['dur_s'])
                    
                    xml_content.append(f'<clipitem id="clipitem-{track_num}-{bloque_idx}">')
                    xml_content.append(f'<' + 'name' + '>{src_file.name}</' + 'name' + '>')
                    xml_content.append('<enabled>TRUE</enabled>')
                    xml_content.append(f'<duration>{duration_frames}</duration>')
                    xml_content.append(f'<start>{start_frame}</start>')
                    xml_content.append(f'<end>{end_frame}</end>')
                    xml_content.append('<in>0</in>')
                    xml_content.append(f'<out>{duration_frames}</out>')
                    xml_content.append(f'<file id="file-{png_index}">')
                    xml_content.append(f'<' + 'name' + '>{src_file.name}</' + 'name' + '>')
                    xml_content.append(f'<pathurl>file://localhost{src_file.resolve()}</pathurl>')
                    xml_content.append('<rate>')
                    xml_content.append(f'<timebase>{fps}</timebase>')
                    xml_content.append('<ntsc>FALSE</ntsc>')
                    xml_content.append('</rate>')
                    xml_content.append(f'<duration>{duration_frames}</duration>')
                    xml_content.append('<media>')
                    xml_content.append('<video>')
                    xml_content.append('<samplecharacteristics>')
                    xml_content.append('<rate>')
                    xml_content.append(f'<timebase>{fps}</timebase>')
                    xml_content.append('<ntsc>FALSE</ntsc>')
                    xml_content.append('</rate>')
                    # CAMBIO: Formato 9:16 (1080x1920 en lugar de 1920x1080)
                    xml_content.append('<width>1080</width>')
                    xml_content.append('<height>1920</height>')
                    xml_content.append('<anamorphic>FALSE</anamorphic>')
                    xml_content.append('<pixelaspectratio>square</pixelaspectratio>')
                    xml_content.append('<fielddominance>none</fielddominance>')
                    xml_content.append('</samplecharacteristics>')
                    xml_content.append('</video>')
                    xml_content.append('</media>')
                    xml_content.append('</file>')
                    xml_content.append('<sourcetrack>')
                    xml_content.append('<mediatype>video</mediatype>')
                    xml_content.append('<trackindex>1</trackindex>')
                    xml_content.append('</sourcetrack>')
                    xml_content.append('</clipitem>')
                
                png_index += 1
            else:
                # Si no hay clip para esta pista en este bloque, avanzar el índice según clips del bloque
                png_index += len(bloque) - (track_num - 1)
                break
        
        xml_content.append('</track>')
    
    xml_content.append('</video>')
    xml_content.append('</media>')
    xml_content.append('</sequence>')
    xml_content.append('</children>')
    xml_content.append('</project>')
    xml_content.append('</xmeml>')

    Path(output).write_text('\n'.join(xml_content), encoding="utf-8")

# ——— GUI ———
class App:
    def __init__(self, root):
        root.title("Auto Premiere Sequence XML (9:16)")
        Label(root, text="FPS:").grid(row=0, column=0)
        self.fps = IntVar(value=30)
        Entry(root, textvariable=self.fps).grid(row=0, column=1)
        Button(root, text=".srt",             command=self.sel_srt).grid(row=1, column=0, columnspan=2, sticky="ew")
        Button(root, text="XML markers",      command=self.sel_xml).grid(row=2, column=0, columnspan=2, sticky="ew")
        Button(root, text="Carpeta imágenes", command=self.sel_imgs).grid(row=3, column=0, columnspan=2, sticky="ew")
        Button(root, text="Destino XML",      command=self.sel_dest).grid(row=4, column=0, columnspan=2, sticky="ew")
        Button(root, text="Generar XML (9:16)", command=self.run).grid(row=5, column=0, columnspan=2, sticky="ew")
        self.paths = {'srt': None, 'xml': None, 'imgs': None, 'dest': None}

    def sel_srt(self):  self.paths['srt']  = filedialog.askopenfilename(filetypes=[('SRT','*.srt')])
    def sel_xml(self):  self.paths['xml']  = filedialog.askopenfilename(filetypes=[('XML','*.xml')])
    def sel_imgs(self): self.paths['imgs'] = filedialog.askdirectory()
    def sel_dest(self): self.paths['dest'] = filedialog.asksaveasfilename(defaultextension='.xml', filetypes=[('XML','*.xml')])

    def run(self):
        try:
            fps     = self.fps.get()
            subs    = leer_srt(self.paths['srt'])
            markers = leer_markers(self.paths['xml'], fps)
            bloques = generar_bloques_por_pares(markers, subs)
            tl      = generar_timeline(bloques)
            out     = self.paths.get('dest') or 'secuencia.xml'
            exportar_xml(tl, self.paths['imgs'], out, fps)
            messagebox.showinfo('¡Listo!','Importa "{}" en Premiere (Archivo > Importar…)'.format(out))
        except Exception as e:
            messagebox.showerror('Error', str(e))

if __name__ == '__main__':
    root = Tk(); root.geometry('320x260')
    App(root)
    root.mainloop()