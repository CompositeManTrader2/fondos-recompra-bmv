# BUYB — Monitor de Recompras BMV

App de Streamlit estilo terminal Bloomberg para extraer, consolidar y analizar
las operaciones de **fondo de recompra** que las emisoras mexicanas publican en
la BMV (`https://www.bmv.com.mx/docs-pub/recompra/...pdf`).

> Reemplazo del notebook `Modelo_Fondos_de_Recompra_V1_8.ipynb` con
> arquitectura modular, cero dependencias del sistema operativo
> (sin Java/Tabula) y soporte multi-activo desde el día 1.

---

## 🖥️ Monitor de mercado + scanner diario automático

**Todas** las emisoras de la BMV, sin que tengas que pedirlas una por una.

| Pieza | Qué hace |
|---|---|
| `.github/workflows/daily_scan.yml` | Corre **20:30 y 09:30 CDMX, lun–vie** en GitHub Actions (gratis en repos públicos). |
| `src/daily_scanner.py` | Recorre los IDs de documento de BMV (`recompra_{ID}_1.pdf`, ~320 IDs/día hábil) desde el último conocido: si la URL es un PDF, es una recompra (de cualquier emisora). Descarga en paralelo, parsea, y guarda. |
| `data/daily/resumen_diario.parquet` | Una fila por (fecha, emisora): importe, operaciones, acciones, VWAP total/compra/venta, casas, remanente del fondo. |
| `data/daily/documentos.parquet` | Registro de cada PDF procesado (idempotencia + auditoría con link al PDF). |
| `data/activos/{EMISORA}/` | Las operaciones de cada emisora, disponibles en el Dashboard individual. |
| `views/monitor.py` | Pantalla **BUYB &lt;GO&gt;**: cinta, KPIs del día, ranking (clic → dashboard), treemap, actividad apilada del mercado, heatmap emisora × sesión, historial, rankings, estado del scanner. |

**Robustez del scanner**
- Re-revisa los últimos 800 IDs en cada corrida (PDFs publicados tarde).
- Frontera adaptativa: si un feriado deja un hueco largo sin recompras, la ventana se duplica en la siguiente corrida.
- Presupuesto de tiempo por corrida: si no termina, guarda avance y la siguiente continúa.
- Si otro commit entra mientras escanea, reinicia sobre `origin/main` y re-ejecuta (idempotente).

**Backfill histórico**: *Actions → Scanner diario de recompras BMV → Run workflow*, con
`seed_id` de un ID antiguo (≈320 IDs por día hábil; `1540000` ≈ mar-2026) y `max_minutos` hasta 300.

**Local**: `python scripts/daily_scan.py` (o `--rebuild-only` para recalcular el resumen).

> GitHub desactiva los workflows programados tras 60 días sin actividad en el repo; los
> commits diarios del scanner cuentan como actividad.

## 🎨 Diseño · identidad Punto Casa de Bolsa

Colores muestreados del reporte oficial: morado `#7030A0`, lavanda `#ECDEF5`, gris
`#949BA1`. Tipografía Fira Sans / Fira Code. La paleta de gráficas (morado de marca
primero, gris de marca para "OTRAS") y el par compra/venta están validados para
daltonismo y contraste sobre blanco (`src/theme.py`). Nunca doble eje Y: medidas de
escala distinta van en paneles apilados. Ejes diarios sin fines de semana.

**Logotipo oficial**: coloca el archivo como `assets/logo_punto.png` (o `.svg`) y la
app, el reporte HTML y el Excel lo usan automáticamente. Sin archivo se muestra un
wordmark de texto.

### Pantallas

| Grupo | Pantalla | Para qué |
|---|---|---|
| Mercado | **Resumen** | Indicadores de la sesión, señales (volumen inusual, aceleración, inician/reanudan, prima vs cierre, pausa, fondo por agotarse, venta neta) y tablero de emisoras con métricas de decisión. |
| Mercado | **Buyback Activity** | Réplica del reporte diario de Punto (TRADE DATE · STOCK · BROKER · B/S · SHARES · AVG PRICE · GROSS MXN), por fecha de reporte u operación. Descarga Excel con el mismo formato y HTML para correo. |
| Mercado | **Casas de bolsa** | Liga de intermediarios, participación de Punto y su evolución, matriz emisora × casa y emisoras que recompran con otras casas (oportunidades comerciales). |
| Mercado | **Rankings e historial** | Ranking por importe/sesiones y consulta histórica descargable. |
| Emisora | Dashboard, Intermediarios, VWAP vs mercado, Exportar | Análisis individual. |
| Herramientas | Multi-activo, Cargar datos, Estado del scanner | |

### Métricas de decisión (Resumen)

- **× prom. 20**: importe de la sesión / promedio de sus 20 sesiones previas.
- **Aceleración**: ritmo de 5 sesiones / ritmo de 20.
- **% del volumen**: acciones recompradas / volumen del mercado (Yahoo Finance).
- **vs cierre**: VWAP de compra vs cierre del día (negativo = compró abajo del cierre).
- **% circulación**: acciones recompradas en 20 sesiones / acciones en circulación (del PDF).
- **Fondo para**: sesiones de remanente al ritmo actual.

## ✨ Características

