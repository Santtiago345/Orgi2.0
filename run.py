#!/usr/bin/env python3
"""
Orgi App — Punto de entrada
Ejecutar con: python run.py
"""
import os, sys
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import app

if __name__ == "__main__":
    import webbrowser
    port = 5000
    print("=" * 50)
    print("  ORGI — Aplicación Financiera")
    print(f"  http://localhost:{port}")
    print("  Ctrl+C para detener")
    print("=" * 50)
    webbrowser.open(f"http://localhost:{port}")
    debug = os.environ.get("FLASK_ENV") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug)
