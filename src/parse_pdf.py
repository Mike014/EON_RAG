import fitz
import json
import re
from pathlib import Path

# Percorsi robusti relativi alla posizione dello script
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
OUTPUT_DIR = PROJECT_DIR / "output"
OUTPUT_PATH = OUTPUT_DIR / "chunks.json"


def find_pdf():
    """Trova il PDF in data/: preferisce il nome esatto, altrimenti il primo .pdf disponibile"""
    preferred = DATA_DIR / "TBS Assistenza Tecnica PV.pdf"
    if preferred.exists():
        return preferred
    pdfs = sorted(DATA_DIR.glob("*.pdf"))
    return pdfs[0] if pdfs else preferred


PDF_PATH = find_pdf()


def extract_solution(text, page_num):
    """Estrae tutti i campi da una pagina soluzione"""

    fields = {
        'id': f'sol_{page_num:03d}',
        'page': page_num,
        'tripletta': '',
        'note_standard': '',
        'note': '',
        'assegnazione': '',
        'script': '',
        'tempistiche': ''
    }

    patterns = {
        'tripletta': r'Tripletta:\s*([^\n]+)',
        'note_standard': r'Note Standard:\s*([^\n]+)',
        'note': r'Note:\s*([^\n]+(?:\n\s*[^A-Z][^\n]*)*)',
        'assegnazione': r'Assegnazione:\s*([^\n]+)',
        'script': r'Script:\s*([^\n]+(?:\n\s*[^A-Z][^\n]*)*)',
        'tempistiche': r'Tempistiche?\s*:\s*([^\n]+)'
    }

    for field, pattern in patterns.items():
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            value = match.group(1).strip()
            value = ' '.join(value.split())
            fields[field] = value

    return fields


def parse_pdf(pdf_path):
    """Parsing completo del PDF"""
    doc = fitz.open(pdf_path)

    print(f"Parsing: {pdf_path}")
    print(f"Pagine totali: {len(doc)}\n")

    solutions = []
    current_path = []
    question_keywords = [
        "Dove riscontra", "Di che marca", "Quale problematica",
        "Quale problema", "Ha gia provato", "Quando e stata",
        "C'e stato", "Cosa si e danneggiato", "Da dove proviene"
    ]

    for page_num in range(len(doc)):
        text = doc[page_num].get_text()
        text_clean = text.replace('\n', ' ').strip()

        # Se e una pagina soluzione
        if "Tripletta:" in text_clean:
            solution = extract_solution(text, page_num + 1)
            solution['path'] = current_path.copy()
            solutions.append(solution)
            print(f"Soluzione a pagina {page_num + 1}: {' -> '.join(current_path)}")

        # Se e una pagina domanda, aggiorna il percorso
        elif any(kw in text_clean for kw in question_keywords):
            options = []
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#') and '-' in line:
                    if any(k in line for k in ['Inverter', 'termico', 'Wallbox', 'Batteria',
                                                'ZCS', 'Zucchetti', 'Fox', 'Solar Edge',
                                                'Daikin', 'Sonnen', 'Wi-Fi', 'connessione']):
                        options.append(line.replace('-', '').strip())

            if options:
                current_path.append(options[0])

    total_pages = len(doc)
    doc.close()
    return solutions, total_pages


def enrich_solutions(solutions):
    """Arricchisce le soluzioni con la marca estratta da path e note_standard"""
    enriched = []

    MARCHE = ["ZCS", "Zucchetti", "Solar Edge", "Fox", "Daikin", "Sonnen"]

    for s in solutions:
        marca = "Sconosciuta"

        note_std = s.get('note_standard', '')
        for m in MARCHE:
            if m.lower() in note_std.lower():
                marca = m
                break

        if marca == "Sconosciuta":
            note = s.get('note', '')
            for m in MARCHE:
                if m.lower() in note.lower():
                    marca = m
                    break

        if marca == "Sconosciuta":
            for p in s.get('path', []):
                for m in MARCHE:
                    if m.lower() in p.lower():
                        marca = m
                        break
                if marca != "Sconosciuta":
                    break

        content = f"""Percorso: {' -> '.join(s.get('path', []))}
Tripletta: {s.get('tripletta', '')}
Note Standard: {s.get('note_standard', '')}
Note: {s.get('note', '')}
Assegnazione: {s.get('assegnazione', '')}
Script: {s.get('script', '')}
Marca: {marca}"""

        enriched.append({
            **s,
            'marca': marca,
            'content': content.strip()
        })

    return enriched


if __name__ == "__main__":
    if not PDF_PATH.exists():
        print(f"File non trovato: {PDF_PATH}")
        print("Copia il file 'TBS Assistenza Tecnica PV.pdf' nella cartella data/")
        exit(1)

    solutions, total_pages = parse_pdf(str(PDF_PATH))
    print(f"\nTrovate {len(solutions)} soluzioni")

    enriched = enrich_solutions(solutions)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)

    print(f"\nChunk salvati in {OUTPUT_PATH}")

    print("\n" + "=" * 60)
    print("STATISTICHE")
    print("=" * 60)
    print(f"Totale soluzioni: {len(enriched)}")
    print(f"Pagine analizzate: {total_pages}")

    if enriched:
        print(f"\nESEMPIO PRIMO CHUNK:")
        print(json.dumps(enriched[0], ensure_ascii=False, indent=2)[:800] + "...")
