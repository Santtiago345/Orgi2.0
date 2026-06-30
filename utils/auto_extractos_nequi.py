"""
AutoExtractos Nequi - Automatizacion de descarga de extractos bancarios
=======================================================================
Requisitos: pip install selenium webdriver-manager
"""
import time
import sys
import re
import random
import threading
from datetime import datetime, date
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ================================================================
# CONFIGURACION - EDITAR SEGUN NECESITES
# ================================================================
URL_LOGIN = "https://transacciones.nequi.com/bdigital/login.jsp?region=co"
URL_EXTRACTOS = "https://transacciones.nequi.com/bdigital/private/#!/documentation"

MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]

# RANGO DE EXTRACCION
ANIO_INICIO = 2020
MES_INICIO = "Octubre"   # Desde que mes empezar
ANIO_FIN = 2026

# Selectors basados en el HTML de Nequi
SEL = {
    "year_select": "select#year",
    "month_select": "select#month",
    "btn_enviar": "button.button-web.second-button",
    "btn_generar": "button.button-web.negative",
    "popup_close": ".close-button-popup",
    "popup_btn": "popup2 a.button-web",
    "spinner": "busy-indicator spinner",
    "cooldown_counter": ".doc-counter-send span",
    # Posibles selectors para clave dinamica (ajustar si es necesario)
    "popup_clave": "popup2 .popup-wrapper",       # Popup generico
    "input_clave": "popup2 input[type='password'], popup2 input[type='text'], popup2 input",
    "btn_confirmar_clave": "popup2 a.button-web, popup2 button.button-web",
}

