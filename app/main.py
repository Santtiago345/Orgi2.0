from flask import Flask, jsonify, render_template, request
from datetime import datetime, date
import json, os, subprocess, sys

from .database import (
    calcular_balance, obtener_rango_fechas, navegar_periodo, es_periodo_actual,
    obtener_transacciones_por_periodo, obtener_gastos_por_categoria,
    agregar_transaccion, obtener_ultima_fecha, obtener_extractos,
    buscar_extracto_duplicado, obtener_extracto_detalle,
    obtener_cuota_info,
    obtener_etiquetas, crear_etiqueta, actualizar_etiqueta, eliminar_etiqueta,
    obtener_etiquetas_transaccion, asignar_etiqueta, quitar_etiqueta,
    obtener_categorias_lista, obtener_transacciones_por_categoria,
    obtener_perfil_crediticia, obtener_prestamos_nequi,
    actualizar_nota, actualizar_categoria_tx,
    renombrar_categoria, obtener_config_categorias, guardar_config_categoria,
    obtener_presupuestos, guardar_presupuesto, eliminar_presupuesto,
    obtener_resumen_presupuesto,
    obtener_tendencia_mensual, obtener_comparativa_anual,
    obtener_top_gastos, obtener_resumen_anual,
    obtener_sin_cruzar, obtener_sugerencias_cruce,
    cruzar_transaccion, obtener_estadisticas_cruce,
)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)

PAGINAS = [
    {"id": "inicio", "nombre": "Inicio", "ruta": "/"},
    {"id": "extractos", "nombre": "Extractos", "ruta": "/extractos"},
    {"id": "categorias", "nombre": "Categorias", "ruta": "/categorias"},
    {"id": "creditos", "nombre": "Creditos", "ruta": "/creditos"},
    {"id": "presupuesto", "nombre": "Presupuesto", "ruta": "/presupuesto"},
    {"id": "reportes", "nombre": "Reportes", "ruta": "/reportes"},
    {"id": "cruce", "nombre": "Cruce", "ruta": "/cruce"},
]

CATEGORIAS = [
    {"id": "Comida", "icono": "\U0001f37d\ufe0f", "color": "#FF6384"},
    {"id": "Transporte", "icono": "\U0001f697", "color": "#36A2EB"},
    {"id": "Servicios", "icono": "\U0001f4a1", "color": "#FFCE56"},
    {"id": "Ropa", "icono": "\U0001f455", "color": "#4BC0C0"},
    {"id": "Entretenimiento", "icono": "\U0001f3ac", "color": "#9966FF"},
    {"id": "Salud", "icono": "\U0001f3e5", "color": "#FF9F40"},
    {"id": "Educacion", "icono": "\U0001f4da", "color": "#7BC8A4"},
    {"id": "Tecnologia", "icono": "\U0001f4bb", "color": "#E7E9EB"},
    {"id": "Viajes", "icono": "\u2708\ufe0f", "color": "#F7464A"},
    {"id": "Ingreso familiar", "icono": "\U0001f468\u200d\U0001f469\u200d\U0001f467", "color": "#46BFBD"},
    {"id": "Salario", "icono": "\U0001f4b0", "color": "#FDB45C"},
    {"id": "Sin clasificar", "icono": "\u2753", "color": "#C9CBCF"},
    {"id": "Compras general", "icono": "\U0001f6d2", "color": "#A8E6CF"},
    {"id": "Cargos financieros", "icono": "\U0001f3e6", "color": "#D4A5A5"},
    {"id": "Varios", "icono": "\U0001f4e6", "color": "#B0B0B0"},
]


def formatear_pesos(valor):
    negativo = valor < 0
    s = f"{abs(valor):,.0f}".replace(",", ".")
    return f"-${s}" if negativo else f"${s}"

def formatear_pesos_linea(valor):
    negativo = valor < 0
    s = f"{abs(valor):,.0f}".replace(",", ".")
    return f"-${s}" if negativo else f"${s}"

def icono_categoria(cat):
    for c in CATEGORIAS:
        if c["id"] == cat:
            return c["icono"]
    return "\U0001f4cc"

