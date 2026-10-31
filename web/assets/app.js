// Dashboard de producción y circulación editorial en el Perú.
// Lee data/datos.json (lo genera scripts/analizar_datos.py) y redibuja todo cuando cambia un filtro.

const estado = {
  desde: 2015,
  hasta: 2025,
  depto: "Todos",
  indicador: "anual",
  anioMapa: null,       // año que muestra el mapa con el indicador "año por año"
  producto: "4901",
  flujo: "Importación",
};

let D = null;          // datos.json
let GEO_PERU = null;   // límites departamentales
const tablas = {};     // vista de tabla de cada gráfico: {columnas, filas}
const formatosOcultos = new Set();  // formatos que se ocultaron con un clic en la leyenda

// ---------- utilidades ----------

const css = (nombre) => getComputedStyle(document.documentElement).getPropertyValue(nombre).trim();

function fmt(n, dec = 0) {
  if (n === null || n === undefined || Number.isNaN(n)) return "–";
  const [ent, frac] = Math.abs(n).toFixed(dec).split(".");
  const conGrupos = ent.length > 4 ? ent.replace(/\B(?=(\d{3})+(?!\d))/g, " ") : ent;
  return (n < 0 ? "−" : "") + conGrupos + (frac ? "," + frac : "");
}
const pct = (n, dec = 1) => fmt(n, dec) + " %";
const millones = (n, dec = 1) => fmt(n / 1e6, dec);
// Montos de comercio con la unidad que les corresponde, para que los socios pequeños no aparezcan como "0,00 M"
const montoUsd = (n) => (n >= 1e6 ? `US$ ${fmt(n / 1e6, 2)} M` : n >= 1e3 ? `US$ ${fmt(n / 1e3, 1)} mil` : `US$ ${fmt(n)}`);
const pctChico = (n) => (n > 0 && n < 0.1 ? "menos de 0,1 %" : pct(n));

function aniosDe(serie) {
  return Object.keys(serie).map(Number).sort((a, b) => a - b);
}

// Años de una serie que caen dentro del periodo elegido
function enRango(serie) {
  return aniosDe(serie).filter((a) => a >= estado.desde && a <= estado.hasta);
}

// Primer y último año del periodo con datos en esa serie (para fuentes que llegan hasta 2023)
function extremos(serie) {
  const a = enRango(serie);
  if (a.length) return [a[0], a[a.length - 1]];
  const todos = aniosDe(serie);
  const ultimo = todos[todos.length - 1];
  return [Math.min(estado.desde, ultimo), ultimo];
}

const sumaAnios = (serie, anios) => anios.reduce((s, a) => s + (serie[a] || 0), 0);

function totalAnio(anio) {
  return D.produccion.titulos[anio];
}

// ---------- tema de Plotly ----------

function base(extra = {}) {
  const tinta2 = css("--tinta-2");
  return {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "system-ui, -apple-system, Segoe UI, sans-serif", size: 12, color: tinta2 },
    separators: ", ",
    margin: { l: 48, r: 16, t: 12, b: 36 },
    hoverlabel: { bgcolor: css("--superficie"), bordercolor: css("--eje"), font: { color: css("--tinta"), size: 13 } },
    xaxis: { gridcolor: "rgba(0,0,0,0)", linecolor: css("--eje"), tickcolor: css("--eje"), fixedrange: true, dtick: 1, tickangle: 0 },
    // Números completos en el eje (10 000 y no "10k"), con espacio de miles y coma decimal
    yaxis: { gridcolor: css("--grilla"), zeroline: false, linecolor: "rgba(0,0,0,0)", fixedrange: true, rangemode: "tozero", tickformat: ",~f" },
    legend: { orientation: "h", x: 0, y: 1.02, yanchor: "bottom", font: { color: tinta2 } },
    bargap: 0.25,
    ...extra,
  };
}

const CONFIG = { displayModeBar: false, responsive: true, locale: "es" };

function dibujar(id, trazas, layout, tabla) {
  tablas[id] = tabla;
  // Las leyendas van arriba del área de trazado: se les reserva espacio solo si se muestran
  const conLeyenda = layout.showlegend !== false && trazas.filter((t) => t.showlegend !== false).length > 1;
  if (conLeyenda && !layout.geo) layout.margin = { ...layout.margin, t: 56 };
  // Se muestran todos los años; si no caben derechos se inclinan para que no se encimen
  const ancho = document.getElementById(id).clientWidth;
  if (layout.xaxis && layout.xaxis.dtick && !layout.geo) {
    const n = new Set(trazas.flatMap((t) => t.x || [])).size;
    const porAnio = (ancho - 60) / Math.max(n, 1);
    layout.xaxis.dtick = 1;
    layout.xaxis.tickangle = porAnio >= 40 ? 0 : porAnio >= 22 ? -45 : -90;
    layout.xaxis.automargin = true;  // deja lugar para las etiquetas inclinadas
  }
  Plotly.react(id, trazas, layout, CONFIG);
  const caja = document.getElementById("tabla-" + id);
  if (caja && !caja.classList.contains("oculto")) pintarTabla(id);
}

// Un año por marca en el eje x (dibujar inclina las etiquetas si no caben)
function dtickAnios() {
  return 1;
}

// ---------- vista de tabla ----------

function prepararVistasTabla() {
  document.querySelectorAll(".tarjeta .grafico").forEach((g) => {
    const tarjeta = g.closest(".tarjeta");
    const fila = g.closest(".mapa-con-lista");
    const verTexto = fila ? "Ver tabla de todos los países" : "Ver tabla";
    const boton = document.createElement("button");
    boton.className = "ver-tabla";
    boton.type = "button";
    boton.textContent = verTexto;
    boton.setAttribute("aria-controls", "tabla-" + g.id);
    boton.setAttribute("aria-expanded", "false");
    // En el mapa mundial el botón va al final de la tarjeta, debajo de la nota al pie; en los demás, en el encabezado
    if (fila) {
      boton.classList.add("debajo");
      (tarjeta.querySelector(".pie") || fila).after(boton);
    } else {
      tarjeta.querySelector("header").appendChild(boton);
    }

    const caja = document.createElement("div");
    caja.className = "tabla-envoltura oculto";
    caja.id = "tabla-" + g.id;
    // En el mapa mundial la tabla se despliega debajo del botón
    (fila ? boton : g).after(caja);

    boton.addEventListener("click", () => {
      const abierta = caja.classList.toggle("oculto") === false;
      boton.textContent = abierta ? "Ocultar tabla" : verTexto;
      boton.setAttribute("aria-expanded", String(abierta));
      if (abierta) pintarTabla(g.id);
    });
  });
}

