# Diccionario de datos

Cada archivo viene de **una sola fuente**. Las fuentes solo se juntan en `web/data/datos.json`, y ningún indicador divide cifras de una fuente entre cifras de otra.

| Código | Fuente | Enlace | Descargado |
|---|---|---|---|
| **INFOARTES** | Ministerio de Cultura, InfoArtes: Registro ISBN 2008–2023 (datos de la BNP – Agencia Peruana del ISBN). Cuenta por **año de registro**. | https://infoartes.pe/posts/registro-isbn-2008-2023 | 29/10/2026 |
| **CATÁLOGO BNP** | Biblioteca Nacional del Perú, catálogo público del ISBN, extraído con `scripts/obtener_catalogo_isbn.py`. Cuenta por **fecha de publicación declarada**. | https://isbn.bnp.gob.pe/catalogo.php | 29/10/2026 |
| **COMTRADE** | Naciones Unidas, UN Comtrade (API pública), Perú como país que reporta. Valores en US$ corrientes. | https://comtradeplus.un.org/ | 29/10/2026 |

> Ojo con el prefijo `isbn_`: en `originales/` lo llevan los archivos del **catálogo BNP**, y en `procesados/` las tablas de **InfoArtes**.

## originales/ (tal como se descargaron)

| Archivo | Fuente | Filas | Contenido |
|---|---|---|---|
| `infoartes_registro_isbn_2008_2023.xlsx` | INFOARTES | 10 tablas | Títulos, ejemplares, soporte, edición, comercialización, tiraje, materia, departamento, tipo de editor e idioma por año |
| `isbn_totales_anio.csv` | CATÁLOGO BNP | 20 | `anio`, `titulos`: todos los títulos con ISBN por año, impresos y digitales (2008–2027; 2026 es parcial y 2027 son fechas anunciadas) |
| `isbn_digital_listado.csv` | CATÁLOGO BNP | 20 048 | Todas las publicaciones electrónicas: `nt` (id interno de la BNP), `isbn`, `titulo`, `autor`, `editorial`, `materia`, `publicado` |
| `isbn_digital_fichas.csv` | CATÁLOGO BNP | 16 142 | Ficha de cada publicación electrónica de 2015–2025: `nt`, `id_editor`, `publico`, `edicion`, `tamano`, `precio`, `soporte`, `formato`, `idioma` |
| `comtrade/ct_<hs>_<año>.json` | COMTRADE | 33 archivos | Respuesta de la API por producto (HS 4901, 4902, 4903) y año (2015–2025) |
| `comtrade/partnerAreas.json` | COMTRADE | – | Catálogo de países socios (código M49 → ISO3) |

## procesados/ (generados por `scripts/procesar_datos.py`)

| Archivo | Fuente | Viene de | Columnas |
|---|---|---|---|
| `isbn_titulos.csv` | INFOARTES | tabla de títulos | `categoria`, `anio`, `valor` |
| `isbn_ejemplares.csv` | INFOARTES | tabla de ejemplares | `categoria`, `anio`, `valor` |
| `isbn_soporte.csv` | INFOARTES | impreso / digital | `categoria`, `anio`, `valor` |
| `isbn_edicion.csv` | INFOARTES | tipo de edición | `categoria`, `anio`, `valor` |
| `isbn_comercializacion.csv` | INFOARTES | venta / gratuita | `categoria`, `anio`, `valor` |
| `isbn_tiraje.csv` | INFOARTES | rangos de tiraje | `categoria`, `anio`, `valor` |
| `isbn_materia.csv` | INFOARTES | materia (Dewey) | `categoria`, `anio`, `valor` |
| `isbn_departamento.csv` | INFOARTES | departamento del editor | `categoria`, `anio`, `valor` |
| `isbn_agente.csv` | INFOARTES | tipo de editor | `categoria`, `anio`, `valor` |
| `isbn_idioma.csv` | INFOARTES | idioma | `categoria`, `anio`, `valor`, `originaria` (lengua originaria sí/no) |
| `catalogo_totales.csv` | CATÁLOGO BNP | `isbn_totales_anio.csv` | `anio`, `titulos` |
| `digital_titulos.csv` | CATÁLOGO BNP | `isbn_digital_listado.csv` + `isbn_digital_fichas.csv`, unidos por `nt` | las de ambos + `anio` y `tipo_formato` (PDF, ePub y otros e-book, HTML, Audiolibro, Otros formatos) |
| `audiolibros.csv` | CATÁLOGO BNP | `digital_titulos.csv`, solo `tipo_formato` = Audiolibro, 2015–2025 (447 títulos). Para análisis: el dashboard no lo usa | `anio`, `publicado`, `isbn`, `titulo`, `autor`, `editorial`, `materia`, `publico`, `idioma`, `edicion`, `formato`, `tamano`, `precio`, `ficha_bnp` (enlace a la ficha en el catálogo) |
| `comercio_exterior.csv` | COMTRADE | `comtrade/*.json` + `partnerAreas.json` | `anio`, `flujo`, `hs`, `producto`, `pais` (en español, con la librería `babel`), `iso3`, `usd`, `kg` |

## Otros datos del proyecto

| Archivo | Fuente |
|---|---|
| `web/data/peru_departamentos.geojson` | Límites departamentales del INEI, vía https://github.com/juaneladio/peru-geojson |
| `web/data/datos.json` | Generado por `scripts/analizar_datos.py` a partir de `procesados/`; es lo que lee el dashboard |
| `cache/` | Páginas HTML del catálogo BNP guardadas al extraer (no se sube a GitHub) |