- **Carga flexible**: 3 formas de ingestar datos:
  1. **🤖 Auto-descarga directa** — escribes la clave (AMX, BIMBO,
     WALMEX…) y la app baja todos los PDFs de recompra usando la API
     REST interna de BMV. **Sin navegador, sin Playwright.**
  2. Subida directa de PDFs.
  3. Pegado de URLs sucias o bookmarklet de respaldo.
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
├── app.py                     # Router (st.navigation) + sidebar común
├── views/monitor.py           # BUYB <GO>: monitor de mercado
├── scripts/daily_scan.py      # CLI del scanner diario
├── .github/workflows/daily_scan.yml
├── requirements.txt           # App
├── requirements-scanner.txt   # Scanner (sin Streamlit)
├── .streamlit/config.toml     # Tema oscuro terminal
├── src/
│   ├── theme.py               # Paleta validada, template Plotly "bbg", CSS, componentes
│   ├── daily_scanner.py       # Scanner de toda la BMV por ID de documento
│   ├── market_store.py        # Lectura de data/daily para la app
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
└── data/
    ├── activos/               # Parquets por emisora (autogenerado)
    └── daily/                 # Resumen de mercado + registro de documentos (scanner)
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
5. **Configura los secrets para persistencia** (ver siguiente sección).
6. Deploy.

## 💾 Persistencia con GitHub auto-commit

Streamlit Cloud reinicia el filesystem cuando la app duerme. Para que
los datos sobrevivan, la app commitea automáticamente los parquets al
mismo repo de GitHub.

### Setup (5 minutos, una sola vez)

**1. Crear un Personal Access Token** en GitHub:

   - Ve a <https://github.com/settings/tokens?type=beta> (Fine-grained token).
   - **Repository access** → *Only select repositories* → tu repo
     `fondos-recompra-bmv`.
   - **Repository permissions** → `Contents: Read and write`.
   - Expiration: 1 año.
   - Click **Generate token** y **copia el token** (empieza con
     `github_pat_...`).

**2. Configurar el secret en Streamlit Cloud:**

   - Entra a tu app en <https://share.streamlit.io>.
   - **⋮ → Settings → Secrets**.
   - Pega:

```toml
[github]
token = "github_pat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
repo  = "TU_USUARIO/fondos-recompra-bmv"
branch = "main"
base_path = "data/activos"
author_name = "App Recompras"
author_email = "noreply@example.com"
```

   - Click **Save** → la app reinicia sola.

**3. Verifica:** abre la app, en el sidebar debe decir
**💾 Persistencia: GitHub**. Si dice "Local (efímera)" revisa que el
secret esté bien escrito.

### ¿Cómo funciona?

- Cada vez que cargas/procesas PDFs nuevos, el `parquet` consolidado se
  empuja vía la GitHub Contents API a `data/activos/{TICKER}/operations.parquet`.
- Cada cambio = un commit con mensaje
  `data(TICKER): N ops`.
- El índice de activos vive en `data/activos/_index.json`.
- Cuando la app reinicia, lee primero de GitHub y reconstruye el estado.

### Modo local (sin secret)

Si no configuras el secret, la app cae automáticamente al filesystem
local (`data/activos/`). Útil para desarrollo. Verás un warning amarillo
en el sidebar.

## 🔁 Flujo típico de uso

1. **📥 Cargar Datos** → arrastrar PDFs o pegar URLs BMV.
2. La app detecta la *Clave de cotización* automáticamente y crea el
   activo si no existía.
3. **📊 Dashboard** → KPIs, VWAP diario/semanal/mensual, drilldown.
4. **🏛️ Casas de Bolsa** → concentración (HHI), participación, ranking.
5. **📈 Comparativo Mercado** → VWAP vs precio Yahoo (`AMXL.MX`, etc.).
6. **⚖️ Multi-Activo** → comparar varias emisoras al mismo tiempo.
7. **⬇️ Exportar** → Excel consolidado.

## 🤖 Auto-descarga desde BMV — 100% automática

La página `bmv.com.mx/.../simec_documentos_recompra_` es una SPA Nuxt.js,
pero internamente usa una **API REST WSO2** que descubrí leyendo el bundle
JS público de BMV. La app llama directamente a esa API:

```
GET   https://www.bmv.com.mx/rest/tokenservice/token?grant_type=client_credentials
POST  https://www.bmv.com.mx/api/searchservice/v1
       body: { lang, payload:{term, term2, termT, searchType:"busquedaDocumentosPorInstrumentos"},
               requestJson: <ag-grid request serialized> }
```

Las credenciales OAuth2 están **embebidas en el frontend público** (uso
legítimo del cliente), por lo que cualquier integración cliente-side
puede usarlas. La respuesta trae documentos de todos los tipos; filtramos
por `cve_tipo_documento == "recompra"` y `cve_empresa == <clave>`.

**Cómo se usa:**

1. Pestaña **📥 Cargar Datos → 🤖 Auto-descarga BMV**.
2. Escribes la clave (ej. `AMX`, `BIMBO`, `WALMEX`).
3. Click en **⚡ Ejecutar auto-descarga**.
4. La app:
   - Pide token OAuth a `tokenservice/token`.
   - Pagina la API REST hasta cubrir todos los PDFs de recompra.
   - Descarga cada PDF directamente del CDN (`docs-pub/recompra/...`).
   - Los procesa con `pdf_parser` y guarda el activo.

> No requiere Playwright, Chromium, navegador o copy-paste. Funciona en
> Streamlit Cloud sin configuración extra.

Como respaldo (si BMV cambia su API), la pestaña incluye un
**bookmarklet** que recolecta los PDFs desde tu navegador.

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
