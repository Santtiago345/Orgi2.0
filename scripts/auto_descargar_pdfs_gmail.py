"""
AutoDownload PDFs Gmail - Descarga automatica de PDFs desde un hilo de Gmail
================================================================================
Requiere tener los PDFs visibles en el cuerpo del correo (incrustados en el hilo).

Requisitos: pip install selenium webdriver-manager

USO:
  1. Ejecuta el script
  2. Se abrira Chrome, ingresa a Gmail y navega al hilo que tiene los PDFs
  3. Presiona ENTER en la terminal
  4. El script descargara automaticamente todos los PDFs
"""
import time
import os
import threading
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ================================================================
# CONFIGURACION
# ================================================================
# Carpeta donde se guardaran los PDFs
DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "PDFs_Gmail")

# Selector para botones de descarga de adjuntos en Gmail
# Busca botones cuyo aria-label comience con "Descargar el archivo adjunto"
SEL_BTN_DESCARGAR = "button[aria-label^='Descargar el archivo adjunto']"

# Espera entre descargas (segundos)
DELAY_ENTRE_DESCARGAS = 2


class GmailPDFDownloader:
    def __init__(self):
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        # Preferencias para descarga automatica de PDFs
        prefs = {
            "download.default_directory": DOWNLOAD_DIR,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True,
            "safebrowsing.enabled": False,
        }

        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("prefs", prefs)
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        self.wait = WebDriverWait(self.driver, 20)
        self.short_wait = WebDriverWait(self.driver, 5)

        self.descargados = set()
        self.omitidos = set()
        self.errores = set()

        self._keep_alive = True
        self._keep_alive_thread = None

    # ----------------------------------------------------------
    # Keep-alive (anti-timeout)
    # ----------------------------------------------------------
    def _keep_session_alive(self):
        acciones = ["move_mouse", "scroll_small", "click_empty"]
        while self._keep_alive:
            try:
                accion = random.choice(acciones)
                if accion == "move_mouse":
                    ActionChains(self.driver).move_by_offset(
                        random.randint(-30, 30), random.randint(-20, 20)
                    ).perform()
                elif accion == "scroll_small":
                    self.driver.execute_script(f"window.scrollBy(0, {random.randint(1, 3)});")
                    time.sleep(0.2)
                    self.driver.execute_script(f"window.scrollBy(0, {random.randint(-3, -1)});")
                elif accion == "click_empty":
                    body = self.driver.find_element(By.TAG_NAME, "body")
                    ActionChains(self.driver).move_to_element_with_offset(
                        body, random.randint(100, 500), random.randint(50, 200)
                    ).click().perform()
                try:
                    body = self.driver.find_element(By.CSS_SELECTOR, "body")
                    ActionChains(self.driver).move_to_element(body).perform()
                except:
                    pass
            except:
                pass
            for _ in range(random.randint(40, 70)):
                if not self._keep_alive:
                    return
                time.sleep(1)

    def iniciar_keep_alive(self):
        self._keep_alive = True
        self._keep_alive_thread = threading.Thread(target=self._keep_session_alive, daemon=True)
        self._keep_alive_thread.start()
        print("  [Keep-Alive] Hilo anti-inactividad iniciado")

    def detener_keep_alive(self):
        self._keep_alive = False
        if self._keep_alive_thread:
            self._keep_alive_thread.join(timeout=2)
            print("  [Keep-Alive] Hilo detenido")

    # ----------------------------------------------------------
    # Pasos
    # ----------------------------------------------------------
    def paso1_navegar(self):
        print("=" * 60)
        print("  AUTODOWNLOAD PDFs - GMAIL")
        print("=" * 60)
        print(f"\n[1/3] Abriendo Gmail (los PDFs se guardaran en: {DOWNLOAD_DIR})")
        self.driver.get("https://mail.google.com")
        print("\n  > Inicia sesion si es necesario")
        print("  > Navega hasta el hilo/correo que tiene los PDFs incrustados")
        print("  > Asegurate de que los PDFs esten visibles en la pagina")
        input("\nPresiona ENTER cuando estes listo en la pagina con los PDFs... ")
        self.iniciar_keep_alive()

    def paso2_descargar(self):
        print(f"\n[2/3] Buscando botones de descarga...")

        # Encontrar todos los botones de descarga
        botones = self.driver.find_elements(By.CSS_SELECTOR, SEL_BTN_DESCARGAR)
        total = len(botones)
        print(f"  Se encontraron {total} archivos adjuntos")

        if total == 0:
            print("  No se encontraron botones de descarga.")
            print("  Sugerencias:")
            print("    - Verifica que los PDFs esten visibles en la pagina")
            print("    - Prueba haciendo scroll hacia abajo para cargar todos")
            resp = input("\n  Presiona ENTER para reintentar o escribe 'salir' para terminar: ")
            if resp.lower() != "salir":
                return self.paso2_descargar()
            return

        for i, btn in enumerate(botones, 1):
            try:
                # Obtener nombre del archivo desde el aria-label
                aria = btn.get_attribute("aria-label")
                filename = aria.replace("Descargar el archivo adjunto ", "")
                filepath = os.path.join(DOWNLOAD_DIR, filename)

                # Saltar si ya se descargo
                if filename in self.descargados:
                    continue
                if os.path.exists(filepath):
                    print(f"  [{i}/{total}] {filename} -> ya existe, saltando")
                    self.omitidos.add(filename)
                    continue

                print(f"  [{i}/{total}] Descargando: {filename}...", end=" ")

                # Scroll hasta el boton
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});",
                    btn
                )
                time.sleep(0.5)

                # --- Estrategia de hover + click ---
                # 1. Hacer hover sobre el contenedor padre de la card
                #    (para que aparezca el boton de descarga)
                card = self.driver.execute_script("""
                    var el = arguments[0].parentElement;
                    for (var i = 0; i < 8; i++) {
                        if (!el) break;
                        var r = el.getBoundingClientRect();
                        if (r.width > 150 && r.height > 40) return el;
                        el = el.parentElement;
                    }
                    return arguments[0].parentElement;
                """, btn)

                ActionChains(self.driver).move_to_element(card).perform()
                time.sleep(0.3)

                # 2. Intentar click normal
                try:
                    btn.click()
                except Exception:
                    # 3. Fallback: click con JavaScript
                    self.driver.execute_script("arguments[0].click();", btn)

                self.descargados.add(filename)
                print("OK")

                # Esperar entre descargas para evitar bloqueos
                time.sleep(DELAY_ENTRE_DESCARGAS)

            except Exception as e:
                try:
                    aria = btn.get_attribute("aria-label")
                    fname = aria.replace("Descargar el archivo adjunto ", "")
                except:
                    fname = f"archivo_{i}"
                print(f"ERROR: {str(e)[:80]}")
                self.errores.add(fname)

        print(f"\n  Descargas iniciadas. Esperando que finalicen...")
        time.sleep(5)

    def paso3_resumen(self):
        print("\n" + "=" * 60)
        print("  RESUMEN")
        print("=" * 60)
        print(f"  Descargados:    {len(self.descargados)}")
        for f in sorted(self.descargados):
            print(f"    - {f}")
        if self.omitidos:
            print(f"\n  Ya existentes:  {len(self.omitidos)}")
            for f in sorted(self.omitidos):
                print(f"    - {f}")
        if self.errores:
            print(f"\n  Con errores:    {len(self.errores)}")
            for f in sorted(self.errores):
                print(f"    - {f}")
        print(f"\n  Destino: {DOWNLOAD_DIR}")

    def run(self):
        try:
            self.paso1_navegar()
            self.paso2_descargar()
            self.paso3_resumen()
            self.preguntar_cerrar()
        except KeyboardInterrupt:
            print("\n\nInterrumpido por el usuario.")
        finally:
            self.detener_keep_alive()
            try:
                self.driver.quit()
            except:
                pass

    def preguntar_cerrar(self):
        resp = input("Presiona ENTER para cerrar el navegador, o escribe 'mantener': ")
        if resp.lower() != "mantener":
            self.driver.quit()
            print("Navegador cerrado.")
        else:
            print("Navegador mantenido abierto. Cierralo manualmente.")


if __name__ == "__main__":
    downloader = GmailPDFDownloader()
    try:
        downloader.run()
    except KeyboardInterrupt:
        print("\n\nPrograma interrumpido por el usuario.")
        downloader.detener_keep_alive()
        try:
            downloader.driver.quit()
        except:
            pass
    except Exception as e:
        print(f"\nError inesperado: {e}")
        downloader.detener_keep_alive()
        try:
            downloader.driver.quit()
        except:
            pass
        input("Presiona ENTER para salir...")
