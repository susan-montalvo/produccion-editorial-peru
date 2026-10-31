"""Capturas del dashboard para el reel (tema oscuro) y para LinkedIn y el README (tema claro).

Necesita el dashboard servido en local y Google Chrome instalado:
    cd web && python -m http.server 8765
    python scripts/capturas_dashboard.py --chrome "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
"""

import argparse
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

RAIZ = Path(__file__).resolve().parents[1]

# Tarjeta del dashboard (por el id de su gráfico) -> archivo; el reel usa una por escena
REEL = {
    "g-titulos": "titulos.png",
    "g-tiraje-prom": "tiraje_promedio.png",
    "g-tiraje": "tiraje_rangos.png",
    "g-mapa": "mapa_departamentos.png",
    "g-formatos": "formatos_digitales.png",
    "g-soporte": "soporte.png",
    "g-mundo": "mapa_mundo.png",
    "g-comercio": "comercio.png",
}
# En el mapa del reel se destacan las regiones que nombra la narración (escena de descentralización)
DESTACAR = ["Puno", "La Libertad", "Arequipa"]
# Desplazamiento de cada etiqueta (grados de longitud y latitud) para dejarla fuera del mapa, sobre el mar o el borde
DESPLAZAR = {"Puno": [2.6, 0.4], "La Libertad": [-3.6, 0.2], "Arequipa": [-3.0, -1.4]}
JS_DESTACAR = """([nombres, desplazar]) => {
  const claves = nombres.map((n) => D.produccion.departamento[n].clave);
  // Centro aproximado de cada departamento: promedio de los vértices de su polígono más grande
  const centro = (clave) => {
    const f = GEO_PERU.features.find((x) => x.properties.NOMBDEP === clave);
    const anillos = f.geometry.type === "Polygon" ? [f.geometry.coordinates[0]] : f.geometry.coordinates.map((p) => p[0]);
    const r = anillos.sort((a, b) => b.length - a.length)[0];
    return [r.reduce((s, c) => s + c[0], 0) / r.length, r.reduce((s, c) => s + c[1], 0) / r.length];
  };
  const c = claves.map(centro).map(([x, y], i) => [x + desplazar[nombres[i]][0], y + desplazar[nombres[i]][1]]);
  const ambar = css("--s4");
  Plotly.addTraces("g-mapa", [
    { type: "choropleth", geojson: GEO_PERU, featureidkey: "properties.NOMBDEP", locations: claves, z: claves.map(() => 0),
      showscale: false, hoverinfo: "skip", colorscale: [[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
      marker: { line: { color: ambar, width: 3.5 } } },
    { type: "scattergeo", lon: c.map((x) => x[0]), lat: c.map((x) => x[1]), mode: "text", text: nombres.map((n) => "<b>" + n + "</b>"),
      textfont: { color: css("--tinta"), size: 15 }, hoverinfo: "skip", showlegend: false },
  ]);
}"""

# Secciones completas para la publicación de LinkedIn y el README
SECCIONES = {
    "#resumen": "01_kpis.png",
    "#produccion": "02_produccion.png",
    "#territorio": "03_territorio.png",
    "#circulacion": "04_circulacion.png",
}


async def capturar(url: str, chrome: str):
    async with async_playwright() as p:
        nav = await p.chromium.launch(executable_path=chrome)

        # Ancho angosto: las tarjetas van a una columna y salen más altas y legibles en el video vertical
        oscuro = await nav.new_page(viewport={"width": 640, "height": 1000}, device_scale_factor=2, color_scheme="dark")
        await oscuro.goto(url, wait_until="networkidle")
        # El dashboard publicado es siempre claro; el tema oscuro se activa solo para estas capturas y se redibuja
        await oscuro.wait_for_selector("#g-titulos g.xtick text")
        await oscuro.evaluate("document.documentElement.dataset.theme = 'dark'; renderTodo()")
        # En el video sobran los controles y las notas: queda el título y el gráfico
        await oscuro.add_style_tag(content=".tarjeta label.control, .ver-tabla, .tarjeta .pie, .anio-mapa { display: none !important; }"
                                   # En el video vertical la lista de países va debajo del mapa mundial
                                   " .mapa-con-lista { grid-template-columns: 1fr !important; }")
        await oscuro.evaluate("window.dispatchEvent(new Event('resize'))")
        await oscuro.wait_for_timeout(2500)
        destino = RAIZ / "reel" / "recursos"
        destino.mkdir(parents=True, exist_ok=True)
        for id_grafico, archivo in REEL.items():
            tarjeta = oscuro.locator(f".tarjeta:has(#{id_grafico})")
            await tarjeta.scroll_into_view_if_needed()
            if id_grafico == "g-mapa":
                await oscuro.evaluate(JS_DESTACAR, [DESTACAR, DESPLAZAR])
            await oscuro.wait_for_timeout(300)
            await tarjeta.screenshot(path=destino / archivo)
            print("->", (destino / archivo).relative_to(RAIZ))
        # La portada se captura en ancho de escritorio, con los indicadores en dos filas de tres
        await oscuro.set_viewport_size({"width": 1000, "height": 1000})
        await oscuro.evaluate("window.scrollTo(0, 0)")
        await oscuro.wait_for_timeout(1500)
        await oscuro.screenshot(path=destino / "portada_dashboard.png")

        claro = await nav.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=2, color_scheme="light")
        await claro.goto(url, wait_until="networkidle")
        await claro.wait_for_timeout(2500)
        destino = RAIZ / "docs" / "capturas"
        destino.mkdir(parents=True, exist_ok=True)
        # La barra fija taparía el borde superior de cada sección
        await claro.add_style_tag(content=".barra { position: static !important; }")
        for selector, archivo in SECCIONES.items():
            seccion = claro.locator(selector)
            await seccion.scroll_into_view_if_needed()
            await claro.wait_for_timeout(300)
            await seccion.screenshot(path=destino / archivo)
            print("->", (destino / archivo).relative_to(RAIZ))
        await nav.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://localhost:8765/")
    p.add_argument("--chrome", default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    a = p.parse_args()
    asyncio.run(capturar(a.url, a.chrome))
