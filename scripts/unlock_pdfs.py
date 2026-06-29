import os
import sys
from pypdf import PdfReader, PdfWriter

PDF_DIR = r"C:\Users\Santt\OneDrive\Documentos\Proyectos\Orgi2.0\pdf bancos"
OUT_DIR = r"C:\Users\Santt\OneDrive\Documentos\Proyectos\Orgi2.0\pdf bancos\unlocked"

def unlock_pdf(pdf_path, password):
    reader = PdfReader(pdf_path)
    if reader.is_encrypted:
        if not reader.decrypt(password):
            return False, "Contraseña incorrecta"
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, os.path.basename(pdf_path))
    with open(out_path, "wb") as f:
        writer.write(f)
    return True, out_path

def main():
    print("=== DESBLOQUEADOR DE PDFs BANCARIOS ===")
    print(f"Buscando PDFs en: {PDF_DIR}")
    pdfs = [f for f in os.listdir(PDF_DIR) if f.lower().endswith('.pdf') and not f.startswith('~')]
    if not pdfs:
        print("No se encontraron PDFs")
        return
    print(f"Se encontraron {len(pdfs)} archivos:")
    for i, f in enumerate(pdfs, 1):
        full = os.path.join(PDF_DIR, f)
        size = os.path.getsize(full) / 1024
        print(f"  {i}. {f} ({size:.0f} KB)")
    print()
    # Group by type
    nu_pdfs = [f for f in pdfs if f.startswith("Nu")]
    cc_pdfs = [f for f in pdfs if "CREDIT_CARD" in f]
    print(f"  Nu Bank: {len(nu_pdfs)} archivos")
    print(f"  Tarjetas: {len(cc_pdfs)} archivos")
    print()
    # Ask for passwords
    nu_pass = input("Contraseña para PDFs de Nu Bank: ")
    cc_pass = input("Contraseña para PDFs de Tarjeta de Crédito: ")
    print()
    # Unlock
    success = 0
    fail = 0
    for f in pdfs:
        full = os.path.join(PDF_DIR, f)
        if f.startswith("Nu"):
            password = nu_pass
        else:
            password = cc_pass
        ok, result = unlock_pdf(full, password)
        if ok:
            print(f"  OK: {f} -> {result}")
            success += 1
        else:
            print(f"  FAIL: {f} - {result}")
            fail += 1
    print(f"\nResultado: {success} desbloqueados, {fail} fallaron")
    if success:
        print(f"PDFs desbloqueados en: {OUT_DIR}")

if __name__ == "__main__":
    main()
