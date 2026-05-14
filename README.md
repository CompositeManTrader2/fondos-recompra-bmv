# Fondos de Recompra BMV — Tracker Multi-Activo

App de Streamlit para extraer, consolidar y analizar las operaciones de
**fondo de recompra** que las emisoras mexicanas publican en la BMV
(`https://www.bmv.com.mx/docs-pub/recompra/...pdf`).

> Reemplazo del notebook `Modelo_Fondos_de_Recompra_V1_8.ipynb` con
> arquitectura modular, cero dependencias del sistema operativo
> (sin Java/Tabula) y soporte multi-activo desde el día 1.

---

## ✨ Características

- **Carga flexible**: 4 formas de ingestar datos:
  1. Subida directa de PDFs.
  2. Pegado de URLs sucias copiadas de la consola del navegador.
  3. **🤖 Auto-descarga (Playwright)** — escribes la clave (AMXL, GFNORTEO…)
     y la app abre Chromium *headless*, busca y descarga todos los PDFs sola.
  4. **🔖 Bookmarklet** — fallback de un click en tu propio navegador para
     casos con anti-bot/captcha.
- **Parser robusto** (`pdfplumber`): detecta variantes de encabezado
  (`NÚMERO DE ACCIONES`, `PRECIO UNIT.`, etc.), normaliza decimales y
  separadores de miles, deduplica por *folio + fecha + casa*.
- **Almacenamiento por activo**: cada emisora se persiste en
  `data/activos/{TICKER}/operations.parquet`. Puedes cargar y comparar
  cuantos activos quieras.
- **Métricas financieras**: VWAP total / compra / venta a nivel día,
  semana y mes; Herfindahl-Hirschman por casa de bolsa; spread V−C.
- **Comparativo de mercado**: cruce contra Yahoo Finance (sufijo `.MX`)
  o un Excel propio, con alerta de sobreprecio (>1.5%).
- **Multi-activo**: tablero comparativo y heatmap de actividad mensual
  entre tickers.
- **Exportación**: Excel consolidado con hojas `TODAS_OPERACIONES`,
  `DIARIO`, `SEMANAL`, `MENSUAL`, `POR_CASA_BOLSA`, `TOTAL`.

## 🗂️ Estructura

```
fondos-recompra-bmv/
├── app.py                     # Entry point Streamlit (home + selector global)
├── requirements.txt
├── .streamlit/config.toml     # Tema morado consistente
├── src/
│   ├── pdf_parser.py          # Extracción robusta con pdfplumber
│   ├── data_processor.py      # Consolidación + VWAP + agregaciones
│   ├── storage.py             # Persistencia parquet por activo
│   ├── visualizations.py      # Gráficas Plotly (interactivas)
│   ├── bmv_downloader.py      # Descarga directa desde URLs BMV
│   └── market_data.py         # Yahoo Finance opcional
├── pages/
│   ├── 1_📥_Cargar_Datos.py
│   ├── 2_📊_Dashboard.py
│   ├── 3_🏛️_Casas_de_Bolsa.py
│   ├── 4_📈_Comparativo_Mercado.py
│   ├── 5_⚖️_Multi_Activo.py
│   └── 6_⬇️_Exportar.py
└── data/activos/              # Parquets por emisora (autogenerado)
```

## 🏗️ Cómo correrlo localmente