class NequiExtractor:
    def __init__(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        self.wait = WebDriverWait(self.driver, 30)
        self.short_wait = WebDriverWait(self.driver, 5)
        self.medium_wait = WebDriverWait(self.driver, 10)
        self.resultados = []
        self._keep_alive = True
        self._keep_alive_thread = None
    
    def _keep_session_alive(self):
        """Ejecuta acciones periodicas para evitar que Nequi detecte inactividad (5 min)"""
        acciones = [
            "move_mouse",
            "scroll_small",
            "click_empty",
            "move_mouse_random",
        ]
        while self._keep_alive:
            try:
                accion = random.choice(acciones)
                if accion == "move_mouse":
                    # Mover el mouse en un patron natural
                    ActionChains(self.driver).move_by_offset(
                        random.randint(-50, 50), random.randint(-30, 30)
                    ).perform()
                elif accion == "scroll_small":
                    # Scroll suave hacia abajo y arriba
                    self.driver.execute_script(f"window.scrollBy(0, {random.randint(1, 3)});")
                    time.sleep(0.3)
                    self.driver.execute_script(f"window.scrollBy(0, {random.randint(-3, -1)});")
                elif accion == "click_empty":
                    # Click en un area vacia (el header o el body)
                    header = self.driver.find_element(By.TAG_NAME, "body")
                    ActionChains(self.driver).move_to_element_with_offset(
                        header, random.randint(100, 500), random.randint(50, 200)
                    ).click().perform()
                elif accion == "move_mouse_random":
                    # Simular movimiento mas natural
                    for _ in range(3):
                        ActionChains(self.driver).move_by_offset(
                            random.randint(-20, 20), random.randint(-15, 15)
                        ).perform()
                        time.sleep(0.1)
                # Resetear la posicion del mouse al elemento actual o al body
                try:
                    body = self.driver.find_element(By.CSS_SELECTOR, "body")
                    ActionChains(self.driver).move_to_element(body).perform()
                except:
                    pass
            except:
                pass
            # Ejecutar cada 45-75 segundos (antes de que venzan los 5 min)
            for _ in range(random.randint(45, 75)):
                if not self._keep_alive:
                    return
                time.sleep(1)
    
    def iniciar_keep_alive(self):
        """Inicia el hilo que mantiene la sesion activa"""
        self._keep_alive = True
        self._keep_alive_thread = threading.Thread(target=self._keep_session_alive, daemon=True)
        self._keep_alive_thread.start()
        print("  [Keep-Alive] Hilo anti-inactividad iniciado")
    
    def detener_keep_alive(self):
        """Detiene el hilo de keep-alive"""
        self._keep_alive = False
        if self._keep_alive_thread:
            self._keep_alive_thread.join(timeout=2)
            print("  [Keep-Alive] Hilo detenido")
    
    def esperar_spinner(self, timeout=15):
        """Esperar a que desaparezca el spinner de carga"""
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.invisibility_of_element_located((By.CSS_SELECTOR, SEL["spinner"]))
            )
        except:
            pass
        time.sleep(1)
    
    def detectar_clave_dinamica(self):
        """Detecta si aparecio un popup pidiendo clave dinamica y pide al usuario que la ingrese"""
        try:
            self.short_wait.until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, SEL["popup_clave"]))
            )
            popup = self.driver.find_element(By.CSS_SELECTOR, SEL["popup_clave"])
            texto_popup = popup.text.lower()

            # Palabras clave que indican que piden clave dinamica
            clave_keywords = ["clave", "dinamica", "código", "token", "cód", "verificación", "verificacion",
                              "seguridad", "sms", "mensaje de texto", "confirmar", "autenticación"]

            if any(k in texto_popup for k in clave_keywords):
                print("\n" + "!" * 60)
                print("  !! CLAVE DINAMICA DETECTADA !!")
                print("!" * 60)
                print(f"  Mensaje: {popup.text[:200]}")
                print("\n  > Revisa el navegador, ingresa la clave que llego a tu celular")
                print("  > Escribela en el campo y presiona Confirmar/Enviar")
                input("\n  Presiona ENTER cuando HAYAS INGRESADO LA CLAVE DINAMICA... ")

                # Esperar a que el popup desaparezca
                try:
                    self.medium_wait.until(
                        EC.invisibility_of_element_located((By.CSS_SELECTOR, SEL["popup_clave"]))
                    )
                except:
                    # Si no desaparece, intentar cerrarlo manualmente
                    try:
                        popup.find_element(By.CSS_SELECTOR, SEL["popup_close"]).click()
                    except:
                        pass

                print("  Clave dinamica procesada, continuando...\n")
                time.sleep(1)
                return True

        except:
            pass
        return False
    
    def esperar_spinner_y_clave(self):
        """Combina espera de spinner con deteccion de clave dinamica"""
        for _ in range(30):  # Max 30 iteraciones ~30 segundos
            # Verificar si hay clave dinamica
            if self.detectar_clave_dinamica():
                # Si habia clave, esperar spinner de nuevo
                continue
            # Verificar si el spinner desaparecio
            try:
                spinner = self.driver.find_element(By.CSS_SELECTOR, SEL["spinner"])
                if not spinner.is_displayed():
                    break
            except:
                break
            time.sleep(1)
        else:
            print("  (Timeout esperando proceso)")
    
    def login_manual(self):
        """Paso 1: Dejar que el usuario inicie sesion manualmente"""
        print("=" * 60)
        print("  AUTOEXTRACTOS NEQUI - v2.0")
        print("=" * 60)
        print(f"\n[1/4] Abriendo pagina de Nequi...")
        self.driver.get(URL_LOGIN)
        print("\n[LOGIN] Pagina de login cargada directamente.")
        print("  - Ingresa tu documento y clave")
        print("  - Resuelve cualquier verificacion de seguridad (clave dinamica si pide)")
        print("  - Despues de iniciar sesion, asegurate de ver la pagina principal de Nequi")
        input("\nPresiona ENTER cuando HAYAS INICIADO SESION... ")
        self.iniciar_keep_alive()
        print("  [Keep-Alive] Manteniendo sesion activa en segundo plano")
    
    def ir_a_extractos(self):
        """Paso 2: Navegar a la seccion de Certificados > Extractos"""
        print(f"\n[2/4] Navegando a Certificados > Extractos...")
        self.driver.get(URL_EXTRACTOS)
        self.esperar_spinner()
        
        try:
            active = self.driver.find_element(By.CSS_SELECTOR, "li.active .ng-binding")
            print(f"  Menu activo: {active.text}")
        except:
            print("  NOTA: No se pudo verificar menu activo")
        
        print("  Pagina de extractos cargada correctamente")
    
    def seleccionar_mes_anio(self, mes, anio):
        """Paso 3a: Seleccionar mes y anio en los dropdowns"""
        year_select = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, SEL["year_select"]))
        )
        Select(year_select).select_by_value(str(anio))
        print(f"  Anio seleccionado: {anio}", end="")
        time.sleep(1)
        
        try:
            month_select = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, SEL["month_select"]))
            )
            Select(month_select).select_by_visible_text(mes)
            print(f" | Mes seleccionado: {mes}")
        except Exception as e:
            print(f" | Mes {mes}: NO DISPONIBLE (puede que no haya datos)")
            return False
        
        self.esperar_spinner()
        return True
    
    def enviar_al_correo(self):
        """Paso 3b: Hacer clic en 'Enviar al correo'"""
        print("  Click en 'Enviar al correo'...")
        btn = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, SEL["btn_enviar"]))
        )
        
        disabled = btn.get_attribute("disabled")
        if disabled:
            print("  Boton deshabilitado (cooldown activo), esperando...")
            self.esperar_cooldown()
            btn = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, SEL["btn_enviar"]))
            )
        
        btn.click()
        print("  Enviado!")
        time.sleep(2)
        return True
    
    def cerrar_popup_confirmacion(self):
        """Paso 3c: Cerrar el popup de confirmacion que aparece"""
        try:
            popup = self.short_wait.until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "popup2 .popup-wrapper"))
            )
            try:
                texto = popup.find_element(By.CSS_SELECTOR, "p.ng-binding")
                print(f"  Popup: {texto.text[:100]}")
            except:
                pass
            
            close_btn = popup.find_element(By.CSS_SELECTOR, SEL["popup_close"])
            close_btn.click()
            print("  Popup cerrado")
            time.sleep(1)
        except:
            pass
    
    def esperar_cooldown(self):
        """Paso 3d: Esperar el cooldown de 30 segundos"""
        print("  Esperando cooldown...")
        try:
            counter = self.short_wait.until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, SEL["cooldown_counter"]))
            )
            print(f"  Cooldown detectado ({counter.text}), esperando...")
            
            self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, SEL["btn_enviar"]))
            )
            time.sleep(2)
            print("  Cooldown terminado!")
        except:
            print("  Sin cooldown visible, esperando 3s...")
            time.sleep(3)
    
    def esperar_envio_completado(self):
        """Esperar a que termine el envio del correo con deteccion de clave dinamica"""
        print("  Procesando envio...")
        # Mientras haya spinner o clave dinamica, esperar
        self.esperar_spinner_y_clave()
        self.cerrar_popup_confirmacion()
        self.esperar_cooldown()
    
    def run(self):
        """Ejecutar la automatizacion completa"""
        self.login_manual()
        self.ir_a_extractos()
        
        # Validar configuracion de mes inicio
        if MES_INICIO not in MESES:
            print(f"\nERROR: '{MES_INICIO}' no es un mes valido. Usa: {', '.join(MESES)}")
            self.driver.quit()
            return
        
        mes_inicio_idx = MESES.index(MES_INICIO)
        
        print(f"\n[3/4] Procesando extractos desde {MES_INICIO} {ANIO_INICIO} hasta {ANIO_FIN}...")
        print(f"  NOTA: Solo se procesaran los meses con datos disponibles")
        print(f"  Si aparece clave dinamica, el script se pausa y te avisa")
        print()
        
        total_ok = 0
        total_fail = 0
        
        for anio in range(ANIO_INICIO, ANIO_FIN + 1):
            # Determinar desde que mes empezar segun el año
            inicio_mes_idx = 0
            if anio == ANIO_INICIO:
                inicio_mes_idx = mes_inicio_idx
            
            for mes_idx in range(inicio_mes_idx, 12):
                mes = MESES[mes_idx]
                
                # Saltar meses futuros
                hoy = date.today()
                if anio > hoy.year or (anio == hoy.year and mes_idx > hoy.month - 1):
                    print(f"[{mes} {anio}] Futuro, saltando")
                    continue
                
                print(f"[{mes} {anio}] ", end="")
                
                try:
                    ok = self.seleccionar_mes_anio(mes, anio)
                    if not ok:
                        print(f"  -> Sin datos, saltando")
                        total_fail += 1
                        self.resultados.append(f"{mes} {anio}: SIN DATOS")
                        continue
                    
                    self.enviar_al_correo()
                    self.esperar_envio_completado()
                    
                    total_ok += 1
                    self.resultados.append(f"{mes} {anio}: ENVIADO OK")
                    print(f"  -> ENVIADO OK")
                    
                except Exception as e:
                    # Si el error es por clave dinamica, preguntar
                    err_msg = str(e)
                    if "clave" in err_msg.lower() or "dinamica" in err_msg.lower():
                        self.detectar_clave_dinamica()
                        # Reintentar
                        try:
                            self.enviar_al_correo()
                            self.esperar_envio_completado()
                            total_ok += 1
                            self.resultados.append(f"{mes} {anio}: ENVIADO OK (con clave)")
                            print(f"  -> ENVIADO OK (despues de clave)")
                            continue
                        except:
                            pass
                    
                    print(f"  -> ERROR: {err_msg[:80]}")
                    total_fail += 1
                    self.resultados.append(f"{mes} {anio}: ERROR - {err_msg[:80]}")
                    
                    try:
                        self.cerrar_popup_confirmacion()
                        self.esperar_cooldown()
                    except:
                        pass
        
        # Reporte final
        print("\n" + "=" * 60)
        print("   REPORTE FINAL")
        print("=" * 60)
        ok_count = sum(1 for r in self.resultados if "OK" in r)
        fail_count = sum(1 for r in self.resultados if "ERROR" in r or "SIN DATOS" in r)
        print(f"  Enviados correctamente: {ok_count}")
        print(f"  Sin datos/Error: {fail_count}")
        print(f"  Total procesados: {len(self.resultados)}")
        print()
        print("  DETALLE:")
        for r in self.resultados:
            print(f"    {r}")
        
        self.detener_keep_alive()
        print()
        opcion = input(f"\n[4/4] Presiona ENTER para cerrar el navegador, o escribe 'mantener' para revisar: ")
        if opcion.lower() != "mantener":
            self.driver.quit()
            print("Navegador cerrado.")
        else:
            print("Navegador mantenido abierto. Cierralo manualmente cuando termines.")

if __name__ == "__main__":
    extractor = NequiExtractor()
    try:
        extractor.run()
    except KeyboardInterrupt:
        print("\n\nPrograma interrumpido por el usuario.")
        extractor.detener_keep_alive()
        try:
            extractor.driver.quit()
        except:
            pass
    except Exception as e:
        print(f"\nError inesperado: {e}")
        extractor.detener_keep_alive()
        try:
            extractor.driver.quit()
        except:
            pass
        input("Presiona ENTER para salir...")
