# Adaptación del Script: De EDL a XML para Adobe Premiere Pro

## ✅ Cambios Realizados

### 1. **Función Principal**
- **Antes**: `exportar_edl()` - Generaba archivos EDL
- **Después**: `exportar_xml()` - Genera archivos XML compatibles con Adobe Premiere Pro

### 2. **Formato de Salida**
- **Antes**: Archivo `.edl` (Edit Decision List)
- **Después**: Archivo `.xml` (Final Cut Pro XML v1.2 compatible con Premiere)

### 3. **Estructura de Pistas**
- **EDL**: Una sola pista con clips secuenciales
- **XML**: Múltiples pistas de video (V1, V2, V3...) para apilar imágenes

### 4. **Asignación de Pistas**
- Cada imagen dentro de un bloque se asigna a una pista diferente
- **V1**: Primera imagen del bloque
- **V2**: Segunda imagen del bloque 
- **V3**: Tercera imagen del bloque
- Y así sucesivamente...

### 5. **Detección de Bloques**
- El script detecta automáticamente bloques analizando gaps > 1 segundo en el timeline
- Cada bloque agrupa imágenes que deben apilarse visualmente

## 📁 Archivos Creados

1. **`script_final.py`** - ✅ Versión final funcional
   - Genera XML compatible con Adobe Premiere Pro
   - GUI actualizada para trabajar con archivos XML
   - Etiquetas XML correctas (`<name>` en lugar de `<n>`)

2. **`script.py`** - ✅ Script original actualizado
   - Función EDL reemplazada por XML
   - GUI adaptada para XML

3. **`script_xml.py`** - Versión de desarrollo

## 🎯 Funcionalidad

### Entrada
- **Archivo SRT**: Subtítulos con tiempos
- **Archivo XML**: Markers que definen bloques
- **Carpeta PNG**: Imágenes numeradas (1.png, 2.png, etc.)
- **FPS**: Frames por segundo del proyecto

### Salida
- **Archivo XML**: Secuencia de Premiere Pro con:
  - Múltiples pistas de video
  - Imágenes apiladas por bloques
  - Tiempos exactos de inicio y duración
  - Metadatos completos de archivos

## 🚀 Uso

1. Ejecutar `python3 script_final.py`
2. Configurar FPS (por defecto 30)
3. Seleccionar archivo SRT
4. Seleccionar archivo XML de markers
5. Seleccionar carpeta de imágenes PNG
6. Elegir destino para el XML
7. Hacer clic en "Generar XML"
8. Importar el archivo XML en Adobe Premiere Pro

## ✨ Características

- **Múltiples pistas**: Cada imagen del bloque va en su propia pista
- **Tiempos precisos**: Mantiene sincronización exacta con subtítulos
- **Detección automática**: Identifica bloques sin configuración manual
- **Compatible 100%**: XML reconocido nativamente por Premiere Pro
- **Metadatos completos**: Incluye rutas de archivos, resolución, etc.

## 🔧 Estructura XML

El XML generado sigue el estándar Final Cut Pro XML v1.2:
- `<project>` - Contenedor principal
- `<sequence>` - Secuencia de timeline
- `<track>` - Pistas de video individuales
- `<clipitem>` - Clips individuales con metadatos
- `<file>` - Referencias a archivos de imagen

¡El script está listo para usar y generar XMLs compatibles con Adobe Premiere Pro!