function pintarTabla(id) {
  const t = tablas[id];
  const caja = document.getElementById("tabla-" + id);
  if (!t || !caja) return;
  const cab = t.columnas.map((c, i) => `<th class="${i ? "num" : ""}">${c}</th>`).join("");
  const filas = t.filas
    .map((f) => "<tr>" + f.map((v, i) => `<td class="${i ? "num" : ""}">${typeof v === "number" ? (t.prefijos?.[i] ?? "") + fmt(v, t.decimales ?? 0) + (t.sufijos?.[i] ?? "") : v}</td>`).join("") + "</tr>")
    .join("");
  caja.innerHTML = `<table><thead><tr>${cab}</tr></thead><tbody>${filas}</tbody></table>`;
}

// Tabla año × serie a partir de trazas de barras o líneas
function tablaAnual(trazas, decimales = 0, sufijo = "") {
  const anios = [...new Set(trazas.flatMap((t) => t.x))].sort((a, b) => a - b);
  return {
    columnas: ["Año", ...trazas.map((t) => t.name)],
    // El año va como texto para que no tome los decimales de los valores
    filas: anios.map((a) => [String(a), ...trazas.map((t) => t.y[t.x.indexOf(a)] ?? "–")]),
    decimales,
    sufijos: ["", ...trazas.map(() => sufijo)],
  };
}

// ---------- KPIs ----------

function kpi({ etiqueta, valor, delta, sentido, nota }) {
  const clase = sentido > 0 ? "sube" : sentido < 0 ? "baja" : "";
  return `<div class="kpi">
    <p class="etiqueta">${etiqueta}</p>
    <div class="valor">${valor}</div>
    ${delta ? `<div class="delta"><b class="${clase}">${delta}</b></div>` : ""}
    ${nota ? `<div class="nota">${nota}</div>` : ""}
  </div>`;
}

function flecha(v) {
  return v > 0 ? "▲" : v < 0 ? "▼" : "■";
}

function variacion(a, b) {
  return (b / a - 1) * 100;
}

function renderKpis() {
  const P = D.produccion;
  const cat = D.catalogo.titulos;
  const [c0, c1] = extremos(cat);
  const [i0, i1] = extremos(P.titulos);

  const tiles = [];
  const vT = variacion(cat[c0], cat[c1]);
  tiles.push(kpi({
    etiqueta: `Títulos con ISBN publicados en ${c1}`,
    valor: fmt(cat[c1]),
    delta: `${flecha(vT)} ${pct(vT, 0)} frente a ${c0}`,
    sentido: Math.sign(vT),
  }));

  // Variación de los ejemplares declarados entre el primer y el último año con datos (InfoArtes llega a 2023)
  const vEj = variacion(P.ejemplares[i0], P.ejemplares[i1]);
  tiles.push(kpi({
    etiqueta: vEj < 0 ? "Caída de ejemplares declarados" : "Variación de ejemplares declarados",
    valor: (vEj > 0 ? "+" : "") + pct(vEj, 0),
    delta: `De ${millones(P.ejemplares[i0])} M (${i0}) a ${millones(P.ejemplares[i1])} M (${i1})`,
    nota: "Ejemplares que declara el editor al registrar el ISBN",
  }));

  if (estado.depto === "Todos") {
    const fuera = (a) => (1 - P.departamento.Lima.serie[a] / totalAnio(a)) * 100;
    const dF = fuera(i1) - fuera(i0);
    tiles.push(kpi({
      etiqueta: `Títulos editados fuera de Lima (${i1})`,
      valor: pct(fuera(i1)),
      delta: `${flecha(dF)} ${fmt(dF, 1)} puntos frente a ${i0}`,
      sentido: Math.sign(dF),
    }));
  } else {
    const s = P.departamento[estado.depto].serie;
    const vD = s[i0] ? variacion(s[i0], s[i1]) : null;
    tiles.push(kpi({
      etiqueta: `Títulos con ISBN en ${estado.depto} (${i1})`,
      valor: fmt(s[i1]),
      delta: vD === null ? `sin títulos en ${i0}` : `${flecha(vD)} ${pct(vD, 0)} frente a ${i0}`,
      sentido: vD === null ? 1 : Math.sign(vD),
      nota: `${pct((s[i1] / totalAnio(i1)) * 100)} del total nacional`,
    }));
  }

  const autor = (a) => (P.agente["Autopublicación (autor-editor)"][a] / totalAnio(a)) * 100;
  const dA = autor(i1) - autor(i0);
  tiles.push(kpi({
    etiqueta: `Títulos autopublicados (${i1})`,
    valor: pct(autor(i1)),
    delta: `${flecha(dA)} ${fmt(dA, 1)} puntos frente a ${i0}`,
    sentido: Math.sign(dA),
  }));

  const dig = D.catalogo.digital_total;
  if (dig) {
    const [d0, d1] = extremos(dig);
    const sh = (a) => ((dig[a] || 0) / cat[a]) * 100;
    const dD = sh(d1) - sh(d0);
    tiles.push(kpi({
      etiqueta: `Publicaciones digitales (${d1})`,
      valor: pct(sh(d1)),
      delta: `${flecha(dD)} ${fmt(dD, 1)} puntos frente a ${d0}`,
      sentido: Math.sign(dD),
      nota: "Porcentaje de los títulos del catálogo ISBN",
    }));
  } else {
    const sh = (a) => (P.soporte.Digital[a] / totalAnio(a)) * 100;
    const dD = sh(i1) - sh(i0);
    tiles.push(kpi({
      etiqueta: `Títulos digitales (${i1})`,
      valor: pct(sh(i1)),
      delta: `${flecha(dD)} ${fmt(dD, 1)} puntos frente a ${i0}`,
      sentido: Math.sign(dD),
    }));
  }

  const exp = D.comercio.mundo["4901|Exportación"];
  const imp = D.comercio.mundo["4901|Importación"];
  const [e0, e1] = extremos(exp);
  const vE = variacion(exp[e0], exp[e1]);
  tiles.push(kpi({
    etiqueta: `Exportaciones de libros (${e1})`,
    valor: "US$ " + millones(exp[e1]) + " M",
    delta: `${flecha(vE)} ${pct(vE, 0)} frente a ${e0}`,
    sentido: Math.sign(vE),
    nota: `Se importaron US$ ${fmt(imp[e1] / exp[e1], 1)} por cada dólar exportado`,
  }));

  document.getElementById("kpis").innerHTML = tiles.join("");
}

