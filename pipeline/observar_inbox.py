"""
OBSERVAR INBOX — Vigilante automático de la carpeta de entrada
==============================================================
Se ejecuta en segundo plano y monitorea data/inbox/ cada 5 segundos.
Cuando detecta un PDF nuevo, espera a que termine la copia y ejecuta
el pipeline de procesamiento.

USO:
  # Ventana normal (visible)
  python pipeline/observar_inbox.py

  # Ventana minimizada (usar con el .bat)
  python pipeline/observar_inbox.py --silent

  # Cerrar con Ctrl+C
"""

import os, sys, time, subprocess, glob

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX_DIR = os.path.join(BASE, "data", "inbox")
PROC_SCRIPT = os.path.join(BASE, "scripts", "procesar_inbox.py")
POLL_INTERVAL = 5    # segundos entre cada verificación
STABILIZE_WAIT = 8   # segundos para esperar que termine la copia

SILENT = "--silent" in sys.argv


def log(msg):
    t = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{t}] {msg}")


def procesar():
    log("PDFs detectados. Procesando...")
    try:
        result = subprocess.run(
            [sys.executable, PROC_SCRIPT, "--inbox-only"],
            capture_output=True, text=True, timeout=120
        )
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                print(f"  {line.strip()}")
        if result.returncode != 0:
            for line in result.stderr.strip().split("\n"):
                if line.strip():
                    print(f"  ERROR: {line.strip()}")
        log("Procesamiento completado.")
    except subprocess.TimeoutExpired:
        log("ERROR: El procesamiento excedió el tiempo límite")
    except Exception as e:
        log(f"ERROR: {e}")


def main():
    os.makedirs(INBOX_DIR, exist_ok=True)

    if not SILENT:
        print("=" * 60)
        print("  OBSERVADOR DE EXTRACTOS BANCARIOS")
        print(f"  Monitoreando: {INBOX_DIR}")
        print("  Cada 5 segundos.")
        print("  Ctrl+C para detener.")
        print("=" * 60)

    # Procesar PDFs pendientes al inicio
    pendientes = glob.glob(os.path.join(INBOX_DIR, "*.pdf"))
    if pendientes:
        log(f"Pendientes: {len(pendientes)} PDF(s)")
        procesar()

    processed_times = {}  # archivo -> timestamp

    try:
        while True:
            pdfs = glob.glob(os.path.join(INBOX_DIR, "*.pdf"))
            nuevos = []

            for p in pdfs:
                fname = os.path.basename(p)
                mtime = os.path.getmtime(p)
                last = processed_times.get(fname, 0)
                # Es nuevo si no lo hemos visto antes, o si su mtime cambió
                if mtime > last:
                    nuevos.append(p)
                    processed_times[fname] = mtime

            if nuevos:
                log(f"Detectados {len(nuevos)} PDF(s) nuevo(s). Esperando {STABILIZE_WAIT}s...")
                time.sleep(STABILIZE_WAIT)
                procesar()
                # Actualizar timestamps después de procesar
                for p in glob.glob(os.path.join(INBOX_DIR, "*.pdf")):
                    fname = os.path.basename(p)
                    processed_times[fname] = os.path.getmtime(p)

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print()
        log("Observador detenido por el usuario.")
    except Exception as e:
        log(f"Error fatal: {e}")
        raise


if __name__ == "__main__":
    main()
