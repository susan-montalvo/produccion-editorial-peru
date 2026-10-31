"""Construye los indicadores y hallazgos, y escribe web/data/datos.json para el dashboard.

Uso:  python scripts/analizar_datos.py
"""

import json
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
PROCESADOS = RAIZ / "datos" / "procesados"
WEB = RAIZ / "web" / "data"

AGENTES = {
    "Editorial": "Editoriales",
    "Editorial universitaria o universidad": "Universidades",
    "Editor - Autor": "Autopublicación (autor-editor)",
}
# Periodo de análisis: los últimos diez años. Las fuentes traen datos desde 2008, pero el dashboard parte de 2015
DESDE = 2015

TIRAJES = [("Hasta 500", ["0-500"]), ("501 a 1 000", ["501-1000"]), ("1 001 a 3 000", ["1001-1500", "1501-2000", "2001-2500", "2501-3000"])]


def leer(nombre: str) -> pd.DataFrame:
    return pd.read_csv(PROCESADOS / f"{nombre}.csv")


def serie(df: pd.DataFrame, col="valor") -> dict:
    df = df[df["anio"] >= DESDE]
    return {int(k): round(float(v), 4) for k, v in df.set_index("anio")[col].items()}


def por_categoria(df: pd.DataFrame) -> dict:
    return {c: serie(g) for c, g in df.groupby("categoria")}