def color_categoria(cat):
    for c in CATEGORIAS:
        if c["id"] == cat:
            return c["color"]
    return "#C9CBCF"

@app.context_processor
def inject_globals():
    balance, ingresos, gastos = calcular_balance()
    return {
        "paginas": PAGINAS,
        "pagina_actual": request.path,
        "balance": balance,
        "balance_fmt": formatear_pesos(balance),
        "total_ingresos_fmt": formatear_pesos(ingresos),
        "total_gastos_fmt": formatear_pesos(gastos),
        "categorias": CATEGORIAS,
        "icono_categoria": icono_categoria,
    }


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/extractos")
def extractos():
    return render_template("extractos.html")

@app.route("/categorias")
def categorias_page():
    return render_template("categorias.html")

@app.route("/creditos")
def creditos_page():
    return render_template("creditos.html")

@app.route("/presupuesto")
def presupuesto_page():
    return render_template("presupuesto.html")

@app.route("/reportes")
def reportes_page():
    return render_template("reportes.html")

@app.route("/cruce")
def cruce_page():
    return render_template("cruce.html")


# ─── API: RESUMEN ──────────────────────────────────────────

@app.route("/api/resumen")
def api_resumen():
    tipo = request.args.get("tipo", "gastos")
    periodo = request.args.get("periodo", "mes")
    desde_str = request.args.get("desde")
    hasta_str = request.args.get("hasta")

    desde = hasta = None
    if periodo == "personalizado" and desde_str and hasta_str:
        try:
            desde = date.fromisoformat(desde_str)
            hasta = date.fromisoformat(hasta_str)
        except:
            pass

    if not desde or not hasta:
        desde, hasta = obtener_rango_fechas(periodo)

    # Si el período actual no tiene transacciones, intentar tomar el último periodo con datos
    txs = obtener_transacciones_por_periodo(tipo, desde, hasta)
    if len(txs) == 0:
        try:
            ultima = obtener_ultima_fecha()
            if ultima:
                # soportar ISO (YYYY-MM-DD) o DD/MM/YYYY
                try:
                    yy, mm, dd = ultima.split('-')
                    y = int(yy); m = int(mm)
                except Exception:
                    from datetime import datetime
                    dt = datetime.strptime(ultima, "%d/%m/%Y")
                    y = dt.year; m = dt.month
                # construir desde/hasta para el mes de la última transacción
                desde = date(y, m, 1)
                import calendar
                last = calendar.monthrange(y, m)[1]
                hasta = date(y, m, last)
        except Exception:
            pass

    return api_resumen_params(tipo, periodo, desde, hasta)


@app.route("/api/navegar")
def api_navegar():
    tipo = request.args.get("tipo", "gastos")
    periodo = request.args.get("periodo", "mes")
    desde_str = request.args.get("desde")
    hasta_str = request.args.get("hasta")
    direccion = int(request.args.get("dir", "0"))

    desde = date.fromisoformat(desde_str) if desde_str else date.today()
    hasta = date.fromisoformat(hasta_str) if hasta_str else date.today()

    if direccion != 0:
        desde, hasta = navegar_periodo(periodo, desde, hasta, direccion)

    return api_resumen_params(tipo, periodo, desde, hasta)


def deduplicar_cuotas(transacciones):
    grupos = {}
    for t in transacciones:
        # Don't deduplicate cuota transactions (show each cuota individually)
        if t.get("es_cuota"):
            continue
        key = (t["entidad"], t["descripcion"].strip().lower(), round(abs(t["valor"]), 2))
        grupos.setdefault(key, []).append(t)
    result = [t for t in transacciones if t.get("es_cuota")]
    for key, group in grupos.items():
        if len(group) > 1:
            t = dict(group[0])
            t["descripcion"] = f"{t['descripcion']} (x{len(group)})"
            result.append(t)
        else:
            result.append(group[0])
    return result


