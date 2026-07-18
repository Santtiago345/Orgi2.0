import json
from unittest.mock import patch, MagicMock
from datetime import date


class TestApiResumen:

    def test_resumen_gastos_mes(self, client):
        r = client.get("/api/resumen?tipo=gastos&periodo=mes")
        assert r.status_code == 200
        data = r.get_json()
        assert "total" in data
        assert "categorias" in data
        assert "transacciones" in data
        assert data["total"] > 0
        assert len(data["categorias"]) > 0
        assert len(data["transacciones"]) > 0

    def test_resumen_ingresos_mes(self, client):
        r = client.get("/api/resumen?tipo=ingresos&periodo=mes")
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] > 0

    def test_resumen_semana(self, client):
        r = client.get("/api/resumen?tipo=gastos&periodo=semana")
        assert r.status_code == 200

    def test_resumen_personalizado(self, client):
        r = client.get(
            "/api/resumen?tipo=gastos&periodo=personalizado"
            "&desde=2026-07-01&hasta=2026-07-31"
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["desde"] == "2026-07-01"
        assert data["hasta"] == "2026-07-31"

    def test_resumen_categorias_tienen_porcentaje(self, client):
        r = client.get("/api/resumen?tipo=gastos&periodo=mes")
        data = r.get_json()
        for c in data["categorias"]:
            assert "porcentaje" in c
            assert "icono" in c
            assert "color" in c

    def test_resumen_transacciones_tienen_valor_fmt(self, client):
        r = client.get("/api/resumen?tipo=gastos&periodo=mes")
        data = r.get_json()
        for t in data["transacciones"]:
            assert "valor_fmt" in t

    def test_resumen_navegar(self, client):
        r = client.get(
            "/api/navegar?tipo=gastos&periodo=mes"
            "&desde=2026-07-01&hasta=2026-07-31&dir=1"
        )
        assert r.status_code == 200
        data = r.get_json()
        assert "2026-08" in data["desde"]


class TestApiExtractos:

    def test_listar_extractos(self, client):
        r = client.get("/api/extractos")
        assert r.status_code == 200
        data = r.get_json()
        assert len(data) == 2

    def test_extracto_detalle(self, client):
        r = client.get("/api/extracto/1")
        assert r.status_code == 200
        data = r.get_json()
        assert data["id"] == 1
        assert data["fuente"] == "nu"
        assert "transacciones" in data
        assert "es_tarjeta_credito" in data

    def test_extracto_no_encontrado(self, client):
        r = client.get("/api/extracto/999")
        assert r.status_code == 404

    def test_extracto_detalle_tc_meta(self, client):
        r = client.get("/api/extracto/1")
        data = r.get_json()
        assert data["es_tarjeta_credito"] is True
        assert data["tc_meta"] is not None
        assert "total_pagar" in data["tc_meta"]

    def test_extracto_rappicard(self, client):
        r = client.get("/api/extracto/2")
        assert r.status_code == 200
        data = r.get_json()
        assert data["fuente"] == "rappicard"


class TestApiAgregarTransaccion:

    def test_agregar_transaccion_valida(self, client):
        payload = {
            "fecha": "2026-07-28",
            "descripcion": "Test desde API",
            "valor": 32000,
            "categoria": "Comida",
            "tipo": "gasto",
        }
        r = client.post("/api/transacciones",
                        data=json.dumps(payload),
                        content_type="application/json")
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert isinstance(data["id"], int)

    def test_agregar_ingreso(self, client):
        payload = {
            "fecha": "2026-07-28",
            "descripcion": "Ingreso test API",
            "valor": 200000,
            "categoria": "Salario",
            "tipo": "ingreso",
        }
        r = client.post("/api/transacciones",
                        data=json.dumps(payload),
                        content_type="application/json")
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

    def test_agregar_sin_datos(self, client):
        r = client.post("/api/transacciones",
                        data=json.dumps({}),
                        content_type="application/json")
        assert r.status_code == 400

    def test_agregar_descripcion_vacia(self, client):
        payload = {
            "descripcion": "",
            "valor": 50000,
            "categoria": "Varios",
            "tipo": "gasto",
        }
        r = client.post("/api/transacciones",
                        data=json.dumps(payload),
                        content_type="application/json")
        assert r.status_code == 400

    def test_agregar_valor_cero(self, client):
        payload = {
            "descripcion": "Test cero",
            "valor": 0,
            "categoria": "Varios",
            "tipo": "gasto",
        }
        r = client.post("/api/transacciones",
                        data=json.dumps(payload),
                        content_type="application/json")
        assert r.status_code == 400


class TestApiCategorias:

    def test_listar_categorias(self, client):
        r = client.get("/api/categorias")
        assert r.status_code == 200
        data = r.get_json()
        assert len(data) > 0
        for c in data:
            assert "categoria" in c
            assert "total_tx" in c
            assert "total_gastado" in c

    def test_categorias_transacciones(self, client):
        r = client.get("/api/categorias/transacciones?categoria=Comida")
        assert r.status_code == 200
        data = r.get_json()
        assert "transacciones" in data
        assert len(data["transacciones"]) > 0
        for t in data["transacciones"]:
            assert t["categoria"] == "Comida"

    def test_categorias_transacciones_sin_resultados(self, client):
        r = client.get(
            "/api/categorias/transacciones?categoria=Inexistente"
        )
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["transacciones"]) == 0
        assert data["total"] == 0

    def test_renombrar_categoria(self, client):
        payload = {"viejo": "Comida", "nuevo": "Alimentos"}
        r = client.post("/api/categorias/rename",
                        data=json.dumps(payload),
                        content_type="application/json")
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
        assert r.get_json()["cambios"] > 0