def sin_tildes(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().upper()


def produccion() -> dict:
    agente = leer("isbn_agente")
    agente["grupo"] = agente["categoria"].map(AGENTES).fillna("Otras entidades")
    agente = agente.groupby(["anio", "grupo"], as_index=False)["valor"].sum().rename(columns={"grupo": "categoria"})

    tiraje = leer("isbn_tiraje")
    grupo = {orig: nuevo for nuevo, origs in TIRAJES for orig in origs}
    tiraje["categoria"] = tiraje["categoria"].map(grupo).fillna("Más de 3 000")
    tiraje = tiraje.groupby(["anio", "categoria"], as_index=False)["valor"].sum()

    depto = leer("isbn_departamento")
    depto["clave"] = depto["categoria"].map(sin_tildes)

    idioma = leer("isbn_idioma")
    originarias = idioma[idioma["originaria"]]

    return {
        "titulos": serie(leer("isbn_titulos")),
        "ejemplares": serie(leer("isbn_ejemplares")),
        "soporte": por_categoria(leer("isbn_soporte")),
        "agente": por_categoria(agente),
        "tiraje": por_categoria(tiraje),
        "tiraje_orden": [t for t, _ in TIRAJES] + ["Más de 3 000"],
        "comercializacion": por_categoria(leer("isbn_comercializacion")),
        "materia": por_categoria(leer("isbn_materia")),
        "departamento": {c: {"clave": g["clave"].iat[0], "serie": serie(g)} for c, g in depto.groupby("categoria")},
        "lenguas_originarias": por_categoria(originarias),
    }


def catalogo() -> dict:
    totales = leer("catalogo_totales").rename(columns={"titulos": "valor"})
    salida = {"titulos": serie(totales[totales["anio"].between(DESDE, date.today().year - 1)])}
    ruta = PROCESADOS / "digital_titulos.csv"
    if not ruta.exists():
        return salida
    d = pd.read_csv(ruta)
    d = d[d["anio"].between(DESDE, date.today().year - 1)]
    formatos = d.groupby(["anio", "tipo_formato"]).size().rename("valor").reset_index()
    salida["digital_formato"] = {c: serie(g) for c, g in formatos.groupby("tipo_formato")}
    salida["digital_total"] = serie(d.groupby("anio").size().rename("valor").reset_index())
    audio = d[d["tipo_formato"] == "Audiolibro"].sort_values("publicado", ascending=False)
    columnas = ["isbn", "titulo", "autor", "editorial", "materia", "publico", "publicado", "formato"]
    salida["audiolibros"] = audio[columnas].fillna("").to_dict("records")
    return salida


def comercio() -> dict:
    c = leer("comercio_exterior")
    mundo = c[c["pais"] == "Mundo"]
    socios = c[(c["pais"] != "Mundo") & (c["usd"] > 0)]
    return {
        "mundo": {f"{hs}|{flujo}": serie(g, "usd") for (hs, flujo), g in mundo.groupby(["hs", "flujo"])},
        "productos": {"4901": "Libros y folletos", "4902": "Diarios y revistas", "4903": "Álbumes y libros infantiles"},
        "socios": socios[["anio", "flujo", "hs", "pais", "iso3", "usd"]].round({"usd": 0}).to_dict("records"),
    }


def hallazgos(p: dict, cat: dict, com: dict) -> list[dict]:
    """Las cifras de los cuatro hallazgos, calculadas aquí para que el texto del dashboard no las copie a mano."""
    a, b = 2015, 2023
    t, e = p["titulos"], p["ejemplares"]
    tiraje_a, tiraje_b = e[a] / t[a], e[b] / t[b]
    chico = p["tiraje"]["Hasta 500"]
    # Rangos originales de InfoArtes: títulos de más de 5 000 ejemplares y rango donde cae la mediana de cada año
    rangos = leer("isbn_tiraje").pivot(index="anio", columns="categoria", values="valor")
    orden = sorted(rangos.columns, key=lambda c: 10**6 if c.startswith(">") else int(c.split("-")[0]))
    acum = rangos[orden].cumsum(axis=1).div(rangos.sum(axis=1), axis=0)
    mediana = {int(y): fila[fila >= 0.5].index[0] for y, fila in acum.iterrows()}
    grande = rangos["> a 5001"] / rangos.sum(axis=1) * 100

    lima = p["departamento"]["Lima"]["serie"]
    fuera = {y: sum(d["serie"][y] for k, d in p["departamento"].items() if k != "Lima") for y in (a, b)}
    autor = p["agente"]["Autopublicación (autor-editor)"]

    exp = com["mundo"]["4901|Exportación"]
    imp = com["mundo"]["4901|Importación"]
    ultimo = max(exp)

    # Digital y audio con el catálogo, que llega hasta el último año completo
    tc, dc = cat["titulos"], cat["digital_total"]
    uc = max(dc)
    audio = pd.DataFrame(cat["audiolibros"])
    audio["anio"] = audio["publicado"].str[:4].astype(int)
    audio = audio[audio["anio"].between(a, uc)]
    total_periodo = sum(tc[y] for y in range(a, uc + 1))
    digital_periodo = sum(dc.get(y, 0) for y in range(a, uc + 1))
    por_editorial = audio["editorial"].value_counts()
    pico = audio["anio"].value_counts().idxmax()
    pdf = cat["digital_formato"]["PDF"]

    return [
        {
            "titulo": "Se publican más títulos, pero en tirajes mucho más cortos",
            "cifras": {
                "titulos_a": t[a], "titulos_b": t[b], "var_titulos": (t[b] / t[a] - 1) * 100,
                "ejemplares_a": e[a], "ejemplares_b": e[b], "var_ejemplares": (e[b] / e[a] - 1) * 100,
                "tiraje_a": tiraje_a, "tiraje_b": tiraje_b,
                "chico_a": chico[a] / t[a] * 100, "chico_b": chico[b] / t[b] * 100,
                "grande_a": grande[a], "grande_b": grande[b],
                "mediana_2019": mediana[2019], "mediana_2020": mediana[2020],
                "catalogo_ultimo": cat["titulos"][max(cat["titulos"])], "anio_ultimo": max(cat["titulos"]),
            },
        },
        {
            "titulo": "Lo digital llegó para quedarse; el audiolibro sigue siendo marginal",
            "cifras": {
                "dig_a": dc[a] / tc[a] * 100, "dig_2020": dc[2020] / tc[2020] * 100, "dig_u": dc[uc] / tc[uc] * 100, "anio_u": uc,
                "pdf_a": pdf[a] / dc[a] * 100, "pdf_u": pdf[uc] / dc[uc] * 100,
                "audio_n": len(audio), "audio_de_cada": total_periodo / len(audio),
                "audio_pct_digital": len(audio) / digital_periodo * 100,
                "audio_top5": por_editorial.head(5).sum() / len(audio) * 100,
                "audio_infantil": (audio["publico"] == "Infantil / Juvenil").mean() * 100,
                "audio_pico_anio": int(pico), "audio_pico_n": int((audio["anio"] == pico).sum()),
            },
        },
        {
            "titulo": "La producción se descentraliza y crece la autopublicación",
            "cifras": {
                "fuera_a": fuera[a], "fuera_b": fuera[b], "var_fuera": (fuera[b] / fuera[a] - 1) * 100,
                "lima_a": lima[a] / t[a] * 100, "lima_b": lima[b] / t[b] * 100,
                "autor_a": autor[a] / t[a] * 100, "autor_b": autor[b] / t[b] * 100,
            },
        },
        {
            "titulo": "El Perú compra libros afuera y vende cada vez menos",
            "cifras": {
                "exp_a": exp[a], "exp_b": exp[ultimo], "var_exp": (exp[ultimo] / exp[a] - 1) * 100,
                "imp_a": imp[a], "imp_b": imp[ultimo], "ratio": imp[ultimo] / exp[ultimo], "anio_ultimo": ultimo,
            },
        },
    ]


def main():
    p, cat, com = produccion(), catalogo(), comercio()
    datos = {
        "generado": date.today().isoformat(),
        "produccion": p,
        "catalogo": cat,
        "comercio": com,
        "hallazgos": hallazgos(p, cat, com),
    }
    WEB.mkdir(parents=True, exist_ok=True)
    (WEB / "datos.json").write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for h in datos["hallazgos"]:
        print(h["titulo"])
        print("  ", {k: round(v, 1) if isinstance(v, float) else v for k, v in h["cifras"].items()})
    print(f"-> web/data/datos.json ({(WEB / 'datos.json').stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
