import os
import pdfplumber
import re
import json
from datetime import datetime

UNLOCKED_DIR = r"C:\Users\Santt\OneDrive\Documentos\Proyectos\Orgi2.0\pdf bancos\unlocked"

def extract_nu_text(pdf_path):
    """Extract text from Nu Bank PDF"""
    with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
    return text

def extract_credit_card_text(pdf_path):
    """Extract text from Credit Card PDF"""
    with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
        tables = []
        for page in pdf.pages:
            t = page.extract_tables()
            if t:
                tables.extend(t)
    return text, tables

def parse_nu_statement(text, filename):
    """Parse Nu Bank statement"""
    info = {
        "archivo": filename,
        "banco": "Nu Bank",
        "fecha_extracto": None,
        "saldo_anterior": None,
        "saldo_actual": None,
        "ingresos": [],
        "gastos": [],
        "transacciones": []
    }
    # Try to find dates
    date_match = re.search(r"(\d{2}/\d{2}/\d{4})", text)
    if date_match:
        info["fecha_extracto"] = date_match.group(1)
    # Try to find balances
    balance_match = re.search(r"saldo[:\s]*R?\$?\s*([\d.,]+)", text, re.IGNORECASE)
    if balance_match:
        info["saldo_actual"] = balance_match.group(1)
    # Extract all amount lines
    amounts = re.findall(r"R?\$?\s*([\d]+\.[\d]{2})", text)
    print(f"\n--- Nu: {filename} ---")
    print(f"  Fecha: {info['fecha_extracto']}")
    print(f"  Saldo: {info['saldo_actual']}")
    print(f"  Posibles montos encontrados: {amounts}")
    return info

def parse_credit_card(text, tables, filename):
    """Parse Credit Card statement"""
    info = {
        "archivo": filename,
        "banco": "Tarjeta de Crédito",
        "fecha_corte": None,
        "fecha_vencimiento": None,
        "total_pagar": None,
        "pago_minimo": None,
        "limite_credito": None,
        "saldo_disponible": None,
        "transacciones": []
    }
    # Extract totals
    total_match = re.search(r"total[^\d]*([\d.,]+)", text, re.IGNORECASE)
    if total_match:
        info["total_pagar"] = total_match.group(1)
    min_match = re.search(r"m[ií]nimo[^\d]*([\d.,]+)", text, re.IGNORECASE)
    if min_match:
        info["pago_minimo"] = min_match.group(1)
    limit_match = re.search(r"l[ií]mite[^\d]*([\d.,]+)", text, re.IGNORECASE)
    if limit_match:
        info["limite_credito"] = limit_match.group(1)
    date_match = re.findall(r"(\d{2}/\d{2}/\d{4})", text)
    if date_match:
        info["fecha_corte"] = date_match[0]
    print(f"\n--- Tarjeta: {filename} ---")
    print(f"  Total a pagar: {info['total_pagar']}")
    print(f"  Pago mínimo: {info['pago_minimo']}")
    print(f"  Límite: {info['limite_credito']}")
    return info

def main():
    if not os.path.exists(UNLOCKED_DIR):
        print("Primero ejecuta unlock_pdfs.py para desbloquear los PDFs")
        return
    files = [f for f in os.listdir(UNLOCKED_DIR) if f.endswith('.pdf')]
    if not files:
        print("No hay PDFs desbloqueados en", UNLOCKED_DIR)
        return
    print(f"Analizando {len(files)} archivos...")
    results = {"nu": [], "credit_cards": []}
    for f in sorted(files):
        path = os.path.join(UNLOCKED_DIR, f)
        if f.startswith("Nu"):
            text = extract_nu_text(path)
            info = parse_nu_statement(text, f)
            results["nu"].append(info)
        elif "CREDIT_CARD" in f:
            text, tables = extract_credit_card_text(path)
            info = parse_credit_card(text, tables, f)
            results["credit_cards"].append(info)
    # Save results
    out_path = os.path.join(UNLOCKED_DIR, "analisis.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nAnálisis guardado en: {out_path}")
    # Summary
    print("\n=== RESUMEN ===")
    for cc in results["credit_cards"]:
        if cc["total_pagar"]:
            print(f"  Tarjeta: ${cc['total_pagar']} a pagar")

if __name__ == "__main__":
    main()