class TestApiEtiquetas:

    def test_listar_etiquetas(self, client):
        r = client.get("/api/etiquetas")
        assert r.status_code == 200
        data = r.get_json()
        assert len(data) == 3

    def test_crear_etiqueta(self, client):
        payload = {"nombre": "nueva-etiqueta", "color": "#123456"}
        r = client.post("/api/etiquetas",
                        data=json.dumps(payload),
                        content_type="application/json")
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert isinstance(data["id"], int)

    def test_crear_etiqueta_duplicada(self, client):
        payload = {"nombre": "urgente"}
        r = client.post("/api/etiquetas",
                        data=json.dumps(payload),
                        content_type="application/json")
        assert r.status_code == 409

    def test_crear_etiqueta_sin_nombre(self, client):
        r = client.post("/api/etiquetas",
                        data=json.dumps({"nombre": ""}),
                        content_type="application/json")
        assert r.status_code == 400

    def test_actualizar_etiqueta(self, client):
        payload = {"nombre": "urgente-upd", "color": "#111111"}
        r = client.put("/api/etiquetas/1",
                       data=json.dumps(payload),
                       content_type="application/json")
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

    def test_actualizar_etiqueta_no_existe(self, client):
        payload = {"nombre": "test"}
        r = client.put("/api/etiquetas/999",
                       data=json.dumps(payload),
                       content_type="application/json")
        assert r.status_code == 404

    def test_eliminar_etiqueta(self, client):
        r = client.delete("/api/etiquetas/3")
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

    def test_eliminar_etiqueta_no_existe(self, client):
        r = client.delete("/api/etiquetas/999")
        assert r.status_code == 404

    def test_asignar_etiqueta_transaccion(self, client):
        payload = {"etiqueta_id": 1}
        r = client.post("/api/transacciones/1/etiquetas",
                        data=json.dumps(payload),
                        content_type="application/json")
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

    def test_obtener_etiquetas_transaccion(self, client):
        r = client.get("/api/transacciones/2/etiquetas")
        assert r.status_code == 200
        data = r.get_json()
        assert len(data) == 1
        assert data[0]["nombre"] == "recurrente"

    def test_quitar_etiqueta_transaccion(self, client):
        r = client.delete("/api/transacciones/2/etiquetas/2")
        assert r.status_code == 200
        assert r.get_json()["ok"] is True


class TestApiPerfilCrediticio:

    def test_perfil_crediticio(self, client):
        r = client.get("/api/perfil-crediticio")
        assert r.status_code == 200
        data = r.get_json()
        assert "tarjetas" in data
        assert "extractos" in data
        assert len(data["tarjetas"]) == 2
        for t in data["tarjetas"]:
            assert "fuente" in t
            assert "deuda_total" in t
            assert "deuda_total_fmt" in t
            assert "cupo_total" in t
            assert "utilizacion" in t

    def test_perfil_tarjeta_tiene_campos(self, client):
        r = client.get("/api/perfil-crediticio")
        data = r.get_json()
        for t in data["tarjetas"]:
            assert "pago_minimo_total" in t
            assert "extracto_actualizado" in t
            assert "periodo_extracto" in t


class TestApiPrestamosNequi:

    def test_prestamos_sin_db_retorna_vacio(self, client):
        with patch("os.path.exists") as mock_exists:
            mock_exists.return_value = False
            r = client.get("/api/prestamos-nequi")
            assert r.status_code == 200
            data = r.get_json()
            assert data == []

    def test_prestamos_con_error_db_retorna_vacio(self, client):
        with patch("app.database.obtener_prestamos_nequi") as mock_fn:
            mock_fn.return_value = []
            r = client.get("/api/prestamos-nequi")
            assert r.status_code == 200
            assert r.get_json() == []
