# Benchmark EON RAG

Report del benchmark eseguito il **13 luglio 2026** (run corretto con metriche sul top chunk e parsing marca aggiornato).

## Metodologia

| Aspetto | Dettaglio |
|---------|-----------|
| Dataset | `data/golden_queries.json` — 8 query golden |
| Iterazioni | 3 per query → **24 test totali** |
| Metrica accuratezza | Valutata sul **top chunk** (`sources[0]`), non sull'intera risposta |
| Latenza | Tempo per singola query (`query_with_metadata`), **escluso** il caricamento modelli |
| Percentili | P95 calcolato su n=24; **P99 non riportato** (campione insufficiente) |
| Varianza | Distinta tra std dev **inter-query** e varianza **intra-query** |

## Configurazione tecnica

| Parametro | Valore |
|-----------|--------|
| Embedding | HuggingFace `BAAI/bge-small-en-v1.5` (locale, CPU) |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| LLM | Non configurato |
| Retrieval | top-5 → rerank → top-3 |
| Chunk indicizzati | 112 |
| Hardware | Windows 10, CPU |

## Metriche aggregate

| Metrica | Valore | Target | Verdetto |
|---------|--------|--------|----------|
| Latenza media | **377.73 ms** | < 500 ms | ✅ |
| Latenza mediana (P50) | **362.98 ms** | — | ✅ |
| Latenza P95 | **492.20 ms** | < 500 ms | ✅ |
| Latenza max | **850.83 ms** | — | ⚠️ Outlier (warm-up reranker) |
| Std dev (inter-query) | **132.52 ms** | — | ⚠️ Variabilità tra query diverse |
| Varianza intra-query | **5858.98 ms²** (~76 ms σ) | — | ⚠️ Primo run più lento per query |
| Fonti medie | **3.0** | — | ✅ |
| Score medio | **2.104** | — | — |
| Top score medio | **2.665** | — | — |
| Accuratezza tripletta (top-1) | **100.0%** | — | ✅ |
| Accuratezza assegnazione (top-1) | **75.0%** | ≥ 90% | ❌ |
| Accuratezza marca (top-1) | **87.5%** | — | ⚠️ |
| **Accuratezza overall (top-1)** | **75.0%** | ≥ 90% | ❌ |

### Note interpretative sulle metriche

- **Std dev 132 ms (inter-query):** riflette che query diverse hanno latenze diverse (es. bench_004 ~237 ms vs bench_001 ~492 ms), non instabilità del sistema.
- **Varianza intra-query ~5859 ms²:** la prima iterazione di alcune query include warm-up del reranker (es. bench_001: 851 ms vs ~472 ms nelle iterazioni successive).
- **P99 rimosso:** con n=24, il percentile 99° non è statisticamente significativo.
- **Marca ora misurata correttamente:** il campo `marca` viene estratto in parsing da `note_standard` → `note` → `path` e propagato nei metadata dell'indice.

## Risultati per query

| ID | Query (sintesi) | Lat. mediana | Top marca | Tripletta | Assegnazione | Marca |
|----|-----------------|--------------|-----------|-----------|--------------|-------|
| bench_001 | Wi-Fi ZCS scollegato | 492.2 ms | ZCS | ✅ | ✅ | ✅ |
| bench_002 | ZCS codice errore | 447.0 ms | ZCS | ✅ | ❌ | ✅ |
| bench_003 | Caldaia ibrida Daikin | 344.0 ms | Daikin | ✅ | ❌ | ✅ |
| bench_004 | Batteria ZCS spenta | 237.1 ms | ZCS | ✅ | ✅ | ✅ |
| bench_005 | Wallbox display spento | 368.2 ms | ZCS | ✅ | ✅ | ✅ |
| bench_006 | Perdita pressione termico | 330.4 ms | ZCS | ✅ | ✅ | ❌ |
| bench_007 | Solar Edge singhiozzo | 448.3 ms | Solar Edge | ✅ | ✅ | ✅ |
| bench_008 | Batterie Sonnen | 231.5 ms | Sonnen | ✅ | ✅ | ✅ |

