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
            offset = s['inicio'].total_seconds()
            # Todos los clips del bloque terminan al final del bloque
            duration = (fin - s['inicio']).total_seconds()
            timeline.append({
                'archivo':  f"{cnt}.png",
                'offset_s': offset,
                'dur_s':    duration,
                'bloque_fin': fin.total_seconds()
            })
            cnt += 1
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
    
    # Reagrupar clips por bloques (detectando gaps)
    bloques = []
    bloque_actual = []
    
    if tl:
        for i, clip in enumerate(tl):
            if i == 0:
                bloque_actual = [clip]
            else:
                gap = clip['offset_s'] - (tl[i-1]['offset_s'] + tl[i-1]['dur_s'])
                if gap > 1.0:  # Gap > 1 segundo = nuevo bloque
                    bloques.append(bloque_actual)
                    bloque_actual = [clip]
                else:
                    bloque_actual.append(clip)
        
        if bloque_actual:
            bloques.append(bloque_actual)

    # Determinar cuántas pistas necesitamos (máximo clips por bloque)
    max_pistas = max(len(bloque) for bloque in bloques) if bloques else 1
    
    # Calcular duración total
    total_duration = s_to_frames(max(clip['offset_s'] + clip['dur_s'] for clip in tl) if tl else 0)
    
    # Construir XML línea por línea
    xml_content = []
    xml_content.append('<?xml version="1.0" encoding="UTF-8"?>')
    xml_content.append('<!DOCTYPE xmeml>')
    xml_content.append('<xmeml version="1">')
    xml_content.append('<project>')
    xml_content.append('<' + 'name' + '>Auto Premiere Sequence Vertical</' + 'name' + '>')
    xml_content.append('<children>')
    xml_content.append('<sequence id="autoseq">')
    xml_content.append('<' + 'name' + '>Auto Sequence Vertical</' + 'name' + '>')
    xml_content.append(f'<duration>{total_duration}</duration>')
    xml_content.append('<rate>')
    xml_content.append(f'<timebase>{fps}</timebase>')
    xml_content.append('<ntsc>FALSE</ntsc>')
    xml_content.append('</rate>')
    # CORRECCION 1: Configurar secuencia como vertical desde el inicio
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

    # CORRECCION 3: Crear pistas correctamente, cada bloque reinicia desde V1
    global_clip_index = 0  # Índice global para las imágenes
    
    for track_num in range(1, max_pistas + 1):
        xml_content.append('<track>')
        xml_content.append('<enabled>TRUE</enabled>')
        xml_content.append('<locked>FALSE</locked>')
        
        # Para cada bloque, verificar si tiene clip en esta pista
        temp_clip_index = 0  # Índice temporal para calcular posiciones
        
        for bloque_idx, bloque in enumerate(bloques):
            if track_num <= len(bloque):  # Si este bloque tiene clip en esta pista
                clip = bloque[track_num - 1]  # track_num-1 porque las pistas son 1-indexed
                
                # CORRECCION 2: Calcular el índice correcto de la imagen
                clip_index_in_block = track_num - 1  # Posición dentro del bloque (0-indexed)
                clips_before_this_block = sum(len(b) for b in bloques[:bloque_idx])
                global_image_index = clips_before_this_block + clip_index_in_block
                
                if global_image_index < len(pngs):
                    src_file = pngs[global_image_index]
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
                    xml_content.append(f'<file id="file-{global_image_index}">')
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
                    # CORRECCION 1: Asegurar formato vertical 9:16
                    xml_content.append('<width>1080</width>')
                    xml_content.append('<height>1920</height>')
                    xml_content.append('<anamorphic>FALSE</anamorphic>')
                    xml_content.append('<pixelaspectratio>square</pixelaspectratio>')
                    xml_content.append('<fielddominance>none</fielddominance>')
                    xml_content.append('<colordepth>24</colordepth>')
                    xml_content.append('</samplecharacteristics>')
                    xml_content.append('</video>')
                    xml_content.append('</media>')
                    xml_content.append('</file>')
                    xml_content.append('<sourcetrack>')
                    xml_content.append('<mediatype>video</mediatype>')
                    xml_content.append('<trackindex>1</trackindex>')
                    xml_content.append('</sourcetrack>')
                    xml_content.append('</clipitem>')
        
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
        root.title("Auto Premiere XML Vertical (9:16) - CORREGIDO")
        Label(root, text="FPS:").grid(row=0, column=0)
        self.fps = IntVar(value=30)
        Entry(root, textvariable=self.fps).grid(row=0, column=1)
        Button(root, text=".srt",             command=self.sel_srt).grid(row=1, column=0, columnspan=2, sticky="ew")
        Button(root, text="XML markers",      command=self.sel_xml).grid(row=2, column=0, columnspan=2, sticky="ew")
        Button(root, text="Carpeta imágenes", command=self.sel_imgs).grid(row=3, column=0, columnspan=2, sticky="ew")
        Button(root, text="Destino XML",      command=self.sel_dest).grid(row=4, column=0, columnspan=2, sticky="ew")
        Button(root, text="🎬 Generar XML Vertical", command=self.run).grid(row=5, column=0, columnspan=2, sticky="ew")
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
            out     = self.paths.get('dest') or 'secuencia_vertical.xml'
            exportar_xml(tl, self.paths['imgs'], out, fps)
            messagebox.showinfo('✅ ¡Listo!','XML vertical generado!\nImporta "{}" en Premiere Pro'.format(out))
        except Exception as e:
            messagebox.showerror('❌ Error', str(e))

if __name__ == '__main__':
    root = Tk(); root.geometry('350x280')
    App(root)
    root.mainloop()