import sys, os, tempfile, sqlite3
from unittest.mock import patch
from datetime import date
import pytest
from app.main import app as flask_app

TEST_SCHEMA = """
CREATE TABLE extractos (
    id INTEGER PRIMARY KEY,
    archivo TEXT, periodo TEXT, anio INTEGER, mes INTEGER,
    titular TEXT, cuenta TEXT, saldo_anterior REAL,
    total_abonos REAL, total_cargos REAL, saldo_actual REAL,
    saldo_promedio REAL, intereses REAL, num_transacciones INTEGER,
    total_pagar REAL, pago_minimo REAL, cupo_total REAL,
    fecha_corte TEXT, fecha_pago TEXT, interes_corriente REAL,
    tasa_mensual REAL, tasa_anual_ea REAL,
    es_refinanciacion INTEGER DEFAULT 0, fuente TEXT, tipo TEXT
);
CREATE TABLE transacciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT, fecha_date DATE, descripcion TEXT, valor REAL,
    entidad TEXT, cruzada INTEGER DEFAULT 0, categoria TEXT,
    es_ingreso INTEGER DEFAULT 0, notas TEXT,
    extracto_id INTEGER REFERENCES extractos(id),
    metodo_pago TEXT, original_id TEXT, banco_id INTEGER
);
CREATE TABLE compras_diferidas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha DATE, descripcion TEXT, valor_total REAL,
    total_cuotas INTEGER, fuente TEXT, categoria TEXT,
    cruzada INTEGER DEFAULT 0
);
CREATE TABLE cuotas_tarjeta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    compra_diferida_id INTEGER REFERENCES compras_diferidas(id),
    num_cuota INTEGER, valor_cuota REAL,
    estado_pago TEXT DEFAULT 'pendiente',
    extracto_id INTEGER REFERENCES extractos(id)
);
CREATE TABLE etiquetas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT UNIQUE, color TEXT
);
CREATE TABLE transaccion_etiquetas (
    transaccion_id INTEGER REFERENCES transacciones(id),
    etiqueta_id INTEGER REFERENCES etiquetas(id),
    PRIMARY KEY(transaccion_id, etiqueta_id)
);
CREATE TABLE config_categorias (
    nombre TEXT PRIMARY KEY, icono TEXT, color TEXT
);
CREATE TABLE presupuestos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria TEXT NOT NULL, monto REAL NOT NULL,
    mes INTEGER NOT NULL, anio INTEGER NOT NULL,
    UNIQUE(categoria, mes, anio)
);
"""


@pytest.fixture
def test_db():
    tmp_dir = tempfile.mkdtemp()
    db_path = os.path.join(tmp_dir, "test.db")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(TEST_SCHEMA)
    c = conn.cursor()

    c.executemany("""
        INSERT INTO extractos
            (id, archivo, periodo, anio, mes, titular, fuente, tipo,
             total_pagar, pago_minimo, cupo_total, saldo_anterior,
             total_cargos, total_abonos, fecha_corte, fecha_pago,
             num_transacciones)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, [
        (1, "nu_julio.pdf", "2026-07", 2026, 7, "Juan Perez",
         "nu", "tarjeta_credito", 500000, 100000, 5000000, 200000,
         700000, 200000, "2026-07-15", "2026-08-05", 5),
        (2, "rappicard_julio.pdf", "2026-07", 2026, 7, "Juan Perez",
         "rappicard", "tarjeta_credito", 300000, 60000, 3000000, 100000,
         400000, 100000, "2026-07-20", "2026-08-10", 3),
    ])

    c.executemany("""
        INSERT INTO transacciones
            (fecha, fecha_date, descripcion, valor, entidad, categoria,
             es_ingreso, notas, metodo_pago, extracto_id)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, [
        ("2026-07-01", "2026-07-01", "Salario mensual", 3000000,
         "empresa", "Salario", 1, "", "transferencia", None),
        ("2026-07-05", "2026-07-05", "Supermercado Exito", -250000,
         "debit", "Comida", 0, "Compra mensual", "debito", None),
        ("2026-07-10", "2026-07-10", "Netflix Plan Premium", -19900,
         "debit", "Entretenimiento", 0, "", "debito", None),
        ("2026-07-12", "2026-07-12", "Gasolina Terpel", -120000,
         "debit", "Transporte", 0, "", "debito", None),
        ("2026-07-15", "2026-07-15", "Restaurante La 10", -45000,
         "debit", "Comida", 0, "", "debito", None),
        ("2026-07-20", "2026-07-20", "Freelance proyecto web", 500000,
         "upwork", "Ingreso familiar", 1, "Pago proyecto",
         "transferencia", None),
        ("2026-07-22", "2026-07-22", "Farmacia Cruz Verde", -35000,
         "debit", "Salud", 0, "", "debito", None),
        ("2026-06-28", "2026-06-28", "Zara Ropa", -80000,
         "debit", "Ropa", 0, "", "debito", None),
        ("2026-06-15", "2026-06-15", "Curso Python Avanzado", -150000,
         "debit", "Educacion", 0, "", "debito", None),
        ("2026-07-25", "2026-07-25", "Internet Tigo Hogar", -89000,
         "debit", "Servicios", 0, "", "debito", None),
        ("2026-07-08", "2026-07-08", "Compra Rappi", -150000,
         "rappicard", "Comida", 0, "", "tarjeta", 2),
        ("2026-07-03", "2026-07-03", "Compra Nu", -200000,
         "nu", "Tecnologia", 0, "", "tarjeta", 1),
    ])

    c.execute("""
        INSERT INTO compras_diferidas
            (id, fecha, descripcion, valor_total, total_cuotas, fuente, categoria)
        VALUES (?,?,?,?,?,?,?)
    """, (1, "2026-06-01", "iPhone 12", 3600000, 12, "nu", "Tecnologia"))

    for i in range(1, 13):
        c.execute("""
            INSERT INTO cuotas_tarjeta
                (compra_diferida_id, num_cuota, valor_cuota, estado_pago, extracto_id)
            VALUES (?,?,?,?,?)
        """, (1, i, 300000, "pendiente" if i > 1 else "pagada",
              1 if i == 1 else None))

    c.executemany(
        "INSERT INTO etiquetas (nombre, color) VALUES (?, ?)",
        [("urgente", "#FF0000"), ("recurrente", "#0000FF"),
         ("esencial", "#00FF00")],
    )
    c.execute(
        "INSERT INTO transaccion_etiquetas (transaccion_id, etiqueta_id) VALUES (?,?)",
        (2, 2),
    )
    c.execute(
        "INSERT INTO transaccion_etiquetas (transaccion_id, etiqueta_id) VALUES (?,?)",
        (5, 3),
    )

    conn.commit()
    conn.close()

    with patch("app.database.DB_PATH", db_path), \
         patch("app.database.DB_COMPLETA", db_path):
        yield

    if os.path.exists(db_path):
        os.remove(db_path)
    os.rmdir(tmp_dir)


@pytest.fixture
def client(test_db):
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c