### Fallimenti

| ID | Campo | Atteso | Top chunk | Causa probabile |
|----|-------|--------|-----------|-----------------|
| bench_002 | Assegnazione | Bo Solutions Elettrico | Nessuna, solo per tracciatura | Reranker preferisce chunk generico |
| bench_003 | Assegnazione | Nessuna, solo per tracciatura | Bo Solutions Termico - Ibrido | Chunk Daikin con escalation diversa |
| bench_006 | Marca | Sconosciuta | ZCS | Query generica → match su impianto ZCS |

## Confronto prima/dopo correzioni

| Metrica | Run precedente | Run corretto | Cambiamento |
|---------|----------------|--------------|-------------|
| Metodo accuratezza | Intera risposta | Top chunk | Più rigoroso |
| Accuratezza assegnazione | 87.5% (sovrastimata) | **75.0%** | Valore reale top-1 |
| Accuratezza marca | 100% (non misurata) | **87.5%** | Ora misurata sul campo `marca` |
| P99 | 475 ms | Rimosso | Campione insufficiente |
| Marca nei chunk | Sempre "Sconosciuta" | ZCS/Daikin/Solar Edge/… | Parsing corretto |

## Tecnologie utilizzate

### Stack RAG

| Layer | Tecnologia | Ruolo |
|-------|------------|-------|
| Orchestrazione | LlamaIndex Core 0.14 | Pipeline retrieval → rerank → risposta |
| Parsing PDF | PyMuPDF | Estrazione 112 soluzioni strutturate |
| Embedding | `BAAI/bge-small-en-v1.5` | Vettori 384-dim, similarità coseno |
| Reranker | `ms-marco-MiniLM-L-6-v2` | Cross-encoder, riordino top-5 → top-3 |
| Vector store | LlamaIndex (disco) | Indice persistente in `output/index/` |
| Query engine | `RetrieverQueryEngine` | Retrieval + post-processing |

### Stack analisi

| Tecnologia | Ruolo |
|------------|-------|
| pandas | Aggregazione e grouping risultati |
| matplotlib | 4 grafici in `benchmark_plot.png` |
| statistics | Media, mediana, P95, varianza intra-query |

### Tecnologie opzionali (non usate)

| Tecnologia | Quando |
|------------|--------|
| OpenAI `text-embedding-3-small` | Con `OPENAI_API_KEY` |
| OpenAI `gpt-4o-mini` | Sintesi risposta strutturata |
| `BAAI/bge-reranker-v2-m3` | Reranker multilingue (fallback) |
| Qdrant | Deploy produzione |

## Grafici

`output/benchmark_plot.png` contiene:

1. Latenza mediana per query (target 500 ms)
2. Distribuzione latenze (istogramma)
3. Accuratezza sul top chunk (target 90%)
4. Boxplot top score per query

## Conclusioni

**Punti di forza:** latenza media 378 ms sotto target; tripletta al 100%; marca misurabile e al 87.5%; retrieval multimarca funzionante (ZCS, Daikin, Solar Edge, Sonnen).

**Aree di miglioramento:** assegnazione top-1 al 75% (target 90%); parsing path ancora euristico; embedding english-first; LLM assente per sintesi risposta.

**Prossimi passi:** configurare `OPENAI_API_KEY`; filtrare per metadata `assegnazione`; migliorare albero decisionale in `parse_pdf.py`.

## File di riferimento

| File | Descrizione |
|------|-------------|
| `output/benchmark_report.json` | Report JSON completo |
| `output/benchmark_plot.png` | Grafici |
| `data/golden_queries.json` | Ground truth |
| `src/benchmark.py` | Script benchmark |
| `src/parse_pdf.py` | Parsing con estrazione marca |