// ---------- Producción ----------

function renderTitulos() {
  const s = D.catalogo.titulos;
  const x = enRango(s);
  const traza = {
    type: "bar", name: "Títulos", x, y: x.map((a) => s[a]),
    marker: { color: css("--s1") },
    hovertemplate: "%{x}: <b>%{y:,}</b> títulos<extra></extra>",
  };
  const l = base({ showlegend: false });
  l.xaxis.dtick = dtickAnios(x.length);
  dibujar("g-titulos", [traza], l, tablaAnual([traza]));
}

function renderTirajePromedio() {
  const P = D.produccion;
  const x = enRango(P.titulos);
  const traza = {
    type: "bar", name: "Ejemplares por título", x, y: x.map((a) => Math.round(P.ejemplares[a] / P.titulos[a])),
    marker: { color: css("--s1") },
    hovertemplate: "%{x}: <b>%{y:,}</b> ejemplares por título<extra></extra>",
  };
  const l = base({ showlegend: false });
  l.xaxis.dtick = dtickAnios(x.length);
  dibujar("g-tiraje-prom", [traza], l, tablaAnual([traza]));
}

function renderTiraje() {
  const P = D.produccion;
  const x = enRango(P.titulos);
  const colores = [css("--seq-1"), css("--seq-2"), css("--seq-3"), css("--seq-4")];
  const trazas = P.tiraje_orden.map((cat, i) => ({
    type: "bar", name: cat + " ej.", x,
    y: x.map((a) => (P.tiraje[cat][a] / P.titulos[a]) * 100),
    marker: { color: colores[i], line: { color: css("--superficie"), width: 1 } },
    hovertemplate: `%{x} · ${cat} ejemplares: <b>%{y:.1f} %</b><extra></extra>`,
  }));
  const l = base({ barmode: "stack" });
  l.yaxis.ticksuffix = " %";
  l.yaxis.range = [0, 100];
  l.xaxis.dtick = dtickAnios(x.length);
  dibujar("g-tiraje", trazas, l, tablaAnual(trazas, 1, " %"));
}

// ---------- Quién publica ----------

const ORDEN_AGENTES = ["Editoriales", "Universidades", "Autopublicación (autor-editor)", "Otras entidades"];

function renderAgente() {
  const P = D.produccion;
  const x = enRango(P.titulos);
  const colores = [css("--s1"), css("--s2"), css("--s3"), css("--s4")];
  const trazas = ORDEN_AGENTES.map((cat, i) => ({
    type: "scatter", mode: "lines+markers", name: cat, x,
    y: x.map((a) => (P.agente[cat][a] / P.titulos[a]) * 100),
    line: { color: colores[i], width: 2 },
    marker: { size: 8, color: colores[i], line: { color: css("--superficie"), width: 2 } },
    hovertemplate: `%{x} · ${cat}: <b>%{y:.1f} %</b><extra></extra>`,
  }));
  const l = base();
  l.yaxis.ticksuffix = " %";
  l.xaxis.dtick = dtickAnios(x.length);
  l.margin.r = 16;
  dibujar("g-agente", trazas, l, tablaAnual(trazas, 1, " %"));
}

function renderMateria() {
  const P = D.produccion;
  const [a0, a1] = extremos(P.titulos);
  const total = (a) => Object.values(P.materia).reduce((s, serie) => s + (serie[a] || 0), 0);
  const cats = Object.keys(P.materia).sort((a, b) => P.materia[b][a1] - P.materia[a][a1]);
  const sh = (c, a) => (P.materia[c][a] / total(a)) * 100;
  const etiqueta = (c) => c.replace(/^\d+ - /, "").replace(" (ciencias aplicadas)", "").replace("Las Artes Bellas y artes decorativas", "Artes")
    .replace("Ciencias naturales y matemáticas", "Ciencias naturales").replace(" y retórica", "");
  // Las áreas van en el eje horizontal. Si la tarjeta es angosta los nombres se inclinan en una línea;
  // si hay espacio van derechos y los largos se parten en dos
  const angosto = document.getElementById("g-materia").clientWidth < 720;
  const corta = (c) => angosto ? etiqueta(c) : etiqueta(c).replace("Ciencias ", "Ciencias<br>")
    .replace(" y psicología", " y<br>psicología").replace(" e historia", "<br>e historia").replace("Generalidades", "Generali-<br>dades");

  const conectores = {
    type: "scatter", mode: "lines", showlegend: false, hoverinfo: "skip",
    x: cats.flatMap((c) => [corta(c), corta(c), null]),
    y: cats.flatMap((c) => [sh(c, a0), sh(c, a1), null]),
    line: { color: css("--eje"), width: 2 },
  };
  const punto = (a, color, nombre) => ({
    type: "scatter", mode: "markers", name: nombre,
    x: cats.map(corta), y: cats.map((c) => sh(c, a)), customdata: cats.map(etiqueta),
    marker: { size: 10, color, line: { color: css("--superficie"), width: 2 } },
    hovertemplate: `%{customdata} · ${a}: <b>%{y:.1f} %</b><extra></extra>`,
  });
  const l = base();
  l.margin = { ...l.margin, l: 48, b: 24 };
  l.xaxis = { ...l.xaxis, dtick: null, type: "category", categoryorder: "array", categoryarray: cats.map(corta),
    tickangle: angosto ? -45 : 0, tickfont: { size: 11 }, automargin: true };
  l.yaxis = { ...l.yaxis, ticksuffix: " %", dtick: 10 };
  dibujar("g-materia", [conectores, punto(a0, css("--tinta-3"), String(a0)), punto(a1, css("--s1"), String(a1))], l, {
    columnas: ["Área", String(a0), String(a1)],
    filas: cats.map((c) => [etiqueta(c), sh(c, a0), sh(c, a1)]),
    decimales: 1,
    sufijos: ["", " %", " %"],
  });
}

// ---------- Territorio ----------

