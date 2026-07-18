import pdfplumber
import sys

def extraer(pdf_path):
    print(f"\n{'='*80}\n{pdf_path}\n{'='*80}")
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages[:3]):  # First 3 pages
            t = page.extract_text()
            if t:
                print(f"\n--- PAGINA {i+1} ---")
                print(t[:3000])

# Nu
extraer(r"data/nu/nu_2026-05_tarjeta_credito.pdf")
extraer(r"data/nu/nu_2026-06_tarjeta_credito.pdf")

# RappiCard
extraer(r"data/rappicard/rappicard_2026-04_tarjeta_credito.pdf")
