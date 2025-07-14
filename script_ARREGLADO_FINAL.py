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
    
    # NO REDETECTAR - Usar los bloques originales que ya vienen de generar_bloques_por_pares
    subs = leer_srt(Path(imgs_dir).parent / "subtitulos.srt")  # Ajustar según tu estructura
    markers = leer_markers(Path(imgs_dir).parent / "markers.xml", fps)  # Ajustar según tu estructura
    bloques_originales = generar_bloques_por_pares(markers, subs)
    
    # SIMPLIFICADO: usar números de clips por bloque basado en timeline
    clip_counts_por_bloque = []
    total_clips_hasta_ahora = 0
    
    for ini, fin, subs_bloque in bloques_originales:
        clips_en_este_bloque = len(subs_bloque)
        clip_counts_por_bloque.append(clips_en_este_bloque)
        total_clips_hasta_ahora += clips_en_este_bloque
    
    # La clave: SOLO crear pistas según el bloque más grande
    max_clips_por_bloque = max(clip_counts_por_bloque) if clip_counts_por_bloque else 1
    total_duration = s_to_frames(max(clip['offset_s'] + clip['dur_s'] for clip in tl) if tl else 0)
    
    print(f"🔍 DEBUG: {len(bloques_originales)} bloques detectados")
    for i, count in enumerate(clip_counts_por_bloque):
        print(f"   Bloque {i+1}: {count} clips")
    print(f"   Máximo clips por bloque: {max_clips_por_bloque}")
    print(f"   ✅ Creando SOLO {max_clips_por_bloque} pistas (V1-V{max_clips_por_bloque})")
    
    # Construir XML
    xml_lines = []
    xml_lines.extend([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE xmeml>',
        '<xmeml version="1">',
        '<project>',
        '<name>Secuencia ARREGLADA</name>',
        '<children>',
        '<sequence id="sequence-1">',
        '<name>Secuencia ARREGLADA</name>',
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

    # CREAR SOLO LAS PISTAS NECESARIAS
    for num_pista in range(1, max_clips_por_bloque + 1):
        xml_lines.extend([
            '<track>',
            '<enabled>TRUE</enabled>',
            '<locked>FALSE</locked>'
        ])
        
        # Para esta pista, colocar clips según la posición en cada bloque
        indice_imagen_global = 0
        
        for bloque_idx, clips_en_bloque in enumerate(clip_counts_por_bloque):
            # Si este bloque tiene un clip en la posición num_pista
            if num_pista <= clips_en_bloque:
                # Encontrar el clip correspondiente en el timeline
                posicion_en_bloque = num_pista - 1  # 0-indexed
                indice_clip_global = sum(clip_counts_por_bloque[:bloque_idx]) + posicion_en_bloque
                
                if indice_clip_global < len(tl) and indice_clip_global < len(pngs):
                    clip = tl[indice_clip_global]
                    src_file = pngs[indice_clip_global]
                    
                    start_frame = s_to_frames(clip['offset_s'])
                    end_frame = s_to_frames(clip['offset_s'] + clip['dur_s'])
                    duration_frames = s_to_frames(clip['dur_s'])
                    
                    print(f"   V{num_pista}: Bloque {bloque_idx+1} -> {src_file.name}")
                    
                    xml_lines.extend([
                        f'<clipitem id="clipitem-v{num_pista}-b{bloque_idx}">',
                        f'<name>{src_file.name}</name>',
                        '<enabled>TRUE</enabled>',
                        f'<duration>{duration_frames}</duration>',
                        f'<start>{start_frame}</start>',
                        f'<end>{end_frame}</end>',
                        '<in>0</in>',
                        f'<out>{duration_frames}</out>',
                        f'<file id="file-{indice_clip_global}">',
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
    print(f"✅ XML creado con SOLO {max_clips_por_bloque} pistas")

# ——— GUI ———
class App:
    def __init__(self, root):
        root.title("🔧 ARREGLADO FINAL - Solo pistas necesarias")
        Label(root, text="FPS:").grid(row=0, column=0)
        self.fps = IntVar(value=30)
        Entry(root, textvariable=self.fps).grid(row=0, column=1)
        Button(root, text=".srt",             command=self.sel_srt).grid(row=1, column=0, columnspan=2, sticky="ew")
        Button(root, text="XML markers",      command=self.sel_xml).grid(row=2, column=0, columnspan=2, sticky="ew")
        Button(root, text="Carpeta imágenes", command=self.sel_imgs).grid(row=3, column=0, columnspan=2, sticky="ew")
        Button(root, text="Destino XML",      command=self.sel_dest).grid(row=4, column=0, columnspan=2, sticky="ew")
        Button(root, text="🔧 ARREGLAR FINAL", command=self.run, bg='#dc3545', fg='white').grid(row=5, column=0, columnspan=2, sticky="ew")
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
            out     = self.paths.get('dest') or 'ARREGLADO_FINAL.xml'
            exportar_xml(tl, self.paths['imgs'], out, fps)
            messagebox.showinfo('🔧 ARREGLADO!','Solo las pistas necesarias creadas!\n\nArchivo: {}'.format(out))
        except Exception as e:
            messagebox.showerror('❌ Error', str(e))

if __name__ == '__main__':
    root = Tk(); root.geometry('460x300')
    App(root)
    root.mainloop()