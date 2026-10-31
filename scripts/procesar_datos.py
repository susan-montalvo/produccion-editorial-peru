"""Limpia y une las tres fuentes en tablas largas (datos/procesados/*.csv).

    InfoArtes / BNP   Registro ISBN 2008-2023, 12 tablas año x categoría
    UN Comtrade       comercio exterior del Perú en HS 4901 (libros), 4902 (diarios y revistas) y 4903 (álbumes infantiles)
    Catálogo ISBN BNP títulos por año (2008-2026) y fichas de las publicaciones electrónicas

Uso:  python scripts/procesar_datos.py
"""

import json
import re
from pathlib import Path

import pandas as pd
from babel import Locale

RAIZ = Path(__file__).resolve().parents[1]
ORIGINALES = RAIZ / "datos" / "originales"
PROCESADOS = RAIZ / "datos" / "procesados"

TABLAS_INFOARTES = {
    "Tabla 1": "ejemplares",
    "Tabla 2": "titulos",
    "Tabla 3": "soporte",
    "Tabla 4": "edicion",
    "Tabla 5": "comercializacion",
    "Tabla 6": "tiraje",
    "Tabla 7": "materia",
    "Tabla 8": "departamento",
    "Tabla 9": "agente",
    "Tabla 10": "idioma",
}

LENGUAS_ORIGINARIAS = {
    "Achuar", "Aimara", "Ashaninka", "Asheninka", "Awajún", "Bora", "Cashinahua", "Ikitu", "Matsigenka",
    "Murui-Muinani", "Nomatsigenga", "Quechua", "Shipibo-konibo", "Shiwilu", "Ticuna", "Uitoto", "Urarina",
    "Wampis", "Yanesha", "Yine",
}


def leer_tabla_infoartes(libro: pd.ExcelFile, hoja: str) -> pd.DataFrame:
    """Cada hoja trae el título arriba, una fila de años y una fila por categoría hasta la nota de fuente."""
    d = libro.parse(hoja, header=None)
    fila_anios = d.index[d.iloc[:, 2].astype(str).str.match(r"^20\d\d")][0]
    anios = d.loc[fila_anios, 2:].dropna().astype(float).astype(int).tolist()
    cuerpo = d.loc[fila_anios + 1:, 1:1 + len(anios)]
    cuerpo = cuerpo[cuerpo[1].notna() & ~cuerpo[1].astype(str).str.startswith("Fuente")]
    cuerpo.columns = ["categoria", *anios]
    largo = cuerpo.melt(id_vars="categoria", var_name="anio", value_name="valor")
    # "-" y ".-" son celdas sin registros
    largo["valor"] = pd.to_numeric(largo["valor"].astype(str).str.replace(r"^\.?-$", "0", regex=True), errors="raise")
    largo["categoria"] = largo["categoria"].astype(str).str.strip().str.replace("–", "-")
    largo["anio"] = largo["anio"].astype(int)
    return largo


def procesar_infoartes() -> dict[str, pd.DataFrame]:
    libro = pd.ExcelFile(ORIGINALES / "infoartes_registro_isbn_2008_2023.xlsx")
    tablas = {nombre: leer_tabla_infoartes(libro, hoja) for hoja, nombre in TABLAS_INFOARTES.items()}

    tablas["idioma"]["originaria"] = tablas["idioma"]["categoria"].isin(LENGUAS_ORIGINARIAS)
    tablas["materia"] = tablas["materia"][tablas["materia"]["categoria"] != "No registra"]

    # Control: las tablas desagregadas deben sumar el total de títulos de cada año
    total = tablas["titulos"].set_index("anio")["valor"]
    for nombre in ["soporte", "edicion", "comercializacion", "tiraje", "departamento", "agente", "idioma"]:
        suma = tablas[nombre].groupby("anio")["valor"].sum()
        dif = (suma - total).loc[lambda s: s != 0]
        if len(dif):
            print(f"  aviso: {nombre} no suma el total en {dict(dif)}")
    return tablas


# Nombres de babel que se acortan para leerlos mejor en el mapa y el ranking
NOMBRES_CORTOS = {"RAE de Hong Kong (China)": "Hong Kong (China)", "RAE de Macao (China)": "Macao (China)"}


def nombres_paises() -> pd.DataFrame:
    ref = json.load(open(ORIGINALES / "comtrade" / "partnerAreas.json"))["results"]
    es = Locale("es").territories
    filas = [{
        "codigo": r["PartnerCode"],
        "iso3": r.get("PartnerCodeIsoAlpha3") or "",
        "pais": es.get(r.get("PartnerCodeIsoAlpha2") or "", r["PartnerDesc"]),
    } for r in ref]
    d = pd.DataFrame(filas)
    d["pais"] = d["pais"].replace(NOMBRES_CORTOS)
    return d