def api_resumen_params(tipo, periodo, desde, hasta):
    categorias = obtener_gastos_por_categoria(tipo, desde, hasta)
    transacciones = obtener_transacciones_por_periodo(tipo, desde, hasta)
    total = sum(c["total"] for c in categorias)
    es_actual = es_periodo_actual(periodo, desde, hasta)

    cuota_info = obtener_cuota_info()
    for t in transacciones:
        ci = cuota_info.get(t["id"])
        t["es_cuota"] = ci is not None and ci["total_cuotas"] > 1
        if ci and ci["total_cuotas"] > 1:
            t["cuota_info"] = ci
            t["valor_original"] = ci["valor_total"]

    transacciones_dedup = deduplicar_cuotas(transacciones)

    return jsonify({
        "total": round(total),
        "total_fmt": formatear_pesos(total),
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "categorias": [{
            **c,
            "total": round(c["total"]),
            "porcentaje": round(c["total"] / total * 100, 1) if total > 0 else 0,
            "icono": icono_categoria(c["categoria"]),
            "color": color_categoria(c["categoria"])
        } for c in categorias],
        "transacciones": [
            {**t, "valor_fmt": formatear_pesos(t["valor"]),
             "valor_original_fmt": formatear_pesos(t["valor_original"]) if t.get("valor_original") else None}
            for t in transacciones_dedup
        ],
        "cuota_info": cuota_info,
        "num_transacciones": len(transacciones_dedup),
        "es_actual": es_actual,
    })


@app.route("/api/ultima-fecha")
def api_ultima_fecha():
    return jsonify({"fecha": obtener_ultima_fecha()})


@app.route("/api/transacciones", methods=["POST"])
def api_agregar_transaccion():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Datos requeridos"}), 400

    fecha = data.get("fecha", date.today().isoformat())
    descripcion = data.get("descripcion", "").strip()
    try:
        valor = float(data.get("valor", 0))
    except Exception:
        return jsonify({"error": "Valor inválido"}), 400
    categoria = data.get("categoria", "Varios").strip()
    tipo = data.get("tipo", "gasto")
    notas = data.get("notas", "").strip()
    metodo_pago = data.get("metodo_pago", "transferencia")

    if not descripcion or valor == 0:
        return jsonify({"error": "Descripcion y valor diferentes de 0 requeridos"}), 400

    new_id = agregar_transaccion(fecha, descripcion, valor, categoria, tipo, notas, metodo_pago=metodo_pago)
    balance, ing, gas = calcular_balance()
    return jsonify({
        "ok": True, "id": new_id,
        "balance_fmt": formatear_pesos(balance),
        "ingresos_fmt": formatear_pesos(ing),
        "gastos_fmt": formatear_pesos(gas),
    })


# ─── API: EXTRACTOS ────────────────────────────────────────

@app.route("/api/extractos")
def api_extractos():
    extractos = obtener_extractos()
    return jsonify(extractos)


@app.route("/api/extracto/<int:extracto_id>")
def api_extracto_detalle(extracto_id):
    data = obtener_extracto_detalle(extracto_id)
    if not data:
        return jsonify({"error": "Extracto no encontrado"}), 404

    extr = data["extracto"]
    es_tc = extr["fuente"] in ("rappicard", "nu")
    tc_meta = None
    if es_tc:
        tc_meta = {
            "total_pagar": extr.get("total_pagar"),
            "total_pagar_fmt": formatear_pesos(extr["total_pagar"]) if extr.get("total_pagar") else None,
            "pago_minimo": extr.get("pago_minimo"),
            "pago_minimo_fmt": formatear_pesos(extr["pago_minimo"]) if extr.get("pago_minimo") else None,
            "cupo_total": extr.get("cupo_total"),
            "cupo_total_fmt": formatear_pesos(extr["cupo_total"]) if extr.get("cupo_total") else None,
            "saldo_anterior": extr.get("saldo_anterior"),
            "saldo_anterior_fmt": formatear_pesos(extr["saldo_anterior"]) if extr.get("saldo_anterior") else None,
            "saldo_actual": extr.get("saldo_actual"),
            "saldo_actual_fmt": formatear_pesos(extr["saldo_actual"]) if extr.get("saldo_actual") else None,
            "total_cargos": extr.get("total_cargos"),
            "total_abonos": extr.get("total_abonos"),
            "fecha_corte": extr.get("fecha_corte"),
            "fecha_pago": extr.get("fecha_pago"),
        }

    return jsonify({
        "id": extr["id"],
        "archivo": extr["archivo"],
        "fuente": extr["fuente"],
        "tipo": extr["tipo"],
        "periodo": extr["periodo"],
        "titular": extr["titular"],
        "num_transacciones": extr["num_transacciones"],
        "es_tarjeta_credito": es_tc,
        "tc_meta": tc_meta,
        "transacciones": [
            {**t, "valor_fmt": formatear_pesos_linea(t["valor"]),
             "es_cuota": any(
                 c["descripcion"] == t["descripcion"] and abs(c["valor"]) == abs(t["valor"])
                 for c in data["cuotas"]
             )}
            for t in data["transacciones"]
        ],
        "ingresos": [
            {**t, "valor_fmt": formatear_pesos_linea(t["valor"])}
            for t in data["ingresos"]
        ],
        "gastos": [
            {**t, "valor_fmt": formatear_pesos_linea(t["valor"])}
            for t in data["gastos"]
        ],
        "total_ingresos": data["total_ingresos"],
        "total_ingresos_fmt": formatear_pesos(data["total_ingresos"]),
        "total_gastos": data["total_gastos"],
        "total_gastos_fmt": formatear_pesos(data["total_gastos"]),
        "num_ingresos": data["num_ingresos"],
        "num_gastos": data["num_gastos"],
        "num_cuotas": data["num_cuotas"],
    })