```bash
git clone https://github.com/<tu_usuario>/fondos-recompra-bmv
cd fondos-recompra-bmv
python -m venv .venv && source .venv/bin/activate    # En Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## ☁️ Deploy en Streamlit Cloud

1. Sube el repo a GitHub (este proyecto ya viene listo).
2. Entra a <https://share.streamlit.io> → **New app**.
3. Selecciona el repo, rama `main` y archivo `app.py`.
4. *Advanced settings* → Python 3.11 (recomendado).
5. Deploy. Listo.

> El parquet de `data/activos/` es **efímero** en Streamlit Cloud (se
> reinicia cuando la app duerme). Para persistencia real ver el roadmap
> abajo.

## 🔁 Flujo típico de uso

1. **📥 Cargar Datos** → arrastrar PDFs o pegar URLs BMV.
2. La app detecta la *Clave de cotización* automáticamente y crea el
   activo si no existía.
3. **📊 Dashboard** → KPIs, VWAP diario/semanal/mensual, drilldown.
4. **🏛️ Casas de Bolsa** → concentración (HHI), participación, ranking.
5. **📈 Comparativo Mercado** → VWAP vs precio Yahoo (`AMXL.MX`, etc.).
6. **⚖️ Multi-Activo** → comparar varias emisoras al mismo tiempo.
7. **⬇️ Exportar** → Excel consolidado.

## 🤖 Auto-descarga desde BMV — cómo funciona

La página de BMV es una SPA Angular sin endpoint REST público. Para
automatizar la descarga la app usa **Playwright** (Chromium headless):

1. Pestaña **📥 Cargar Datos → 🤖 Auto-descarga BMV → ⚡ Modo automático**.
2. Escribes la clave (ej. `AMXL`) y la app:
   - Lanza Chromium en modo headless.
   - Navega a `bmv.com.mx/.../simec_documentos_recompra_`.
   - Escribe la clave en el buscador, abre la pestaña Documentos.
   - Pagina y captura todos los `recompra_*.pdf`.
   - Los descarga y los procesa con `pdf_parser`.
3. Si Playwright falla (anti-bot, captcha, IP bloqueada), usa el
   **🔖 modo bookmarklet**: arrastras el JS a tu barra de marcadores y con
   un click desde la página de BMV se descarga `bmv_pdfs.txt` que subes a
   la app. Este fallback siempre funciona porque corre en *tu* navegador.

> En Streamlit Cloud la primera ejecución del modo automático tarda ~30 s
> instalando Chromium. Las siguientes son inmediatas.

## 🛣️ Roadmap

### Mejoras al modelo (prioridad alta)

| Mejora | Por qué importa |
|---|---|
| **Persistencia en Supabase / S3** | Streamlit Cloud reinicia el FS al dormir. Migrar `storage.py` a un bucket. |
| **Refresco automático** del catálogo de la BMV | Hoy hay que pegar URLs; un *job* (cron/GitHub Action) puede listar nuevos PDFs por emisora cada noche. |
| **Detección de outliers de precio** (z-score y MAD) | Marcar trades que se ejecutaron a precios anómalos vs ventana intradía. |
| **Drift VWAP vs intradía** | Compara VWAP del fondo contra el VWAP intradía oficial (Bolsa) — no sólo el cierre. |
| **Atribución por casa** | Qué tanto le cuesta a la emisora cada casa (sobreprecio promedio, tracking error). |
| **Volumen relativo** | Qué porcentaje del volumen total operado en mercado representa la recompra día a día. |
| **Notificaciones** | Telegram/Email cuando un día rompa límites (volumen anómalo, precio fuera de banda). |

### Funcionales

- Comparar dos ventanas (YoY, antes/después de evento corporativo).
- Calendario corporativo (dividendos, splits) overlay en gráficas.
- Forecast simple del importe restante autorizado vs ejecutado.
- Edición manual de operaciones mal parseadas con `st.data_editor`.

### Calidad de código

- Tests unitarios con `pytest` para los helpers numéricos del parser.
- Logger estructurado (loguru) en lugar de `print`.
- Caching con `@st.cache_data` en lecturas pesadas de parquet.

### Nice-to-have

- Modo "auditor": flag de sobreprecio configurable, reporte PDF de cierre.
- Generación automática de PPTX (heredar el flujo `3.x` del notebook).
- Login básico (`streamlit-authenticator`) si se publica en internet.

## 🔧 Notas técnicas

- **Sin Java**: el notebook original usaba `tabula-py`, que requiere Java.
  Streamlit Cloud no lo provee. Aquí toda la extracción de tablas se hace
  con `pdfplumber` con doble estrategia (`lines` → fallback `text`).
- **Encoding**: los nombres de archivo y páginas usan emojis Unicode;
  Streamlit Cloud (Linux) los maneja sin problema.
- **Multi-account de gh**: si tienes varias cuentas, define
  `GH_HOST=github.com` y `gh auth switch` antes de hacer push.

## 📜 Licencia

MIT.