function valoresDepto() {
  const P = D.produccion;
  const [a0, a1] = extremos(P.titulos);
  const anios = enRango(P.titulos);
  return Object.entries(P.departamento).map(([nombre, d]) => {
    const s = d.serie;
    return {
      nombre, clave: d.clave, inicio: s[a0] || 0, fin: s[a1] || 0,
      acumulado: sumaAnios(s, anios.length ? anios : [a1]),
      variacion: s[a0] ? variacion(s[a0], s[a1]) : null,
    };
  });
}

function renderMapa() {
  const P = D.produccion;
  const [a0, a1] = extremos(P.titulos);
  const filas = valoresDepto();
  const ind = estado.indicador;
  const esVar = ind === "variacion";
  const esAnual = ind === "anual";

  // Año por año: el deslizador recorre los años del periodo con datos departamentales
  const aniosMapa = enRango(P.titulos).length ? enRango(P.titulos) : [a1];
  if (!aniosMapa.includes(estado.anioMapa)) estado.anioMapa = aniosMapa[aniosMapa.length - 1];
  const anio = estado.anioMapa;
  const deAnio = (f) => P.departamento[f.nombre].serie[anio] || 0;
  prepararAnioMapa(aniosMapa, esAnual);

  const valor = (f) => (ind === "acumulado" ? f.acumulado : esAnual ? deAnio(f) : f.variacion);

  let z, colorscale, zmin, zmax, colorbar;
  if (esVar) {
    // Escala divergente centrada en 0; los extremos se recortan en ±200 % para que se vean los matices
    z = filas.map((f) => (f.variacion === null ? null : Math.max(-200, Math.min(200, f.variacion))));
    colorscale = [[0, css("--div-neg")], [0.5, css("--div-mid")], [1, css("--seq-3")]];
    zmin = -200; zmax = 200;
    colorbar = { ticksuffix: " %", tickvals: [-200, -100, 0, 100, 200], ticktext: ["≤ −200 %", "−100 %", "0", "+100 %", "≥ +200 %"] };
  } else {
    z = filas.map((f) => Math.log10(Math.max(valor(f), 1)));
    colorscale = [[0, css("--seq-0")], [0.33, css("--seq-1")], [0.66, css("--seq-2")], [1, css("--seq-4")]];
    zmin = 0; zmax = Math.ceil(Math.max(...z));
    // Año por año: la escala se fija con el máximo de todo el periodo, para que los colores se comparen entre años
    if (esAnual) zmax = Math.ceil(Math.log10(Math.max(...filas.flatMap((f) => aniosMapa.map((a) => P.departamento[f.nombre].serie[a] || 1)))));
    const ticks = [1, 10, 100, 1000, 10000, 100000].filter((t) => Math.log10(t) <= zmax);
    colorbar = { tickvals: ticks.map(Math.log10), ticktext: ticks.map((t) => fmt(t)) };
  }
  const texto = filas.map((f) => esAnual
    ? `<b>${f.nombre}</b><br>${anio}: ${fmt(deAnio(f))} títulos`
    : `<b>${f.nombre}</b><br>${a0}: ${fmt(f.inicio)} · ${a1}: ${fmt(f.fin)}<br>` +
      `Acumulado: ${fmt(f.acumulado)}<br>Variación: ${f.variacion === null ? "sin base en " + a0 : pct(f.variacion, 0)}`);

  const trazas = [{
    type: "choropleth", geojson: GEO_PERU, featureidkey: "properties.NOMBDEP",
    locations: filas.map((f) => f.clave), z, zmin, zmax, colorscale,
    text: texto, hovertemplate: "%{text}<extra></extra>",
    marker: { line: { color: css("--superficie"), width: 1 } },
    colorbar: { ...colorbar, thickness: 10, len: 0.6, outlinewidth: 0, tickfont: { color: css("--tinta-2") } },
  }];
  const sel = filas.find((f) => f.nombre === estado.depto);
  if (sel) {
    trazas.push({
      type: "choropleth", geojson: GEO_PERU, featureidkey: "properties.NOMBDEP",
      locations: [sel.clave], z: [0], showscale: false, hoverinfo: "skip",
      colorscale: [[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
      marker: { line: { color: css("--tinta"), width: 2.5 } },
    });
  }
  const l = base({
    margin: { l: 0, r: 0, t: 0, b: 0 },
    geo: { fitbounds: "locations", visible: false, bgcolor: "rgba(0,0,0,0)", projection: { type: "mercator" } },
    dragmode: false,
  });
  document.getElementById("sub-mapa").textContent =
    ind === "acumulado" ? `Títulos acumulados ${a0}–${a1}` : esAnual ? `Títulos registrados en ${anio}` : `Variación ${a0}–${a1}`;
  // Año por año: la tabla muestra cada departamento con todos los años del periodo
  const tabla = esAnual
    ? {
        columnas: ["Departamento", ...aniosMapa.map(String)],
        filas: [...filas].sort((a, b) => deAnio(b) - deAnio(a))
          .map((f) => [f.nombre, ...aniosMapa.map((a) => P.departamento[f.nombre].serie[a] || 0)]),
      }
    : {
        columnas: ["Departamento", String(a0), String(a1), "Acumulado", "Variación"],
        filas: [...filas].sort((a, b) => b.fin - a.fin).map((f) => [f.nombre, f.inicio, f.fin, f.acumulado, f.variacion ?? "–"]),
        sufijos: ["", "", "", "", " %"],
      };
  dibujar("g-mapa", trazas, l, tabla);
}

// Línea de tiempo del indicador "año por año": un botón por cada año del periodo
function prepararAnioMapa(anios, visible) {
  const caja = document.getElementById("anio-mapa");
  caja.hidden = !visible;
  if (!visible) return;
  caja.innerHTML = anios
    .map((a) => `<button type="button" data-anio="${a}" aria-pressed="${a === estado.anioMapa}">${a}</button>`)
    .join("");
  // En pantallas angostas la línea se desliza: el año elegido queda centrado sin mover la página
  const activo = caja.querySelector('[aria-pressed="true"]');
  if (activo) caja.scrollLeft = activo.offsetLeft - (caja.clientWidth - activo.offsetWidth) / 2;
}

function renderDepto() {
  const P = D.produccion;
  const x = enRango(P.titulos);
  let trazas;
  if (estado.depto === "Todos") {
    const lima = P.departamento.Lima.serie;
    trazas = [
      { name: "Lima", y: x.map((a) => lima[a]), color: css("--s1") },
      { name: "Resto del país", y: x.map((a) => totalAnio(a) - lima[a]), color: css("--s2") },
    ].map((t) => ({
      type: "scatter", mode: "lines+markers", name: t.name, x, y: t.y,
      line: { color: t.color, width: 2 }, marker: { size: 8, color: t.color, line: { color: css("--superficie"), width: 2 } },
      hovertemplate: `%{x} · ${t.name}: <b>%{y:,}</b><extra></extra>`,
    }));
    document.getElementById("t-depto").textContent = "Lima frente al resto del país";
  } else {
    const s = P.departamento[estado.depto].serie;
    trazas = [{
      type: "bar", name: estado.depto, x, y: x.map((a) => s[a] || 0), marker: { color: css("--s1") },
      hovertemplate: `%{x}: <b>%{y:,}</b> títulos<extra></extra>`,
    }];
    document.getElementById("t-depto").textContent = estado.depto;
  }
  const l = base({ showlegend: trazas.length > 1 });
  l.xaxis.dtick = dtickAnios(x.length);
  dibujar("g-depto", trazas, l, tablaAnual(trazas));

  const [a0, a1] = extremos(P.titulos);
  const tabla = document.getElementById("tabla-deptos");
  tabla.querySelector("thead").innerHTML =
    `<tr><th>Departamento</th><th class="num">${a0}</th><th class="num">${a1}</th><th class="num">Var.</th></tr>`;
  tabla.querySelector("tbody").innerHTML = valoresDepto()
    .sort((a, b) => b.fin - a.fin)
    .map((f) => `<tr data-depto="${f.nombre}" tabindex="0" class="${f.nombre === estado.depto ? "sel" : ""}">
      <td>${f.nombre}</td><td class="num">${fmt(f.inicio)}</td><td class="num">${fmt(f.fin)}</td>
      <td class="num">${f.variacion === null ? "–" : pct(f.variacion, 0)}</td></tr>`)
    .join("");
}

// ---------- Digital y audio ----------

function renderSoporte() {
  const P = D.produccion;
  const x = enRango(P.titulos);
  const trazas = [["Impreso", css("--s1")], ["Digital", css("--s2")]].map(([cat, color]) => ({
    type: "bar", name: cat, x, y: x.map((a) => P.soporte[cat][a]),
    marker: { color, line: { color: css("--superficie"), width: 1 } },
    customdata: x.map((a) => (P.soporte[cat][a] / P.titulos[a]) * 100),
    hovertemplate: `%{x} · ${cat}: <b>%{y:,}</b> (%{customdata:.1f} %)<extra></extra>`,
  }));
  const l = base({ barmode: "stack" });
  l.xaxis.dtick = dtickAnios(x.length);
  dibujar("g-soporte", trazas, l, tablaAnual(trazas));
}

const ORDEN_FORMATOS = [["PDF", "--s1"], ["ePub y otros e-book", "--s2"], ["HTML", "--s3"], ["Audiolibro", "--s4"], ["Otros formatos", "--tinta-3"]];

function renderFormatos() {
  const F = D.catalogo.digital_formato;
  const div = document.getElementById("g-formatos");
  if (!F) {
    div.innerHTML = '<p class="sub" style="padding:40px 0;text-align:center">La descarga de fichas del catálogo aún no termina.</p>';
    return;
  }
  const x = enRango(D.catalogo.digital_total);
  // Los formatos van de mayor a menor según los títulos del periodo; cada uno conserva su color
  const total = (cat) => x.reduce((s, a) => s + (F[cat][a] || 0), 0);
  const trazas = ORDEN_FORMATOS.filter(([cat]) => F[cat])
    .sort(([a], [b]) => total(b) - total(a))
    .map(([cat, color]) => ({
      type: "bar", name: cat, x, y: x.map((a) => F[cat][a] || 0),
      marker: { color: css(color), line: { color: css("--superficie"), width: 1 } },
      hovertemplate: `%{x} · ${cat}: <b>%{y:,}</b><extra></extra>`,
      visible: formatosOcultos.has(cat) ? "legendonly" : true,
    }));
  // Leyenda propia, de mayor a menor recorriendo primero la columna izquierda y luego la derecha
  const ley = document.getElementById("ley-formatos");
  ley.style.gridTemplateRows = `repeat(${Math.ceil(trazas.length / 2)}, auto)`;
  ley.innerHTML = trazas.map((t) =>
    `<button type="button" data-serie="${t.name}" aria-pressed="${!formatosOcultos.has(t.name)}"><span style="background:${t.marker.color}"></span>${t.name}</button>`).join("");
  const l = base({ barmode: "stack", showlegend: false });
  l.xaxis.dtick = dtickAnios(x.length);
  dibujar("g-formatos", trazas, l, tablaAnual(trazas));
}

function renderAudio() {
  const lista = D.catalogo.audiolibros || [];
  const serie = (D.catalogo.digital_formato || {}).Audiolibro || {};
  const x = enRango(D.catalogo.digital_total);
  const delAnio = (a) => lista.filter((r) => Number(r.publicado.slice(0, 4)) === a);
  const enPeriodo = lista.filter((r) => x.includes(Number(r.publicado.slice(0, 4))));
  document.getElementById("sub-audio").textContent =
    `${fmt(enPeriodo.length)} títulos en formato de audio entre ${x[0]} y ${x[x.length - 1]}, de ${fmt(new Set(enPeriodo.map((r) => r.editorial)).size)} editoriales o instituciones`;

  // En el cursor: las editoriales del año, de mayor a menor (las tres primeras y el resto agrupado)
  const detalle = (a) => {
    const cuenta = {};
    for (const r of delAnio(a)) cuenta[r.editorial] = (cuenta[r.editorial] || 0) + 1;
    const orden = Object.entries(cuenta).sort((p, q) => q[1] - p[1]);
    const resto = orden.slice(3).reduce((s, [, n]) => s + n, 0);
    return orden.slice(0, 3).map(([e, n]) => `${e}: ${fmt(n)}`).join("<br>") + (resto ? `<br>Otras: ${fmt(resto)}` : "");
  };
  const traza = {
    type: "bar", name: "Audiolibros", x, y: x.map((a) => serie[a] || 0),
    marker: { color: css("--s4"), line: { color: css("--superficie"), width: 1 } },
    text: x.map((a) => serie[a] ? fmt(serie[a]) : ""), textposition: "outside", cliponaxis: false,
    textfont: { color: css("--tinta-2"), size: 12 },
    customdata: x.map(detalle),
    hovertemplate: "<b>%{x}: %{y} audiolibros</b><br>%{customdata}<extra></extra>",
  };
  const l = base({ showlegend: false });
  l.margin = { ...l.margin, t: 24 };
  l.xaxis.dtick = dtickAnios(x.length);
  dibujar("g-audio", [traza], l, tablaAnual([traza]));
}

// ---------- Circulación ----------

function renderComercio() {
  const M = D.comercio.mundo;
  const trazas = [["Importación", "--s1"], ["Exportación", "--s2"]].map(([flujo, color]) => {
    const s = M[`${estado.producto}|${flujo}`] || {};
    const x = enRango(s);
    return {
      type: "scatter", mode: "lines+markers", name: flujo === "Importación" ? "Importaciones" : "Exportaciones",
      x, y: x.map((a) => s[a] / 1e6),
      line: { color: css(color), width: 2 }, marker: { size: 8, color: css(color), line: { color: css("--superficie"), width: 2 } },
      hovertemplate: `%{x}: <b>US$ %{y:.1f} M</b><extra>%{fullData.name}</extra>`,
    };
  });
  const l = base();
  l.yaxis.tickprefix = "US$ ";
  l.margin.l = 76;
  l.yaxis.ticksuffix = " M";
  l.xaxis.dtick = 1;
  // En la tabla, cada monto lleva su moneda y la unidad (millones de US$)
  const tabla = tablaAnual(trazas, 1, " M");
  tabla.prefijos = ["", ...trazas.map(() => "US$ ")];
  dibujar("g-comercio", trazas, l, tabla);
}

function sociosEnPeriodo() {
  const acumulado = new Map();
  for (const r of D.comercio.socios) {
    if (r.hs !== Number(estado.producto) || r.flujo !== estado.flujo) continue;
    if (r.anio < estado.desde || r.anio > estado.hasta) continue;
    const k = r.pais;
    const prev = acumulado.get(k) || { pais: r.pais, iso3: r.iso3, usd: 0 };
    prev.usd += r.usd;
    acumulado.set(k, prev);
  }
  return [...acumulado.values()].sort((a, b) => b.usd - a.usd);
}

// Periodo con datos de comercio dentro del elegido, para los subtítulos: "(2015–2025)"
function periodoComercio() {
  const anios = D.comercio.socios.map((r) => r.anio).filter((a) => a >= estado.desde && a <= estado.hasta);
  const a0 = Math.min(...anios), a1 = Math.max(...anios);
  return a0 === a1 ? `(${a0})` : `(${a0}–${a1})`;
}

// Color de una posición (0 a 1) dentro de una escala de Plotly, para que la lista use los mismos tonos que el mapa
function colorEnEscala(escala, v) {
  const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  for (let i = 1; i < escala.length; i++) {
    const [p0, c0] = escala[i - 1], [p1, c1] = escala[i];
    if (v <= p1) {
      const f = (v - p0) / (p1 - p0 || 1), a = rgb(c0), b = rgb(c1);
      return `rgb(${a.map((x, k) => Math.round(x + (b[k] - x) * f)).join(",")})`;
    }
  }
  return escala[escala.length - 1][1];
}

function renderMundo() {
  const socios = sociosEnPeriodo().filter((s) => s.iso3 && s.iso3.length === 3);
  const total = socios.reduce((s, r) => s + r.usd, 0);
  const importa = estado.flujo === "Importación";
  const producto = D.comercio.productos[estado.producto].toLowerCase();
  const periodo = periodoComercio();
  document.getElementById("t-mapa-mundo").textContent = `${importa ? "De dónde vienen" : "A dónde van"} los ${producto}`;

  // Solo se pintan los diez socios principales; el color es el monto en millones de US$ y la lista de al lado hace de leyenda
  const top = socios.slice(0, 10);
  const share = (s) => (s.usd / total) * 100;
  const sumaTop = top.reduce((s, r) => s + share(r), 0);
  const quien = importa ? "orígenes" : "destinos";
  document.getElementById("sub-mundo").textContent = `Los diez principales ${quien}, en millones de US$ acumulados y porcentaje de participación ${periodo}`;
  document.getElementById("pie-mundo").innerHTML = socios.length > 10
    ? `Estos diez países concentran el <strong>${pct(sumaTop)}</strong> de las ${importa ? "importaciones" : "exportaciones"} de ${producto} ` +
      `${periodo}; los otros ${fmt(socios.length - 10)} países con comercio suman el ${pct(100 - sumaTop)}.<br>` +
      "Fuente: UN Comtrade."
    : `Se muestran los ${fmt(socios.length)} países con comercio registrado ${periodo}.<br>Fuente: UN Comtrade.`;

  const maxUsd = Math.max(...top.map((s) => s.usd), 1);
  const escala = [[0, css("--seq-1")], [0.5, css("--seq-2")], [1, css("--seq-4")]];
  document.getElementById("lista-mundo").innerHTML =
    `<li class="cab-fila"><span class="cab">Monto acumulado y participación ${periodo}</span></li>` +
    top.map((s, i) => `<li><span class="muestra" style="background:${colorEnEscala(escala, s.usd / maxUsd)}"></span>` +
      `<span class="puesto">${i + 1}.</span><span>${s.pais}</span><span class="monto">${montoUsd(s.usd)}</span><span class="monto">${pctChico(share(s))}</span></li>`).join("");
  const trazas = [{
    type: "choropleth", locationmode: "ISO-3", locations: top.map((s) => s.iso3), z: top.map((s) => s.usd / 1e6), zmin: 0, zmax: maxUsd / 1e6,
    showscale: false,
    text: top.map((s, i) => `<b>${i + 1}. ${s.pais}</b><br>${montoUsd(s.usd)} · ${pctChico(share(s))}`),
    hovertemplate: "%{text}<extra></extra>",
    colorscale: escala,
    marker: { line: { color: css("--superficie"), width: 0.5 } },
  }];
  const l = base({
    margin: { l: 0, r: 0, t: 0, b: 0 },
    geo: {
      projection: { type: "natural earth" }, showframe: false, showcoastlines: false,
      showland: true, landcolor: css("--grilla"), showcountries: true, countrycolor: css("--superficie"),
      bgcolor: "rgba(0,0,0,0)", lataxis: { range: [-58, 85] },
    },
    dragmode: false,
  });
  dibujar("g-mundo", trazas, l, {
    columnas: ["País", "Monto", "Participación"],
    filas: socios.map((s) => [s.pais, montoUsd(s.usd), pctChico(share(s))]),
  });
}

// ---------- Hallazgos ----------

// Entero con espacio de miles también en cuatro cifras ("6 093"), para los textos de los hallazgos
const miles = (n) => (Math.round(n) >= 1000 ? `${Math.floor(Math.round(n) / 1000)} ${String(Math.round(n) % 1000).padStart(3, "0")}` : String(Math.round(n)));

// Rango de tiraje de InfoArtes en palabras: "501-1000" → "501 a 1 000"; "0-500" → "500 o menos"
function rangoTiraje(r) {
  if (r.startsWith(">")) return "más de 5 000";
  const [d, h] = r.split("-").map(Number);
  return d === 0 ? `${miles(h)} o menos` : `${miles(d)} a ${miles(h)}`;
}

function renderHallazgos() {
  const [h1, h2, h3, h4] = D.hallazgos.map((h) => h.cifras);
  const c = (v) => `<span class="cifra">${v}</span>`;
  const textos = [
    `Entre 2015 y 2023 los títulos con ISBN pasaron de ${c(miles(h1.titulos_a))} a ${c(miles(h1.titulos_b))} (${c("+" + pct(h1.var_titulos, 0))}); en ${h1.anio_ultimo}, el catálogo registró ${c(fmt(h1.catalogo_ultimo))}. ` +
      `Pero los ejemplares declarados cayeron ${c(pct(-h1.var_ejemplares, 0))}. ` +
      `Típicamente, hasta 2019, el libro se imprimía en ${c(rangoTiraje(h1.mediana_2019))} ejemplares. ` +
      `Desde 2020, se registran mayores porcentajes de libros impresos en ${c("500 ejemplares a menos")}.`,
    `Las publicaciones digitales pasaron de ${c(pct(h2.dig_a, 0))} de los títulos en 2015 a ${c(pct(h2.dig_2020, 0))} en 2020 y se mantienen en ${c(pct(h2.dig_u, 0))} en ${h2.anio_u}. ` +
      `El PDF pasó de ${c(pct(h2.pdf_a, 0))} a ${c(pct(h2.pdf_u, 0))} de lo digital; en cambio, solo ${c(fmt(h2.audio_n))} títulos se registraron como audio entre 2015 y ${h2.anio_u}. ` +
      `Cinco editoriales o instituciones registraron el ${c(pct(h2.audio_top5, 0))} de esos audiolibros.`,
    `Entre 2015 y 2023 los títulos editados fuera de Lima casi se triplicaron (${c(fmt(h3.fuera_a))} → ${c(fmt(h3.fuera_b))}) y Lima bajó de ${c(pct(h3.lima_a, 0))} a ${c(pct(h3.lima_b, 0))} del total. ` +
      `La autopublicación, en la que el autor registra su propio libro, pasó de ${c(pct(h3.autor_a))} a ${c(pct(h3.autor_b))} de los títulos.`,
    `Las exportaciones de libros cayeron de ${c("US$ " + millones(h4.exp_a) + " M")} en 2015 a ${c("US$ " + millones(h4.exp_b) + " M")} en ${h4.anio_ultimo} (${c(pct(h4.var_exp, 0))}); ` +
      `mientras las importaciones bajaron mucho menos, de ${c("US$ " + millones(h4.imp_a) + " M")} a ${c("US$ " + millones(h4.imp_b) + " M")} (${c(pct((h4.imp_b / h4.imp_a - 1) * 100, 0))}), tras recuperarse de la caída de 2020. ` +
      `En ${h4.anio_ultimo} el Perú importó ${c(fmt(h4.ratio, 1))} dólares en libros por cada dólar que exportó.`,
  ];
  document.getElementById("lista-hallazgos").innerHTML = D.hallazgos
    .map((h, i) => `<article class="hallazgo"><h3>${h.titulo}</h3><p>${textos[i]}</p></article>`)
    .join("");
}

// ---------- Descarga ----------

function descargarCsv() {
  const P = D.produccion;
  const filas = [["fuente", "indicador", "categoria", "anio", "valor"]];
  const agregar = (fuente, indicador, porCategoria) => {
    for (const [cat, serie] of Object.entries(porCategoria)) {
      for (const a of enRango(serie)) filas.push([fuente, indicador, cat, a, serie[a]]);
    }
  };
  agregar("BNP/InfoArtes", "titulos", { Total: P.titulos });
  agregar("BNP/InfoArtes", "ejemplares", { Total: P.ejemplares });
  agregar("BNP/InfoArtes", "soporte", P.soporte);
  agregar("BNP/InfoArtes", "tiraje", P.tiraje);
  agregar("BNP/InfoArtes", "agente", P.agente);
  agregar("BNP/InfoArtes", "materia", P.materia);
  const deptos = Object.fromEntries(
    Object.entries(P.departamento)
      .filter(([n]) => estado.depto === "Todos" || n === estado.depto)
      .map(([n, d]) => [n, d.serie]));
  agregar("BNP/InfoArtes", "departamento", deptos);
  agregar("BNP/catalogo ISBN", "titulos", { Total: D.catalogo.titulos });
  if (D.catalogo.digital_formato) agregar("BNP/catalogo ISBN", "formato_digital", D.catalogo.digital_formato);
  for (const [clave, serie] of Object.entries(D.comercio.mundo)) {
    const [hs, flujo] = clave.split("|");
    for (const a of enRango(serie)) filas.push(["UN Comtrade", `comercio_${hs}_usd`, flujo, a, serie[a]]);
  }
  const csv = filas.map((f) => f.map((v) => (/[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : v)).join(",")).join("\n");
  const enlace = document.createElement("a");
  enlace.href = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
  enlace.download = `produccion_editorial_peru_${estado.desde}_${estado.hasta}${estado.depto === "Todos" ? "" : "_" + estado.depto}.csv`;
  enlace.click();
  URL.revokeObjectURL(enlace.href);
}

// ---------- controles ----------

function renderTodo() {
  renderKpis();
  renderTitulos();
  renderTirajePromedio();
  renderTiraje();
  renderAgente();
  renderMateria();
  renderMapa();
  renderDepto();
  renderSoporte();
  renderFormatos();
  renderAudio();
  renderComercio();
  renderMundo();
}

// Al redibujar, lo que está a la vista no debe moverse: se toma como ancla la primera tarjeta visible
// debajo de la barra fija y, después de redibujar, se corrige el desplazamiento si cambió de lugar
function sinSaltos(redibujar) {
  const borde = document.querySelector(".barra").getBoundingClientRect().bottom;
  const bloques = [...document.querySelectorAll(".kpi, section > h2, .tarjeta, .hallazgo")];
  const ancla = bloques.find((e) => e.getBoundingClientRect().top >= borde)
    || bloques.find((e) => e.getBoundingClientRect().bottom > borde);
  const antes = ancla ? ancla.getBoundingClientRect().top : 0;
  // Los KPIs se reemplazan al redibujar: después se busca la tarjeta que ocupa la misma posición
  const nKpi = ancla && ancla.classList.contains("kpi") ? [...document.querySelectorAll(".kpi")].indexOf(ancla) : -1;
  redibujar();
  if (!ancla) return;
  const corregir = () => {
    const actual = nKpi >= 0 ? document.querySelectorAll(".kpi")[nKpi] : ancla;
    if (!actual || !actual.isConnected) return;
    const d = actual.getBoundingClientRect().top - antes;
    if (Math.abs(d) > 1) window.scrollBy({ top: d, behavior: "instant" });
  };
  corregir();
  requestAnimationFrame(corregir);
}

function elegirDepto(nombre) {
  estado.depto = estado.depto === nombre ? "Todos" : nombre;
  document.getElementById("f-depto").value = estado.depto;
  sinSaltos(() => { renderKpis(); renderMapa(); renderDepto(); });
}

function iniciarControles() {
  const anios = aniosDe(D.catalogo.titulos);
  const opciones = anios.map((a) => `<option value="${a}">${a}</option>`).join("");
  const desde = document.getElementById("f-desde");
  const hasta = document.getElementById("f-hasta");
  desde.innerHTML = opciones;
  hasta.innerHTML = opciones;
  estado.hasta = anios[anios.length - 1];
  desde.value = estado.desde;
  hasta.value = estado.hasta;
  const alCambiarAnio = (e) => {
    estado.desde = Number(desde.value);
    estado.hasta = Number(hasta.value);
    // El periodo necesita al menos dos años para comparar
    if (estado.desde >= estado.hasta) {
      if (e.target === desde) estado.hasta = Math.min(estado.desde + 1, anios[anios.length - 1]);
      else estado.desde = Math.max(estado.hasta - 1, anios[0]);
      if (estado.desde >= estado.hasta) estado.desde = estado.hasta - 1;
      desde.value = estado.desde;
      hasta.value = estado.hasta;
    }
    sinSaltos(renderTodo);
  };
  desde.addEventListener("change", alCambiarAnio);
  hasta.addEventListener("change", alCambiarAnio);

  const depto = document.getElementById("f-depto");
  const nombres = Object.keys(D.produccion.departamento).sort((a, b) => a.localeCompare(b, "es"));
  depto.innerHTML = `<option value="Todos">Todos</option>` + nombres.map((n) => `<option>${n}</option>`).join("");
  depto.addEventListener("change", () => { estado.depto = "__"; elegirDepto(depto.value); });

  document.getElementById("f-indicador").addEventListener("change", (e) => { estado.indicador = e.target.value; sinSaltos(renderMapa); });
  document.getElementById("anio-mapa").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-anio]");
    if (b) { estado.anioMapa = Number(b.dataset.anio); sinSaltos(renderMapa); }
  });

  const producto = document.getElementById("f-producto");
  producto.innerHTML = Object.entries(D.comercio.productos).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
  producto.addEventListener("change", () => { estado.producto = producto.value; sinSaltos(() => { renderComercio(); renderMundo(); }); });

  document.querySelectorAll("#f-flujo button").forEach((b) => b.addEventListener("click", () => {
    estado.flujo = b.dataset.v;
    document.querySelectorAll("#f-flujo button").forEach((o) => o.setAttribute("aria-pressed", String(o === b)));
    sinSaltos(renderMundo);
  }));

  document.getElementById("ley-formatos").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-serie]");
    if (!b) return;
    const s = b.dataset.serie;
    if (formatosOcultos.has(s)) formatosOcultos.delete(s); else formatosOcultos.add(s);
    sinSaltos(renderFormatos);
  });


  const tablaDeptos = document.getElementById("tabla-deptos");
  tablaDeptos.addEventListener("click", (e) => { const tr = e.target.closest("tr[data-depto]"); if (tr) elegirDepto(tr.dataset.depto); });
  tablaDeptos.addEventListener("keydown", (e) => {
    const tr = e.target.closest("tr[data-depto]");
    if (tr && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); elegirDepto(tr.dataset.depto); }
  });
  document.getElementById("g-mapa").on("plotly_click", (e) => {
    const clave = e.points[0].location;
    const nombre = Object.keys(D.produccion.departamento).find((n) => D.produccion.departamento[n].clave === clave);
    if (nombre) elegirDepto(nombre);
  });

  document.getElementById("descargar").addEventListener("click", descargarCsv);

  // Resalta en la navegación la sección visible
  const enlaces = [...document.querySelectorAll(".barra nav a")];
  const observador = new IntersectionObserver((entradas) => {
    for (const en of entradas) {
      if (en.isIntersecting) enlaces.forEach((a) => a.classList.toggle("activo", a.hash === "#" + en.target.id));
    }
  }, { rootMargin: "-40% 0px -55% 0px" });
  document.querySelectorAll("main section[id]").forEach((s) => observador.observe(s));

}

async function iniciar() {
  const [datos, geo] = await Promise.all([
    fetch("data/datos.json").then((r) => r.json()),
    fetch("data/peru_departamentos.geojson").then((r) => r.json()),
  ]);
  D = datos;
  GEO_PERU = geo;
  document.getElementById("fecha-datos").textContent = D.generado.split("-").reverse().join("/");
  prepararVistasTabla();
  renderHallazgos();
  // El mapa necesita existir antes de engancharle el evento de clic
  renderMapa();
  iniciarControles();
  renderTodo();
}

window.addEventListener("DOMContentLoaded", iniciar);
