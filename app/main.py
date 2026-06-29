from flask import Flask, jsonify, render_template, request
from datetime import datetime, date
import json, os, subprocess, sys

from .database import (
    calcular_balance, obtener_rango_fechas, navegar_periodo, es_periodo_actual,
    obtener_transacciones_por_periodo, obtener_gastos_por_categoria,
    agregar_transaccion, obtener_ultima_fecha, obtener_extractos,
    buscar_extracto_duplicado, obtener_extracto_detalle
)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)

PAGINAS = [
    {"id": "inicio", "nombre": "Inicio", "ruta": "/"},
    {"id": "extractos", "nombre": "Extractos", "ruta": "/extractos"},
    {"id": "presupuesto", "nombre": "Presupuesto", "ruta": "/presupuesto"},
    {"id": "reportes", "nombre": "Reportes", "ruta": "/reportes"},
]

CATEGORIAS = [
    {"id": "Comida", "icono": "🍽️", "color": "#FF6384"},
    {"id": "Transporte", "icono": "🚗", "color": "#36A2EB"},
    {"id": "Servicios", "icono": "💡", "color": "#FFCE56"},
    {"id": "Ropa", "icono": "👕", "color": "#4BC0C0"},
    {"id": "Entretenimiento", "icono": "🎬", "color": "#9966FF"},
    {"id": "Salud", "icono": "🏥", "color": "#FF9F40"},
    {"id": "Educacion", "icono": "📚", "color": "#7BC8A4"},
    {"id": "Tecnologia", "icono": "💻", "color": "#E7E9EB"},
    {"id": "Viajes", "icono": "✈️", "color": "#F7464A"},
    {"id": "Ingreso familiar", "icono": "👨‍👩‍👧", "color": "#46BFBD"},
    {"id": "Salario", "icono": "💰", "color": "#FDB45C"},
    {"id": "Sin clasificar", "icono": "❓", "color": "#C9CBCF"},
    {"id": "Compras general", "icono": "🛒", "color": "#A8E6CF"},
    {"id": "Cargos financieros", "icono": "🏦", "color": "#D4A5A5"},
    {"id": "Varios", "icono": "📦", "color": "#B0B0B0"},
]


def formatear_pesos(valor):
    negativo = valor < 0
    s = f"{abs(valor):,.0f}".replace(",", ".")
    return f"-${s}" if negativo else f"${s}"

def formatear_pesos_linea(valor):
    """Formatea sin decimales para lineas de detalle."""
    negativo = valor < 0
    s = f"{abs(valor):,.0f}".replace(",", ".")
    return f"-${s}" if negativo else f"${s}"

def icono_categoria(cat):
    for c in CATEGORIAS:
        if c["id"] == cat:
            return c["icono"]
    return "📌"

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
    """Agrupa cuotas (misma entidad+descripcion+abs(valor)) en una transaccion."""
    grupos = {}
    for t in transacciones:
        key = (t["entidad"], t["descripcion"].strip().lower(), round(abs(t["valor"]), 2))
        grupos.setdefault(key, []).append(t)
    result = []
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

    # Deduplicar cuotas en la vista de transacciones (no en totales por categoria)
    transacciones = deduplicar_cuotas(transacciones)

    return jsonify({
        "total": round(total, 2),
        "total_fmt": formatear_pesos(total),
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "categorias": [{
            **c,
            "porcentaje": round(c["total"] / total * 100, 1) if total > 0 else 0,
            "icono": icono_categoria(c["categoria"]),
            "color": next((x["color"] for x in CATEGORIAS if x["id"] == c["categoria"]), "#C9CBCF")
        } for c in categorias],
        "transacciones": [
            {**t, "valor_fmt": formatear_pesos(t["valor"])}
            for t in transacciones
        ],
        "num_transacciones": len(transacciones),
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
    valor = float(data.get("valor", 0))
    categoria = data.get("categoria", "Varios").strip()
    tipo = data.get("tipo", "gasto")
    notas = data.get("notas", "").strip()

    if not descripcion or valor <= 0:
        return jsonify({"error": "Descripcion y valor requeridos"}), 400

    new_id = agregar_transaccion(fecha, descripcion, valor, categoria, tipo, notas)
    balance, ing, gas = calcular_balance()
    return jsonify({
        "ok": True, "id": new_id,
        "balance_fmt": formatear_pesos(balance),
        "ingresos_fmt": formatear_pesos(ing),
        "gastos_fmt": formatear_pesos(gas),
    })


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
        return jsonify({"error": "No se envió ningún archivo"}), 400

    file = request.files["pdf"]
    if file.filename == "":
        return jsonify({"error": "Nombre de archivo vacío"}), 400

    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Solo se aceptan archivos PDF"}), 400

    # Verificar duplicado
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

    # Ejecutar procesamiento
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(BASE, "scripts", "procesar_inbox.py"), "--inbox-only"],
            capture_output=True, text=True, timeout=120
        )
        output = result.stdout + result.stderr
        success = result.returncode == 0
    except Exception as e:
        output = str(e)
        success = False

    # Obtener info del extracto procesado
    info = {"archivo_original": file.filename, "archivo_real": real_name, "success": success}
    if success:
        extractos = obtener_extractos()
        if extractos:
            ultimo = extractos[0]
            info["banco"] = ultimo["fuente"]
            info["periodo"] = ultimo["periodo"]
            info["tipo"] = "tarjeta_credito" if ultimo["fuente"] in ("nu", "rappicard") else "cuenta_corriente"

    return jsonify(info)