@app.route("/api/upload-pdf", methods=["POST"])
def api_upload_pdf():
    if "pdf" not in request.files:
        return jsonify({"error": "No se envi\u00f3 ning\u00fan archivo"}), 400

    file = request.files["pdf"]
    if file.filename == "":
        return jsonify({"error": "Nombre de archivo vac\u00edo"}), 400

    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Solo se aceptan archivos PDF"}), 400

    if buscar_extracto_duplicado(file.filename):
        return jsonify({"error": "Este extracto ya existe en la base de datos", "duplicado": True}), 409

    inbox_dir = os.path.join(BASE, "data", "inbox")
    os.makedirs(inbox_dir, exist_ok=True)
    ruta_pdf = os.path.join(inbox_dir, file.filename)

    contador = 0
    base, ext = os.path.splitext(file.filename)
    while os.path.exists(ruta_pdf):
        contador += 1
        ruta_pdf = os.path.join(inbox_dir, f"{base}_{contador}{ext}")

    file.save(ruta_pdf)
    real_name = os.path.basename(ruta_pdf)

    try:
        result = subprocess.run(
            [sys.executable, os.path.join(BASE, "pipeline", "procesar_inbox.py")],
            capture_output=True, text=True, timeout=300
        )
        output = result.stdout + result.stderr
        success = result.returncode == 0
    except Exception as e:
        output = str(e)
        success = False

    info = {"archivo_original": file.filename, "archivo_real": real_name, "success": success}
    # Incluir logs del pipeline (líneas finales) para mostrar al usuario
    try:
        lines = [l for l in output.splitlines() if l.strip()]
        info["logs"] = lines[-40:]
    except Exception:
        info["logs"] = []
    if success:
        extractos = obtener_extractos()
        if extractos:
            ultimo = extractos[0]
            info["banco"] = ultimo["fuente"]
            info["periodo"] = ultimo["periodo"]
            info["tipo"] = "tarjeta_credito" if ultimo["fuente"] in ("nu", "rappicard") else "cuenta_corriente"
    else:
        info["error"] = output.strip().splitlines()[-1] if output else "Error al procesar el PDF"
        # also include full output in case caller wants more detail
        info["output_full"] = output

    return jsonify(info)


# ─── API: ETIQUETAS ─────────────────────────────────────────

@app.route("/api/etiquetas")
def api_etiquetas():
    return jsonify(obtener_etiquetas())

@app.route("/api/etiquetas", methods=["POST"])
def api_crear_etiqueta():
    data = request.get_json()
    nombre = data.get("nombre", "").strip()
    color = data.get("color", "#6B7280")
    if not nombre:
        return jsonify({"error": "Nombre requerido"}), 400
    new_id, err = crear_etiqueta(nombre, color)
    if err:
        return jsonify({"error": err}), 409
    return jsonify({"ok": True, "id": new_id})

