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
    
    # Reagrupar clips por bloques
    bloques = []
    bloque_actual = []
    
    if tl:
        for i, clip in enumerate(tl):
            if i == 0:
                bloque_actual = [clip]
            else:
                gap = clip['offset_s'] - (tl[i-1]['offset_s'] + tl[i-1]['dur_s'])
                if gap > 1.0:
                    bloques.append(bloque_actual)
                    bloque_actual = [clip]
                else:
                    bloque_actual.append(clip)
        
        if bloque_actual:
            bloques.append(bloque_actual)

    # SOLO crear las pistas necesarias (máximo clips por bloque)
    max_pistas_necesarias = max(len(bloque) for bloque in bloques) if bloques else 1
    total_duration = s_to_frames(max(clip['offset_s'] + clip['dur_s'] for clip in tl) if tl else 0)
    
    print(f"DEBUG: {len(bloques)} bloques, máximo {max_pistas_necesarias} pistas necesarias")
    for i, bloque in enumerate(bloques):
        print(f"  Bloque {i+1}: {len(bloque)} clips")
    
    # Construir XML
    xml_lines = []
    xml_lines.extend([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE xmeml>',
        '<xmeml version="1">',
        '<project>',
        '<name>Secuencia Vertical CORREGIDA</name>',
        '<children>',
        '<sequence id="sequence-1">',
        '<name>Secuencia Vertical CORREGIDA</name>',
        f'<duration>{total_duration}</duration>',
        '<rate>',
        f'<timebase>{fps}</timebase>',
        '<ntsc>FALSE</ntsc>',
        '</rate>',
        '<timecode>',
        '<rate>',
        f'<timebase>{fps}</timebase>',
        '<ntsc>FALSE</ntsc>',
        '</rate>',
        '<string>00:00:00:00</string>',
        '<frame>0</frame>',
        '<source>source</source>',
        '<displayformat>NDF</displayformat>',
        '</timecode>',
        '<media>',
        '<video>',
        '<format>',
        '<samplecharacteristics>',
        '<rate>',
        f'<timebase>{fps}</timebase>',
        '<ntsc>FALSE</ntsc>',
        '</rate>',
        '<width>1080</width>',
        '<height>1920</height>',
        '<anamorphic>FALSE</anamorphic>',
        '<pixelaspectratio>square</pixelaspectratio>',
        '<fielddominance>none</fielddominance>',
        '<colordepth>24</colordepth>',
        '</samplecharacteristics>',
        '</format>'
    ])

    # CLAVE: Solo crear las pistas mínimas necesarias
    for num_pista in range(1, max_pistas_necesarias + 1):
        xml_lines.extend([
            '<track>',
            '<enabled>TRUE</enabled>',
            '<locked>FALSE</locked>'
        ])
        
        # Para esta pista, buscar clips en TODOS los bloques
        clip_global_index = 0
        
        for bloque_idx, bloque in enumerate(bloques):
            # Solo si este bloque tiene un clip en esta posición
            if num_pista <= len(bloque):
                clip = bloque[num_pista - 1]  # Clip en posición num_pista del bloque
                
                # Calcular el índice global de la imagen
                clips_antes_de_este_bloque = sum(len(b) for b in bloques[:bloque_idx])
                indice_imagen_global = clips_antes_de_este_bloque + (num_pista - 1)
                
                if indice_imagen_global < len(pngs):
                    src_file = pngs[indice_imagen_global]
                    start_frame = s_to_frames(clip['offset_s'])
                    end_frame = s_to_frames(clip['offset_s'] + clip['dur_s'])
                    duration_frames = s_to_frames(clip['dur_s'])
                    
                    print(f"  V{num_pista}: Bloque {bloque_idx+1} -> {src_file.name} ({start_frame}-{end_frame})")
                    
                    xml_lines.extend([
                        f'<clipitem id="clipitem-v{num_pista}-b{bloque_idx}">',
                        f'<name>{src_file.name}</name>',
                        '<enabled>TRUE</enabled>',
                        f'<duration>{duration_frames}</duration>',
                        f'<start>{start_frame}</start>',
                        f'<end>{end_frame}</end>',
                        '<in>0</in>',
                        f'<out>{duration_frames}</out>',
                        f'<file id="file-{indice_imagen_global}">',
                        f'<name>{src_file.name}</name>',
                        f'<pathurl>file://localhost{src_file.resolve()}</pathurl>',
                        '<rate>',
                        f'<timebase>{fps}</timebase>',
                        '<ntsc>FALSE</ntsc>',
                        '</rate>',
                        f'<duration>{duration_frames}</duration>',
                        '<media>',
                        '<video>',
                        '<samplecharacteristics>',
                        '<rate>',
                        f'<timebase>{fps}</timebase>',
                        '<ntsc>FALSE</ntsc>',
                        '</rate>',
                        '<width>1080</width>',
                        '<height>1920</height>',
                        '<anamorphic>FALSE</anamorphic>',
                        '<pixelaspectratio>square</pixelaspectratio>',
                        '<fielddominance>none</fielddominance>',
                        '<colordepth>24</colordepth>',
                        '</samplecharacteristics>',
                        '</video>',
                        '</media>',
                        '</file>',
                        '<sourcetrack>',
                        '<mediatype>video</mediatype>',
                        '<trackindex>1</trackindex>',
                        '</sourcetrack>',
                        '</clipitem>'
                    ])
        
        xml_lines.append('</track>')
    
    xml_lines.extend([
        '</video>',
        '<audio>',
        '<numOutputChannels>2</numOutputChannels>',
        '<format>',
        '<samplecharacteristics>',
        '<depth>16</depth>',
        '<samplerate>48000</samplerate>',
        '</samplecharacteristics>',
        '</format>',
        '<outputs>',
        '<group>',
        '<index>1</index>',
        '<numchannels>1</numchannels>',
        '<downmix>0</downmix>',
        '<channel>',
        '<index>1</index>',
        '</channel>',
        '</group>',
        '<group>',
        '<index>2</index>',
        '<numchannels>1</numchannels>',
        '<downmix>0</downmix>',
        '<channel>',
        '<index>2</index>',
        '</channel>',
        '</group>',
        '</outputs>',
        '</audio>',
        '</media>',
        '</sequence>',
        '</children>',
        '</project>',
        '</xmeml>'
    ])

    Path(output).write_text('\n'.join(xml_lines), encoding="utf-8")

