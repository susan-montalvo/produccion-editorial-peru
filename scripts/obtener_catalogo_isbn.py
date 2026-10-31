"""Descarga el catálogo público de la Agencia Peruana del ISBN (BNP).

El catálogo (https://isbn.bnp.gob.pe/catalogo.php) muestra 6 títulos por página y sus filtros no se combinan,
así que se recorre en tres pasos:

    totales  títulos por año de publicación               -> datos/originales/isbn_totales_anio.csv
    listado  todas las páginas del filtro "Publicación electrónica" -> datos/originales/isbn_digital_listado.csv
    fichas   la ficha de cada título digital (soporte, formato, precio, público, idioma)
                                                         -> datos/originales/isbn_digital_fichas.csv

Cada página queda en datos/cache/ (ignorada por git), así que una corrida interrumpida retoma donde quedó.
Se hacen pocas consultas en paralelo para no cargar el servidor de la BNP.

Uso:
    python scripts/obtener_catalogo_isbn.py totales
    python scripts/obtener_catalogo_isbn.py listado
    python scripts/obtener_catalogo_isbn.py fichas --desde 2015 --hasta 2025
"""

import argparse
import csv
import gzip
import html
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import requests
import truststore

# El servidor de la BNP no envía el certificado intermedio; el almacén del sistema operativo sí lo tiene
truststore.inject_into_ssl()

BASE = "https://isbn.bnp.gob.pe/catalogo.php"
RAIZ = Path(__file__).resolve().parents[1]
CACHE = RAIZ / "datos" / "cache"
ORIGINALES = RAIZ / "datos" / "originales"
HILOS = 3

sesion = requests.Session()
sesion.headers["User-Agent"] = "Mozilla/5.0 (proyecto academico; Python Intermedio, produccion editorial Peru)"


def bajar(params: dict, nombre: str) -> str:
    """Devuelve el HTML de la página, desde la caché si ya se bajó."""
    ruta = CACHE / f"{nombre}.html.gz"
    if ruta.exists():
        return gzip.decompress(ruta.read_bytes()).decode("latin-1")
    for intento in range(8):
        try:
            r = sesion.get(BASE, params=params, timeout=60)
            r.raise_for_status()
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_bytes(gzip.compress(r.content))
            return r.content.decode("latin-1")
        except requests.RequestException:
            time.sleep(min(2 ** intento, 60))
    # El servidor a veces se cae por minutos: se anota y se sigue; la próxima corrida lo reintenta
    print(f"  falló {params}")
    return ""


def limpiar(texto: str) -> str:
    texto = html.unescape(re.sub(r"<br\s*/?>", "; ", texto))
    texto = re.sub(r"<[^>]+>", "", texto)
    return re.sub(r"\s+", " ", texto).strip(" ;")


def total_resultados(pagina: str) -> int:
    return int(re.search(r"(\d+) resultados", pagina).group(1))


def totales():
    filas = []
    for anio in range(2008, date.today().year + 2):
        pagina = bajar({"mode": "busqueda_menu", "anio": anio}, f"anio/{anio}")
        filas.append({"anio": anio, "titulos": total_resultados(pagina)})
        print(anio, filas[-1]["titulos"])
    escribir(ORIGINALES / "isbn_totales_anio.csv", filas)


BLOQUE = re.compile(
    r'mode=detalle&nt=(\d+)"><img.*?<span class="isbn"><strong>ISBN </strong>([^<]*)</span>'
    r'.*?class="titulo"[^>]*>(.*?)</a></p>(.*?)<span class="textofecha">([^<]*)</span>',
    re.S,
)


def parsear_listado(pagina: str) -> list[dict]:
    filas = []
    for nt, isbn, titulo, medio, fecha in BLOQUE.findall(pagina):
        campos = dict(re.findall(r'<span class="labels" >([^<]+):</span><span class="texto">(.*?)</span>', medio))
        filas.append({
            "nt": int(nt),
            "isbn": isbn.strip(),
            "titulo": limpiar(titulo),
            "autor": limpiar(campos.get("Autor", "")),
            "editorial": limpiar(campos.get("Editorial", "")),
            "materia": limpiar(campos.get("Materia", "")),
            "publicado": fecha.strip(),
        })
    return filas


def listado():
    params = {"mode": "busqueda_menu", "formato": "digital"}
    primera = bajar({**params, "pagina": 1}, "digital/p00001")
    n_paginas = -(-total_resultados(primera) // 6)
    print(f"{total_resultados(primera)} títulos digitales en {n_paginas} páginas")
    filas = {}
    with ThreadPoolExecutor(HILOS) as ex:
        futuros = {ex.submit(bajar, {**params, "pagina": p}, f"digital/p{p:05d}"): p for p in range(1, n_paginas + 1)}
        for i, f in enumerate(as_completed(futuros), 1):
            for fila in parsear_listado(f.result()):
                filas[fila["nt"]] = fila
            if i % 200 == 0:
                print(f"  {i}/{n_paginas} páginas, {len(filas)} títulos")
    escribir(ORIGINALES / "isbn_digital_listado.csv", sorted(filas.values(), key=lambda x: x["nt"]))
    print(f"{len(filas)} títulos únicos")
    if len(filas) < total_resultados(primera):
        print(f"  aviso: faltan {total_resultados(primera) - len(filas)} títulos; vuelvan a correr este paso")


CAMPOS_FICHA = {
    "Público objetivo": "publico",
    "Número de edición": "edicion",
    "Tamaño": "tamano",
    "Precio": "precio",
    "Soporte": "soporte",
    "Formato": "formato",
    "Idioma": "idioma",
}


def parsear_ficha(nt: int, pagina: str) -> dict:
    fila = {"nt": nt}
    for etiqueta, valor in re.findall(r'<span class="labels" >([^<]+):</span>(.*?)(?=<span class="labels"|</div>)', pagina, re.S):
        clave = CAMPOS_FICHA.get(html.unescape(etiqueta).strip())
        if clave:
            fila[clave] = limpiar(valor)
    editor = re.search(r"id_editor=(\d+)", pagina)
    fila["id_editor"] = editor.group(1) if editor else ""
    return fila


def fichas(desde: int, hasta: int):
    with open(ORIGINALES / "isbn_digital_listado.csv", encoding="utf-8") as f:
        nts = [int(r["nt"]) for r in csv.DictReader(f) if desde <= int(r["publicado"][:4] or 0) <= hasta]
    print(f"{len(nts)} fichas de {desde} a {hasta}")
    filas = []
    with ThreadPoolExecutor(HILOS) as ex:
        futuros = {ex.submit(bajar, {"mode": "detalle", "nt": nt}, f"ficha/{nt}"): nt for nt in nts}
        for i, f in enumerate(as_completed(futuros), 1):
            if f.result():
                filas.append(parsear_ficha(futuros[f], f.result()))
            if i % 500 == 0:
                print(f"  {i}/{len(nts)} fichas")
    columnas = ["nt", "id_editor", *CAMPOS_FICHA.values()]
    escribir(ORIGINALES / "isbn_digital_fichas.csv", sorted(filas, key=lambda x: x["nt"]), columnas)


def escribir(ruta: Path, filas: list[dict], columnas=None):
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columnas or list(filas[0]), extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)
    print(f"-> {ruta.relative_to(RAIZ)}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("paso", choices=["totales", "listado", "fichas"])
    p.add_argument("--desde", type=int, default=2015)
    p.add_argument("--hasta", type=int, default=2025)
    a = p.parse_args()
    {"totales": totales, "listado": listado, "fichas": lambda: fichas(a.desde, a.hasta)}[a.paso]()
