# EON RAG

Sistema **Retrieval-Augmented Generation (RAG)** per l'assistenza tecnica fotovoltaico/termico E.ON.  
Il progetto estrae le soluzioni operative dal manuale PDF *TBS Assistenza Tecnica PV*, le indicizza semanticamente e risponde alle domande degli operatori recuperando tripletta, note, script e assegnazione.

## Obiettivo

Automatizzare la ricerca della procedura corretta quando un operatore descrive un problema cliente (es. *"inverter ZCS con Wi-Fi scollegato"*, *"caldaia ibrida Daikin con perdita d'acqua"*), restituendo la soluzione più pertinente dal manuale tecnico.

## Architettura

Il pipeline è diviso in 4 fasi:

```
PDF (data/)  →  parse_pdf.py  →  chunks.json
                                      ↓
                              build_index.py  →  output/index/
                                      ↓
                              query_engine.py  →  risposte strutturate
                                      ↓
                              benchmark.py     →  report + grafici
```

| Fase | Script | Output |
|------|--------|--------|
| 1 — Parsing | `src/parse_pdf.py` | `output/chunks.json` (112 soluzioni) |
| 2 — Indicizzazione | `src/build_index.py` | `output/index/` (vector store LlamaIndex) |
| 3 — Query Engine | `src/query_engine.py` | `output/query_results.json` |
| 4 — Benchmark | `src/benchmark.py` | `output/benchmark_report.json`, `benchmark_plot.png` |

## Struttura del progetto

```
eon-rag/
├── data/
│   ├── TBS Assistenza Tecnica PV*.pdf   # Manuale sorgente
│   └── golden_queries.json              # Dataset di test (8 query)
├── src/
│   ├── parse_pdf.py                     # Estrazione chunk dal PDF
│   ├── build_index.py                   # Creazione indice vettoriale
│   ├── query_engine.py                  # Motore di query RAG
│   └── benchmark.py                     # Benchmark e metriche
├── output/
│   ├── chunks.json                      # Soluzioni estratte
│   ├── index/                           # Indice persistente
│   ├── query_results.json               # Risultati test query
│   ├── benchmark_report.json            # Report benchmark
│   └── benchmark_plot.png               # Grafici benchmark
├── notebooks/                           # Jupyter notebooks (opzionale)
├── requirements.txt
└── venv/
```

## Tecnologie

| Componente | Tecnologia | Ruolo |
|------------|------------|-------|
| Framework RAG | [LlamaIndex](https://www.llamaindex.ai/) | Orchestrazione retrieval + generazione |
| Parsing PDF | [PyMuPDF](https://pymupdf.readthedocs.io/) (`fitz`) | Estrazione testo strutturato |
| Embedding | OpenAI `text-embedding-3-small` *oppure* HuggingFace `BAAI/bge-small-en-v1.5` | Vettorizzazione chunk |
| LLM | OpenAI `gpt-4o-mini` (opzionale) | Sintesi risposta strutturata |
| Reranking | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Riordino risultati per rilevanza |
| Vector store | LlamaIndex (persistente su disco) | Ricerca per similarità |
| Analisi | pandas, matplotlib | Benchmark e visualizzazioni |
| Vector DB (futuro) | qdrant-client | Pronto per deploy scalabile |

## Setup

### Requisiti

- Python 3.12+
- Windows / Linux / macOS

### Installazione

```powershell
cd eon-rag
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install llama-index-embeddings-huggingface sentence-transformers
```

### Variabili d'ambiente (consigliato)

```powershell
$env:OPENAI_API_KEY = "sk-..."
```

Senza API key il sistema funziona in **modalità locale** (embedding HuggingFace + solo retrieval).

## Utilizzo

```powershell
venv\Scripts\python.exe src\parse_pdf.py      # Fase 1
venv\Scripts\python.exe src\build_index.py    # Fase 2
venv\Scripts\python.exe src\query_engine.py   # Fase 3
venv\Scripts\python.exe src\benchmark.py      # Fase 4
```

## Formato di una soluzione (chunk)

| Campo | Descrizione |
|-------|-------------|
| `id` | Identificativo (`sol_005`) |
| `page` | Pagina PDF |
| `tripletta` | Categoria ticket CRM |
| `note_standard` | Tipo intervento (es. *Inverter ZCS*) |
| `note` | Istruzioni per l'operatore |
| `script` | Testo da leggere al cliente |
| `assegnazione` | Team di escalation |
| `path` | Percorso nell'albero decisionale |
| `marca` | Marca componente estratta da `note_standard`, `note` o `path` |

## Risultati benchmark (ultimo run)

Metriche misurate **sul top chunk** recuperato (non sull'intera risposta). Dettagli in [Benchmark.md](Benchmark.md).

| Metrica | Valore |
|---------|--------|
| Latenza media per query | **377.73 ms** |
| Latenza P95 | **492.20 ms** |
| Latenza max | **850.83 ms** |
| Accuratezza tripletta (top-1) | **100%** |
| Accuratezza assegnazione (top-1) | **75%** |
| Accuratezza marca (top-1) | **87.5%** |
| Accuratezza overall (top-1) | **75%** |

> **Nota:** P99 non è riportato (campione insufficiente, n=24). La deviazione standard (132.52 ms) misura la variabilità **tra query diverse**, non la stabilità intra-query. Il tempo di caricamento modelli non è incluso nelle latenze per-query.

## Limitazioni note

- **Parsing path**: l'albero decisionale non viene ricostruito correttamente; `path` è spesso identico per tutte le soluzioni.
- **Marca**: estratta da `note_standard` → `note` → `path` (in quest'ordine, perché il path è euristico).
- **Embedding locale**: `bge-small-en-v1.5` è english-first; con `OPENAI_API_KEY` i risultati in italiano migliorano.
- **LLM opzionale**: senza OpenAI il sistema restituisce il contesto recuperato anziché una risposta sintetizzata.

## Documentazione aggiuntiva

- [Benchmark.md](Benchmark.md) — Metodologia, tabelle e analisi dettagliata

## Licenza

Progetto didattico — Epicode E.ON RAG.
