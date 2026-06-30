# Orgi — Gestión Financiera Personal

Aplicación web para sistematizar, analizar y visualizar extractos bancarios personales (Nequi, Nu, RappiCard).

## Estructura del Proyecto

```
app/                    # Aplicación web Flask
analysis/               # Scripts de análisis y reportes
pipeline/               # Pipeline de ingesta y procesamiento de PDFs
utils/                  # Utilidades (descarga automática, limpieza)
tests/                  # Pruebas unitarias
data/                   # [PRIVADO] PDFs bancarios, inbox
outputs/                # [PRIVADO] Bases de datos, reportes generados
run.py                  # Punto de entrada de la web app
```

## Inicio Rápido

```bash
pip install -r requirements.txt
python run.py
# Abre http://localhost:5000
```

## Módulos

### Web App (`app/`)

Flask con Chart.js. Tres vistas principales:
- **Inicio** — Balance, gráfico de gastos/ingresos por categoría, explorador de transacciones con filtros y navegación por período (día/semana/mes/año/personalizado).
- **Extractos** — Listado de extractos por banco con detalle expandible (metadatos, transacciones, cuotas).
- **Presupuesto / Reportes** — (en desarrollo).

### Pipeline (`pipeline/`)

Automatiza la ingesta de PDFs:

```
data/inbox/ → desbloquear → identificar banco → extraer período →
renombrar → mover a data/{banco}/ → ejecutar análisis →
outputs/db/finanzas_unificadas.db
```

| Script | Función |
|--------|---------|
| `procesar_inbox.py` | Orquestador: procesa inbox y ejecuta pipeline |
| `observar_inbox.py` | Vigilante por polling (5s) |
| `observar_inbox.ps1` | Vigilante por FileSystemWatcher (tiempo real) |
| `construir_bd_unificada.py` | Construye `finanzas_unificadas.db` |
| `construir_bd_final.py` / `_v2.py` | Versiones alternas de construcción |
| `unlock_pdfs.py` | Desbloquea PDFs con contraseña |

### Análisis (`analysis/`)

| Script | Función |
|--------|---------|
| `analisis_unificado.py` | Sistematización unificada (Nequi + Nu + RappiCard) |
| `analisis_completo.py` | Análisis completo con cruces y cuotas |
| `analisis_nequi.py` | Análisis específico para Nequi |
| `analisis_nequi_completo.py` | Análisis Nequi con recurrencias |
| `analisis_tarjetas_completo.py` | Análisis de tarjetas de crédito (Nu, RappiCard) |
| `analyze_pdfs.py` | Escaneo y clasificación de PDFs |
| `mifinanza.py` | Importación desde MyFinance App |

### Utilidades (`utils/`)

| Script | Función |
|--------|---------|
| `auto_descargar_pdfs_gmail.py` | Descarga automática desde Gmail |
| `auto_extractos_nequi.py` | Descarga automática desde Nequi web |
| `cleanup_and_unlock.py` | Limpieza y desbloqueo masivo |

## Uso del Pipeline

### Manual
```bash
python pipeline/procesar_inbox.py
```

### Vigilante automático
Ejecutar `iniciar_observador.bat` (doble clic) o:
```bash
python pipeline/observar_inbox.py
```

## Licencia

Uso personal.
