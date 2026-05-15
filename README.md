# Fondos de Recompra BMV — Tracker Multi-Activo

App de Streamlit para extraer, consolidar y analizar las operaciones de
**fondo de recompra** que las emisoras mexicanas publican en la BMV
(`https://www.bmv.com.mx/docs-pub/recompra/...pdf`).

> Reemplazo del notebook `Modelo_Fondos_de_Recompra_V1_8.ipynb` con
> arquitectura modular, cero dependencias del sistema operativo
> (sin Java/Tabula) y soporte multi-activo desde el día 1.

---

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