@app.route("/api/etiquetas/<int:eid>", methods=["PUT"])
def api_actualizar_etiqueta(eid):
    data = request.get_json()
    nombre = data.get("nombre", "").strip()
    color = data.get("color", "#6B7280")
    if not nombre:
        return jsonify({"error": "Nombre requerido"}), 400
    if actualizar_etiqueta(eid, nombre, color):
        return jsonify({"ok": True})
    return jsonify({"error": "No encontrada"}), 404

@app.route("/api/etiquetas/<int:eid>", methods=["DELETE"])
def api_eliminar_etiqueta(eid):
    if eliminar_etiqueta(eid):
        return jsonify({"ok": True})
    return jsonify({"error": "No encontrada"}), 404

@app.route("/api/transacciones/<int:tid>/etiquetas", methods=["GET"])
def api_obtener_etiquetas_tx(tid):
    from .database import get_db
    conn = get_db()
    tags = obtener_etiquetas_transaccion(conn, tid)
    conn.close()
    return jsonify(tags)

@app.route("/api/transacciones/<int:tid>/etiquetas", methods=["POST"])
def api_asignar_etiqueta(tid):
    data = request.get_json()
    eid = data.get("etiqueta_id")
    if not eid:
        return jsonify({"error": "etiqueta_id requerido"}), 400
    if asignar_etiqueta(tid, eid):
        return jsonify({"ok": True})
    return jsonify({"error": "Ya asignada"}), 409

@app.route("/api/transacciones/<int:tid>/etiquetas/<int:eid>", methods=["DELETE"])
def api_quitar_etiqueta(tid, eid):
    if quitar_etiqueta(tid, eid):
        return jsonify({"ok": True})
    return jsonify({"error": "No encontrada"}), 404

@app.route("/api/transacciones/<int:tid>/notas", methods=["PUT"])
def api_actualizar_nota(tid):
    data = request.get_json()
    notas = data.get("notas", "")
    if actualizar_nota(tid, notas):
        return jsonify({"ok": True})
    return jsonify({"error": "No encontrada"}), 404

@app.route("/api/transacciones/<int:tid>/categoria", methods=["PUT"])
def api_actualizar_categoria_tx(tid):
    data = request.get_json()
    categoria = data.get("categoria", "").strip()
    if not categoria:
        return jsonify({"error": "Categoria requerida"}), 400
    if actualizar_categoria_tx(tid, categoria):
        return jsonify({"ok": True})
    return jsonify({"error": "No encontrada"}), 404


# ─── API: CATEGORIAS ────────────────────────────────────────

@app.route("/api/categorias")
def api_categorias():
    return jsonify(obtener_categorias_lista())

@app.route("/api/categorias/transacciones")
def api_categorias_transacciones():
    categoria = request.args.get("categoria", "")
    desde_str = request.args.get("desde")
    hasta_str = request.args.get("hasta")
    metodo_pago = request.args.get("metodo_pago")
    orden = request.args.get("orden", "fecha")
    desc = request.args.get("desc", "true") == "true"

    desde = hasta = None
    if desde_str:
        desde = date.fromisoformat(desde_str)
    if hasta_str:
        hasta = date.fromisoformat(hasta_str)

    txs = obtener_transacciones_por_categoria(categoria, desde, hasta, metodo_pago, orden, desc)
    cuota_info = obtener_cuota_info()
    for t in txs:
        ci = cuota_info.get(t["id"])
        t["es_cuota"] = ci is not None and ci["total_cuotas"] > 1
        if ci and ci["total_cuotas"] > 1:
            t["cuota_info"] = ci
    total = round(sum(abs(t["valor"]) for t in txs))
    return jsonify({
        "transacciones": [{**t, "valor_fmt": formatear_pesos(t["valor"])} for t in txs],
        "total": total,
        "total_fmt": formatear_pesos(total),
        "num_transacciones": len(txs),
    })