PRODUCTOS = {"4901": "Libros y folletos", "4902": "Diarios y revistas", "4903": "Álbumes y libros infantiles"}


def procesar_comtrade() -> pd.DataFrame:
    filas = []
    for f in sorted((ORIGINALES / "comtrade").glob("ct_*.json")):
        filas += json.load(open(f))["data"]
    d = pd.DataFrame(filas)
    d = d.merge(nombres_paises(), left_on="partnerCode", right_on="codigo", how="left")
    d.loc[d["partnerCode"] == 0, "pais"] = "Mundo"
    if d["pais"].isna().any():
        print("  aviso: socios sin nombre", d.loc[d["pais"].isna(), "partnerCode"].unique())
    salida = pd.DataFrame({
        "anio": d["refYear"],
        "flujo": d["flowCode"].map({"M": "Importación", "X": "Exportación"}),
        "hs": d["cmdCode"],
        "producto": d["cmdCode"].map(PRODUCTOS),
        "pais": d["pais"],
        "iso3": d["iso3"].fillna(""),
        "usd": d["primaryValue"],
        "kg": d["netWgt"],
    })
    # Control: la suma de socios debe cuadrar con el total "Mundo" que reporta el Perú
    socios = salida[salida.pais != "Mundo"].groupby(["anio", "flujo", "hs"])["usd"].sum()
    mundo = salida[salida.pais == "Mundo"].set_index(["anio", "flujo", "hs"])["usd"]
    brecha = ((socios - mundo).abs() / mundo).loc[lambda s: s > 0.01]
    if len(brecha):
        print(f"  aviso: socios no cuadran con Mundo en {len(brecha)} casos")
    return salida.sort_values(["anio", "flujo", "hs", "usd"], ascending=[True, True, True, False])


# Valores del campo "Formato" de las fichas, agrupados. El orden importa: "Pdf/A" es PDF y
# "DAISY 2: texto completo y sin audio" no es audio.
FORMATOS = [
    ("Audiolibro", r"mp3|cd audio|wav|m4a|m4b|aac|ogg|flac|audiolibro"),
    ("PDF", r"pdf"),
    ("ePub y otros e-book", r"epub|opf|kindle|azw|ibook|reader|pdb|bbeb|mobi|exebook"),
    ("HTML", r"html"),
]


def tipo_formato(formato) -> str:
    if formato is None or pd.isna(formato) or not str(formato).strip():
        return "Sin dato"
    texto = str(formato).lower().replace("sin audio", "")
    for nombre, patron in FORMATOS:
        if re.search(patron, texto):
            return nombre
    return "Otros formatos"


def procesar_catalogo() -> dict[str, pd.DataFrame]:
    salida = {"catalogo_totales": pd.read_csv(ORIGINALES / "isbn_totales_anio.csv")}
    listado_csv, fichas_csv = ORIGINALES / "isbn_digital_listado.csv", ORIGINALES / "isbn_digital_fichas.csv"
    if not fichas_csv.exists():
        print("  falta isbn_digital_fichas.csv: corran obtener_catalogo_isbn.py fichas")
        return salida
    listado = pd.read_csv(listado_csv)
    fichas = pd.read_csv(fichas_csv)
    d = listado.merge(fichas, on="nt", how="inner")
    d["anio"] = pd.to_numeric(d["publicado"].str[:4], errors="coerce")
    d["tipo_formato"] = d["formato"].map(tipo_formato)
    salida["digital_titulos"] = d

    # Lista de audiolibros para análisis (no la usa el dashboard), con el enlace a su ficha en la BNP
    audio = d[(d["tipo_formato"] == "Audiolibro") & d["anio"].between(2015, 2025)].copy()
    audio["ficha_bnp"] = "https://isbn.bnp.gob.pe/catalogo.php?mode=detalle&nt=" + audio["nt"].astype(str)
    columnas = ["anio", "publicado", "isbn", "titulo", "autor", "editorial", "materia", "publico",
                "idioma", "edicion", "formato", "tamano", "precio", "ficha_bnp"]
    salida["audiolibros"] = audio.sort_values(["publicado", "titulo"], ascending=[False, True])[columnas]
    return salida


def main():
    PROCESADOS.mkdir(parents=True, exist_ok=True)
    print("InfoArtes")
    for nombre, tabla in procesar_infoartes().items():
        tabla.to_csv(PROCESADOS / f"isbn_{nombre}.csv", index=False)
    print("Comtrade")
    procesar_comtrade().to_csv(PROCESADOS / "comercio_exterior.csv", index=False)
    print("Catálogo ISBN")
    for nombre, tabla in procesar_catalogo().items():
        tabla.to_csv(PROCESADOS / f"{nombre}.csv", index=False)
    print("listo:", sorted(p.name for p in PROCESADOS.glob("*.csv")))


if __name__ == "__main__":
    main()
