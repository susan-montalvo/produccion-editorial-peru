"""Reel vertical 1080x1920: guion.json -> voz clonada -> video con gráficos, música y subtítulos.

Extiende reel_base.py (sesión 15 del curso) con:
    - una imagen por escena (capturas del dashboard), debajo de la cifra
    - música de fondo bajo la voz (composición propia generada aquí, o la pista que se indique)
    - créditos de datos, música y voz en el pie

Uso:
    python reel/hacer_reel.py --voz reel/mi_voz.m4a                 # voz clonada con Qwen3-TTS (CPU)
    python reel/hacer_reel.py --prueba                              # voz del sistema (macOS), solo para revisar el diseño
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import truststore
from PIL import Image, ImageDraw

# El Python de conda no trae certificados raíz; las fuentes se bajan de GitHub con los del sistema
truststore.inject_into_ssl()

AQUI = Path(__file__).parent
sys.path.insert(0, str(AQUI))
import reel_base as rb  # noqa: E402

ANCHO, ALTO, MARGEN = rb.ANCHO, rb.ALTO, rb.MARGEN
ZONA = (420, 1390)   # entre el aviso de IA y los subtítulos
Y_SUBTITULO, Y_PIE = 1450, 1620   # más abajo que en reel_base para que las capturas se vean grandes
VOLUMEN_MUSICA = 0.12


# Voz de prueba -------------------------------------------------------------------

class VozSistema:
    """Narra con la voz de macOS (`say`). Sirve para revisar ritmo y diseño; no clona ninguna voz."""

    def __init__(self, voz="Paulina"):
        self.voz, self.sr, self.texto_ref = voz, 22050, "(voz del sistema)"

    def decir(self, frases, estilos=None):
        wavs = []
        for f in frases:
            tmp = AQUI / "salidas" / "_say.aiff"
            subprocess.run(["say", "-v", self.voz, "-o", str(tmp), f], check=True)
            wavs.append(rb.cargar_audio(tmp, self.sr))
            tmp.unlink()
        return wavs


def acortar_silencios(w, sr, maximo=0.35, deja=0.2, umbral_db=-40, ventana=0.02):
    """La voz clonada a veces deja silencios largos dentro de una frase: los que pasan de `maximo` segundos
    se recortan a `deja` segundos. Silencio = ventanas de 20 ms con energía por debajo de `umbral_db` del pico."""
    w = np.asarray(w, np.float32)
    n = max(int(ventana * sr), 1)
    marcos = len(w) // n
    if marcos < 3:
        return w
    rms = np.sqrt(np.mean(w[: marcos * n].reshape(marcos, n) ** 2, axis=1))
    callado = 20 * np.log10(rms / (np.abs(w).max() + 1e-9) + 1e-9) < umbral_db
    partes, i = [], 0
    while i < marcos:
        j = i
        while j < marcos and callado[j] == callado[i]:
            j += 1
        tramo = w[i * n: j * n]
        # Solo se recortan los silencios internos (los del principio y el final los maneja reel_base)
        if callado[i] and 0 < i and j < marcos and (j - i) * ventana > maximo:
            mitad = int(deja * sr / 2)
            tramo = np.concatenate([tramo[:mitad], tramo[-mitad:]])
        partes.append(tramo)
        i = j
    partes.append(w[marcos * n:])
    return np.concatenate(partes)


class SinPausasLargas:
    """Envuelve una voz para acortar los silencios internos de cada frase que genera."""

    def __init__(self, voz):
        # Qwen3-TTS conoce su frecuencia de muestreo recién al generar la primera frase
        self.voz, self.sr, self.texto_ref = voz, getattr(voz, "sr", None), voz.texto_ref

    def decir(self, frases, estilos=None):
        wavs = self.voz.decir(frases, estilos)
        self.sr = self.voz.sr
        return [acortar_silencios(w, self.sr) for w in wavs]


# Subtítulos con cifras ----------------------------------------------------------
# La voz necesita los números escritos en palabras, pero en pantalla se leen mejor en cifras:
# "dos mil quince" → "2015", "diez mil trescientos cuarenta y cinco" → "10 345", "sesenta por ciento" → "60 %".

_UNIDADES = {"cero": 0, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
             "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
             "dieciséis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiuno": 21,
             "veintidós": 22, "veintitrés": 23, "veinticuatro": 24, "veinticinco": 25, "veintiséis": 26,
             "veintisiete": 27, "veintiocho": 28, "veintinueve": 29, "treinta": 30, "cuarenta": 40, "cincuenta": 50,
             "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90, "cien": 100, "ciento": 100,
             "doscientos": 200, "trescientos": 300, "cuatrocientos": 400, "quinientos": 500, "seiscientos": 600,
             "setecientos": 700, "ochocientos": 800, "novecientos": 900}
_SIGNOS = ".,;:?!"


def _limpia(p):
    return p.lower().rstrip(_SIGNOS)


def _es_numero(p):
    return _limpia(p) in _UNIDADES or _limpia(p) == "mil"


def _valor(palabras):
    total, actual = 0, 0
    for p in palabras:
        p = _limpia(p)
        if p == "y":
            continue
        if p == "mil":
            total += (actual or 1) * 1000
            actual = 0
        else:
            actual += _UNIDADES[p]
    return total + actual


def _cifra(n, es_anio):
    if es_anio or n < 10000:
        return str(n)
    return f"{n:,}".replace(",", " ")


def numeros_en_cifras(palabras):
    """Junta las palabras de un número (con sus tiempos) y las reemplaza por la cifra."""
    salida, i = [], 0
    while i < len(palabras):
        if not _es_numero(palabras[i][2]):
            salida.append(palabras[i])
            i += 1
            continue
        j = i
        # "y" solo une números ("cincuenta y nueve"); "dos" o "mil" seguidos de otro número continúan la cifra
        while j + 1 < len(palabras) and palabras[j][2][-1] not in _SIGNOS and (
                _es_numero(palabras[j + 1][2])
                or (_limpia(palabras[j + 1][2]) == "y" and j + 2 < len(palabras) and _es_numero(palabras[j + 2][2]))):
            j += 2 if _limpia(palabras[j + 1][2]) == "y" else 1
        grupo = palabras[i:j + 1]
        n = _valor([g[2] for g in grupo])
        es_anio = 1900 <= n <= 2100 and _limpia(grupo[0][2]) == "dos"
        texto, fin = _cifra(n, es_anio), grupo[-1][1]
        cola = grupo[-1][2][len(grupo[-1][2].rstrip(_SIGNOS)):]
        # "por ciento" pasa a "%"
        if (not cola and j + 2 < len(palabras) and _limpia(palabras[j + 1][2]) == "por"
                and _limpia(palabras[j + 2][2]) == "ciento"):
            texto, fin = texto + " %", palabras[j + 2][1]
            cola = palabras[j + 2][2][len("ciento"):] if palabras[j + 2][2].lower().startswith("ciento") else ""
            j += 2
        salida.append((grupo[0][0], fin, texto + cola))
        i = j + 1
    return salida


def limpiar_palabras(palabras, fin_audio):
    """Whisper a veces repite el final del audio con palabras de duración cero o una palabra idéntica muy breve
    pegada a la anterior: se descartan."""
    limpias = []
    for p in palabras:
        if p[1] - p[0] <= 0.01 or p[0] >= fin_audio:
            continue
        if limpias and p[2].lower() == limpias[-1][2].lower() and p[1] - p[0] < 0.15:
            continue
        limpias.append(p)
    return limpias


def referencia_normalizada(ruta, salidas):
    """Los MP3 decodificados pueden pasar de ±1 y Qwen3-TTS lo advierte: la referencia se lleva a −1 dBFS de pico."""
    audio = rb.cargar_audio(ruta, 24000)
    audio = audio / max(np.abs(audio).max(), 1e-6) * 0.89
    destino = Path(salidas) / "_referencia.wav"
    sf.write(destino, audio, 24000)
    return destino


# Música ----------------------------------------------------------------------------

def generar_musica(duracion, ruta, sr=44100, bpm=76):
    """Pista ambiental propia: acordes La m - Fa - Do - Sol con un arpegio suave. Se publica como CC0."""
    acordes = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]   # notas MIDI
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)
    compas = 4 * 60 / bpm
    n = int(duracion * sr)
    t = np.arange(n) / sr
    pista = np.zeros(n, np.float32)
    for k in range(int(duracion / compas) + 1):
        acorde = acordes[k % len(acordes)]
        ini, fin = int(k * compas * sr), min(n, int((k + 1) * compas * sr))
        if ini >= n:
            break
        tt = t[ini:fin] - t[ini]
        env = np.minimum(1, tt / 0.8) * np.minimum(1, (compas - tt) / 0.8)   # entrada y salida suaves
        for nota in acorde:
            f = hz(nota)
            pista[ini:fin] += env * (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * f * 1.003 * tt)) * 0.12
        pista[ini:fin] += env * np.sin(2 * np.pi * hz(acorde[0] - 12) * tt) * 0.10   # bajo
        for j, nota in enumerate(acorde + [acorde[1] + 12]):   # arpegio de corcheas
            for rep in range(2):
                a = ini + int((j + 4 * rep) * compas / 8 * sr)
                if a >= fin:
                    continue
                ta = t[a:fin] - t[a]
                pista[a:fin] += np.exp(-ta * 5) * np.sin(2 * np.pi * hz(nota + 12) * ta) * 0.07
    pista *= np.minimum(1, t / 2) * np.minimum(1, (duracion - t) / 3)
    pista /= np.abs(pista).max() * 1.1
    sf.write(ruta, np.stack([pista, pista], 1), sr)
    return ruta


# Video -----------------------------------------------------------------------------

def base(titulo, fuente_datos, autor, credito_musica):
    """Como reel_base._base, con el pie más abajo y el crédito de la música."""
    img = Image.new("RGB", (ANCHO, ALTO), rb.FONDO)
    d = ImageDraw.Draw(img)
    d.text((MARGEN, 250), titulo.upper(), font=rb._fuente("PublicSans", 40, 800), fill=rb.ACENTO)
    aviso = "VOZ GENERADA CON IA"
    f = rb._fuente("PublicSans", 28, 700)
    x1 = MARGEN + d.textlength(aviso, font=f) + 36
    d.rounded_rectangle((MARGEN, 315, x1, 365), radius=25, outline=rb.SUAVE, width=2)
    d.text((MARGEN + 18, 340), aviso, font=f, fill=rb.SUAVE, anchor="lm")
    pie = rb._fuente("PublicSans", 30, 500)
    y = Y_PIE
    for linea in rb._envolver(d, f"Autora: {autor} · Fuente: {fuente_datos}", pie, ANCHO - 2 * MARGEN):
        d.text((MARGEN, y), linea, font=pie, fill=rb.SUAVE)
        y += 42
    if credito_musica:
        d.text((MARGEN, y + 6), f"Música: {credito_musica}", font=rb._fuente("PublicSans", 26, 500), fill=rb.SUAVE)
    return img


def cuadro(fondo, capas, narracion, t, bloques, fuente_sub):
    """Como reel_base._cuadro, con los subtítulos en Y_SUBTITULO."""
    img = fondo.copy()
    i = max([k for k, (ini, _) in enumerate(narracion.escenas) if ini - rb.PAUSA <= t] or [0])
    a = min(1.0, max(0.0, (t - narracion.escenas[i][0] + rb.PAUSA) / 0.35))
    capa = capas[i]
    if a < 1:
        capa = capa.copy()
        capa.putalpha(capa.getchannel("A").point(lambda v: int(v * a)))
    img.paste(capa, (0, int(40 * (1 - a))), capa)

    d = ImageDraw.Draw(img)
    d.rounded_rectangle((MARGEN, 180, ANCHO - MARGEN, 188), radius=4, fill=rb.CAJA)
    d.rounded_rectangle((MARGEN, 180, MARGEN + (ANCHO - 2 * MARGEN) * t / narracion.duracion, 188), radius=4, fill=rb.ACENTO)

    b = next((b for b in bloques if b[0][0] - 0.1 <= t <= b[-1][1] + 0.25), None)
    if b:
        texto = " ".join(p[2] for p in b)
        w = d.textlength(texto, font=fuente_sub)
        x, y = (ANCHO - w) / 2, Y_SUBTITULO
        d.rounded_rectangle((x - 36, y - 26, x + w + 36, y + fuente_sub.size + 34), radius=28, fill=rb.CAJA)
        for ini, fin, palabra in b:
            d.text((x, y), palabra, font=fuente_sub, fill=rb.ACENTO if ini <= t <= fin + 0.05 else rb.TEXTO)
            x += d.textlength(palabra + " ", font=fuente_sub)
    return img


def escena(e):
    """La cifra y su etiqueta arriba; la captura del dashboard debajo, centrada en lo que queda de la zona."""
    capa = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    ancho = ANCHO - 2 * MARGEN
    y = ZONA[0]
    if e.get("cifra"):
        f = rb._ajustar(d, e["cifra"], "Oswald", 700, ancho, 170)
        y += -d.textbbox((0, 0), e["cifra"], font=f, anchor="ls")[1]
        d.text((MARGEN, y), e["cifra"], font=f, fill=rb.TEXTO, anchor="ls")
        y += 30
        fe, color = rb._fuente("PublicSans", 44, 600), rb.SUAVE
    else:
        fe, color = rb._fuente("Oswald", 84, 600), rb.TEXTO
    for linea in rb._envolver(d, e["etiqueta"], fe, ancho):
        y += fe.size
        d.text((MARGEN, y), linea, font=fe, fill=color, anchor="ls")
        y += int(fe.size * 0.3)

    if e.get("imagen"):
        img = Image.open(AQUI / e["imagen"]).convert("RGBA")
        alto_libre = ZONA[1] - (y + 30)
        escala = min(ancho / img.width, alto_libre / img.height)
        img = img.resize((int(img.width * escala), int(img.height * escala)), Image.LANCZOS)
        mascara = Image.new("L", img.size, 0)
        ImageDraw.Draw(mascara).rounded_rectangle((0, 0, *img.size), radius=24, fill=255)
        x0 = (ANCHO - img.width) // 2
        y0 = y + 30 + (alto_libre - img.height) // 2
        capa.paste(img, (x0, y0), mascara)
    return capa


def video(guion, narracion, ruta, fuente_datos, autor, musica, credito_musica):
    ruta = Path(ruta)
    wav = ruta.with_suffix(".wav")
    sf.write(wav, narracion.audio, narracion.sr)
    fondo = base(guion["titulo"], fuente_datos, autor, credito_musica)
    capas = [escena(e) for e in guion["escenas"]]
    bloques = rb._bloques(narracion.palabras)
    fuente_sub = rb._fuente("PublicSans", 62, 800)
    dur = narracion.duracion
    # Voz normalizada a -14 LUFS; la música va muy por debajo y se desvanece al final
    filtro = "[1:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]"
    entrada_musica = []
    if musica:
        filtro = (f"[1:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[v];"
                  f"[2:a]volume={VOLUMEN_MUSICA},afade=t=in:d=1.5,afade=t=out:st={max(dur - 2.5, 0):.2f}:d=2.5,aresample=48000[m];"
                  f"[v][m]amix=inputs=2:duration=first:normalize=0[a]")
        entrada_musica = ["-stream_loop", "-1", "-i", str(musica)]
    cmd = [rb.FFMPEG, "-y", "-v", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{ANCHO}x{ALTO}", "-r", str(rb.FPS), "-i", "-",
           "-i", str(wav), *entrada_musica,
           "-filter_complex", filtro, "-map", "0:v", "-map", "[a]",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-t", f"{dur:.2f}", "-movflags", "+faststart", str(ruta)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for k in range(int(dur * rb.FPS)):
        proc.stdin.write(cuadro(fondo, capas, narracion, k / rb.FPS, bloques, fuente_sub).tobytes())
    proc.stdin.close()
    proc.wait()
    return ruta


def portada(guion, narracion, ruta, fuente_datos, autor, credito_musica, escena_n=1):
    t = narracion.escenas[escena_n][0] + 1.0
    img = cuadro(base(guion["titulo"], fuente_datos, autor, credito_musica), [escena(e) for e in guion["escenas"]],
                     narracion, t, rb._bloques(narracion.palabras), rb._fuente("PublicSans", 62, 800))
    img.save(ruta)
    return ruta


def rehacer_escenas(a, guion, salidas, tiempos, t0):
    """Narra de nuevo solo las escenas indicadas y las reemplaza en la narración guardada (salidas/reel.wav)."""
    audio, sr = sf.read(salidas / "reel.wav", dtype="float32")
    escenas = [tuple(x) for x in json.loads(tiempos.read_text())]
    voz = SinPausasLargas(rb.Voz(referencia_normalizada(a.voz, salidas), modelo=a.tts, device=a.device))
    rb._reloj(f"voz lista; se rehacen las escenas {a.rehacer_escena}", t0)
    indices = [n - 1 for n in a.rehacer_escena]
    nuevas = voz.decir([guion["escenas"][i]["frase"] for i in indices])
    nuevas = {i: rb._acelerar(w, voz.sr, a.velocidad) if a.velocidad != 1 else np.asarray(w, np.float32)
              for i, w in zip(indices, nuevas)}
    if voz.sr != sr:
        raise SystemExit(f"la frecuencia de la voz ({voz.sr}) no coincide con la de reel.wav ({sr})")
    # Se arma de nuevo el audio con las mismas pausas que usa reel_base.narrar
    partes, nuevas_escenas, t = [np.zeros(int(rb.INICIO * sr), np.float32)], [], rb.INICIO
    for i, (ini, fin) in enumerate(escenas):
        w = nuevas.get(i, audio[int(ini * sr):int(fin * sr)])
        if i in nuevas:
            guion["escenas"][i]["wer"] = rb._wer(guion["escenas"][i]["frase"], rb._a16k(w, sr))
        nuevas_escenas.append((t, t + len(w) / sr))
        partes += [w, np.zeros(int(rb.PAUSA * sr), np.float32)]
        t += len(w) / sr + rb.PAUSA
    partes.append(np.zeros(int(rb.FINAL * sr), np.float32))
    narracion = rb.Narracion(np.concatenate(partes), sr, nuevas_escenas)
    sf.write(salidas / "reel.wav", narracion.audio, sr)
    tiempos.write_text(json.dumps(narracion.escenas))
    (AQUI / "guion.json").write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")
    rb._reloj(f"narración: {narracion.duracion:.1f} s; WER de las escenas rehechas: "
              + ", ".join(f"{n}: {guion['escenas'][n - 1]['wer']:.2f}" for n in a.rehacer_escena), t0)
    return narracion


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--voz", help="15 a 25 s de tu voz: m4a, opus, ogg o wav")
    p.add_argument("--prueba", action="store_true", help="narra con la voz del sistema para revisar el diseño")
    p.add_argument("--autor", default="Susan Montalvo")
    p.add_argument("--fuente", default="BNP (Agencia Peruana del ISBN), Ministerio de Cultura (InfoArtes), UN Comtrade")
    p.add_argument("--musica", help="pista propia; si no se indica, se genera una (CC0)")
    p.add_argument("--credito-musica", default="composición propia generada con Python (CC0)")
    p.add_argument("--sin-musica", action="store_true", help="solo la voz, sin pista ni crédito de música")
    p.add_argument("--tts", default="Qwen/Qwen3-TTS-12Hz-0.6B-Base")
    p.add_argument("--device", default="cpu")
    p.add_argument("--velocidad", type=float, default=1.0)
    p.add_argument("--salidas", default=str(AQUI / "salidas"))
    p.add_argument("--rehacer-escena", type=int, nargs="+", metavar="N",
                   help="vuelve a narrar solo esas escenas (1 = la primera) y las empalma en salidas/reel.wav; requiere --voz")
    p.add_argument("--reusar-audio", action="store_true",
                   help="rehace subtítulos y video con la narración de salidas/reel.wav, sin volver a generar la voz")
    a = p.parse_args()
    if not a.voz and not a.prueba and not a.reusar_audio:
        p.error("indiquen --voz, --prueba o --reusar-audio")

    t0 = time.time()
    salidas = Path(a.salidas)
    salidas.mkdir(exist_ok=True)
    guion = json.loads((AQUI / "guion.json").read_text())

    tiempos = salidas / "reel_escenas.json"   # inicio y fin de cada escena, para poder reutilizar la narración
    if a.rehacer_escena:
        narracion = rehacer_escenas(a, guion, salidas, tiempos, t0)
    elif a.reusar_audio:
        audio, sr = sf.read(salidas / "reel.wav", dtype="float32")
        narracion = rb.Narracion(audio, sr, [tuple(x) for x in json.loads(tiempos.read_text())])
        rb._reloj(f"narración reutilizada: {narracion.duracion:.1f} s", t0)
    else:
        voz = VozSistema() if a.prueba else rb.Voz(referencia_normalizada(a.voz, salidas), modelo=a.tts, device=a.device)
        voz = SinPausasLargas(voz)
        rb._reloj(f"voz lista; referencia: «{voz.texto_ref}»", t0)
        narracion = rb.narrar(voz, guion, velocidad=a.velocidad)
        rb._reloj(f"narración: {narracion.duracion:.1f} s; WER por escena: "
                  + ", ".join(f"{e['wer']:.2f}" for e in guion["escenas"]), t0)
        if not a.prueba:
            (AQUI / "guion.json").write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")
            tiempos.write_text(json.dumps(narracion.escenas))

    rb.subtitulos(narracion, guion)
    narracion.palabras = numeros_en_cifras(limpiar_palabras(narracion.palabras, narracion.duracion))
    rb.a_srt(narracion, AQUI / "subtitulos.srt" if not a.prueba else salidas / "prueba.srt")
    rb._reloj(f"subtítulos: {len(narracion.palabras)} palabras", t0)

    if a.sin_musica:
        musica, a.credito_musica = None, None
    else:
        musica = Path(a.musica) if a.musica else generar_musica(narracion.duracion + 1, AQUI / "recursos" / "musica.wav")
    nombre = "prueba" if a.prueba else "reel"
    portada(guion, narracion, salidas / f"{nombre}_portada.png", a.fuente, a.autor, a.credito_musica)
    video(guion, narracion, salidas / f"{nombre}.mp4", a.fuente, a.autor, musica, a.credito_musica)
    rb._reloj(f"listo: {salidas / (nombre + '.mp4')} ({narracion.duracion:.1f} s)", t0)


if __name__ == "__main__":
    main()