@app.route("/api/categorias/rename", methods=["POST"])
def api_renombrar_categoria():
    data = request.get_json()
    viejo = data.get("viejo", "").strip()
    nuevo = data.get("nuevo", "").strip()
    if not viejo or not nuevo:
        return jsonify({"error": "Se requieren nombre viejo y nuevo"}), 400
    cambios = renombrar_categoria(viejo, nuevo)
    return jsonify({"ok": True, "cambios": cambios})


@app.route("/api/categorias/config", methods=["GET"])
def api_obtener_config_categorias():
    return jsonify(obtener_config_categorias())


@app.route("/api/categorias/config", methods=["PUT"])
def api_guardar_config_categoria():
    data = request.get_json()
    nombre = data.get("nombre", "").strip()
    icono = data.get("icono", "")
    color = data.get("color", "#C9CBCF")
    if not nombre:
        return jsonify({"error": "Nombre requerido"}), 400
    guardar_config_categoria(nombre, icono, color)
    return jsonify({"ok": True})


# ─── API: PRESUPUESTOS ─────────────────────────────────────

@app.route("/api/presupuestos")
def api_presupuestos():
    return jsonify(obtener_presupuestos())

@app.route("/api/presupuestos", methods=["POST"])
def api_guardar_presupuesto():
    data = request.get_json()
    categoria = data.get("categoria", "").strip()
    try:
        monto = float(data.get("monto", 0))
        mes = int(data.get("mes", 0))
        anio = int(data.get("anio", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Monto, mes y anio requeridos"}), 400
    if not categoria or monto <= 0 or mes < 1 or mes > 12 or anio < 2000:
        return jsonify({"error": "Datos invalidos"}), 400
    new_id = guardar_presupuesto(categoria, monto, mes, anio)
    return jsonify({"ok": True, "id": new_id})

@app.route("/api/presupuestos/<int:pid>", methods=["DELETE"])
def api_eliminar_presupuesto(pid):
    if eliminar_presupuesto(pid):
        return jsonify({"ok": True})
    return jsonify({"error": "No encontrado"}), 404

@app.route("/api/presupuestos/resumen")
def api_resumen_presupuesto():
    try:
        mes = int(request.args.get("mes", 0))
        anio = int(request.args.get("anio", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "mes y anio requeridos"}), 400
    if mes < 1 or mes > 12 or anio < 2000:
        return jsonify({"error": "Parametros invalidos"}), 400
    data = obtener_resumen_presupuesto(mes, anio)
    for d in data:
        d["icono"] = icono_categoria(d["categoria"])
        d["color"] = color_categoria(d["categoria"])
    return jsonify(data)


# ─── API: REPORTES ─────────────────────────────────────────

@app.route("/api/reportes/tendencia")
def api_tendencia_mensual():
    try:
        meses = int(request.args.get("meses", 12))
    except (TypeError, ValueError):
        meses = 12
    return jsonify(obtener_tendencia_mensual(meses))

@app.route("/api/reportes/comparativa")
def api_comparativa_anual():
    try:
        anio = int(request.args.get("anio", 0))
    except (TypeError, ValueError):
        anio = 0
    if anio < 2000:
        from datetime import date
        anio = date.today().year
    data = obtener_comparativa_anual(anio)
    for d in data:
        d["icono"] = icono_categoria(d["categoria"])
        d["color"] = color_categoria(d["categoria"])
    return jsonify(data)

@app.route("/api/reportes/top-gastos")
def api_top_gastos():
    try:
        limite = int(request.args.get("limite", 10))
    except (TypeError, ValueError):
        limite = 10
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")
    data = obtener_top_gastos(limite, desde, hasta)
    for d in data:
        d["icono"] = icono_categoria(d["categoria"])
        d["color"] = color_categoria(d["categoria"])
    return jsonify(data)

@app.route("/api/reportes/resumen-anual")
def api_resumen_anual():
    try:
        anio = int(request.args.get("anio", 0))
    except (TypeError, ValueError):
        anio = 0
    if anio < 2000:
        from datetime import date
        anio = date.today().year
    return jsonify(obtener_resumen_anual(anio))


# ─── API: CRUCE ────────────────────────────────────────────

@app.route("/api/cruce/sin-cruzar")
def api_cruce_sin_cruzar():
    entidad = request.args.get("entidad")
    categoria = request.args.get("categoria")
    try:
        limite = int(request.args.get("limite", 50))
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        limite, offset = 50, 0
    data = obtener_sin_cruzar(entidad, categoria, limite, offset)
    for t in data["transacciones"]:
        t["valor_fmt"] = formatear_pesos(t["valor"])
    return jsonify(data)


@app.route("/api/cruce/sugerencias/<int:tx_id>")
def api_cruce_sugerencias(tx_id):
    sugerencias = obtener_sugerencias_cruce(tx_id)
    for s in sugerencias:
        s["valor_fmt"] = formatear_pesos(s["valor"])
    return jsonify(sugerencias)


@app.route("/api/cruce/cruzar", methods=["POST"])
def api_cruce_cruzar():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Datos requeridos"}), 400
    tx_id_bancaria = data.get("tx_id_bancaria")
    tx_id_myfinance = data.get("tx_id_myfinance")
    if not tx_id_bancaria or not tx_id_myfinance:
        return jsonify({"error": "tx_id_bancaria y tx_id_myfinance requeridos"}), 400
    if cruzar_transaccion(tx_id_bancaria, tx_id_myfinance):
        return jsonify({"ok": True})
    return jsonify({"error": "Error al cruzar transacciones"}), 500


@app.route("/api/cruce/estadisticas")
def api_cruce_estadisticas():
    return jsonify(obtener_estadisticas_cruce())


# ─── API: PERFIL CREDITICIO ────────────────────────────

@app.route("/api/perfil-crediticio")
def api_perfil_crediticio():
    data = obtener_perfil_crediticia()
    import calendar as _cal
    from datetime import date as _date

    hoy = _date.today()
    for t in data["tarjetas"]:
        # Calcular si el extracto está al día (mismo mes y año o no)
        anio_ext = t.get('ultimo_anio') or 0
        mes_ext = t.get('ultimo_mes') or 0
        t["extracto_actualizado"] = (anio_ext == hoy.year and mes_ext == hoy.month)
        t["periodo_extracto"] = f"{mes_ext:02d}/{anio_ext}" if anio_ext else "—"

        deuda = t.get("deuda_total") or 0
        t["deuda_total"] = round(deuda)
        t["deuda_total_fmt"] = formatear_pesos(round(deuda))
        t["pago_minimo_total"] = round(t.get("pago_minimo_total") or 0)
        t["pago_minimo_total_fmt"] = formatear_pesos(t["pago_minimo_total"])
        cupo = t.get("cupo_total") or 0
        t["cupo_total"] = round(cupo)
        t["cupo_total_fmt"] = formatear_pesos(t["cupo_total"])
        t["utilizacion"] = round(deuda / cupo * 100, 1) if cupo > 0 else 0
        t["fecha_corte"] = t.get("fecha_corte") or "—"
        t["fecha_pago"] = t.get("fecha_pago") or "—"

    for e in data["extractos"]:
        for k in ("total_pagar", "pago_minimo", "cupo_total", "saldo_anterior",
                  "saldo_actual", "total_cargos", "total_abonos",
                  "interes_corriente", "tasa_mensual", "tasa_anual_ea"):
            if e.get(k) is not None:
                e[k] = round(e[k], 2)
    return jsonify(data)


@app.route("/api/prestamos-nequi")
def api_prestamos_nequi():
    prestamos = obtener_prestamos_nequi()
    for p in prestamos:
        p['monto_prestado_fmt'] = formatear_pesos(p['monto_prestado'])
        p['total_pagado_fmt'] = formatear_pesos(p['total_pagado'])
        p['saldo_pendiente_fmt'] = formatear_pesos(p['saldo_pendiente'])
        pct = p['total_pagado'] / p['monto_prestado'] * 100 if p['monto_prestado'] > 0 else 0
        p['porcentaje_pagado'] = round(pct, 1)
        for pago in p['pagos']:
            pago['valor_fmt'] = formatear_pesos(pago['valor'])
    return jsonify(prestamos)