# ——— GUI ———
class App:
    def __init__(self, root):
        root.title("🎯 PISTAS DEFINITIVAS - No más subir canales")
        Label(root, text="FPS:").grid(row=0, column=0)
        self.fps = IntVar(value=30)
        Entry(root, textvariable=self.fps).grid(row=0, column=1)
        Button(root, text=".srt",             command=self.sel_srt).grid(row=1, column=0, columnspan=2, sticky="ew")
        Button(root, text="XML markers",      command=self.sel_xml).grid(row=2, column=0, columnspan=2, sticky="ew")
        Button(root, text="Carpeta imágenes", command=self.sel_imgs).grid(row=3, column=0, columnspan=2, sticky="ew")
        Button(root, text="Destino XML",      command=self.sel_dest).grid(row=4, column=0, columnspan=2, sticky="ew")
        Button(root, text="🎯 CORREGIR PISTAS", command=self.run, bg='#28a745', fg='white').grid(row=5, column=0, columnspan=2, sticky="ew")
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
            out     = self.paths.get('dest') or 'PISTAS_CORREGIDAS.xml'
            exportar_xml(tl, self.paths['imgs'], out, fps)
            messagebox.showinfo('🎯 PISTAS CORREGIDAS!','Ahora reinicia desde V1 en cada bloque!\n\nArchivo: {}'.format(out))
        except Exception as e:
            messagebox.showerror('❌ Error', str(e))

if __name__ == '__main__':
    root = Tk(); root.geometry('450x300')
    App(root)
    root.mainloop()