import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from query_engine import (
    INDEX_DIR,
    create_query_engine,
    load_index,
    query_with_metadata,
    setup_llama,
)

PROJECT_DIR = SCRIPT_DIR.parent
GOLDEN_QUERIES_PATH = PROJECT_DIR / "data" / "golden_queries.json"
REPORT_PATH = PROJECT_DIR / "output" / "benchmark_report.json"
PLOT_PATH = PROJECT_DIR / "output" / "benchmark_plot.png"


def load_golden_queries(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def run_benchmark(query_engine, golden_queries, iterations=3):
    """Esegue il benchmark su tutte le query (multiple iterazioni)"""
    print("Esecuzione benchmark...")
    print(
        f"   {len(golden_queries)} query x {iterations} iterazioni = "
        f"{len(golden_queries) * iterations} test"
    )
    print()

    results = []

    for test in golden_queries:
        query = test['query']

        for i in range(iterations):
            start = time.perf_counter()
            result = query_with_metadata(query_engine, query)
            end = time.perf_counter()
            latency_ms = (end - start) * 1000

            response = result['response']
            sources = result.get('sources', [])
            top_source = sources[0] if sources else {}

            tripletta_ok = test.get('expected_tripletta', '') in top_source.get('tripletta', '')
            assegnazione_ok = test.get('expected_assegnazione', '') in top_source.get('assegnazione', '')
            marca_ok = test.get('expected_marca', '') in top_source.get('marca', '')

            if not test.get('expected_tripletta'):
                tripletta_ok = True
            if not test.get('expected_assegnazione'):
                assegnazione_ok = True
            if not test.get('expected_marca'):
                marca_ok = True

            avg_score = statistics.mean([s['score'] for s in sources]) if sources else 0

            results.append({
                'test_id': test['id'],
                'query': query,
                'iteration': i + 1,
                'latency_ms': latency_ms,
                'num_sources': len(sources),
                'avg_score': avg_score,
                'top_score': top_source.get('score', 0) if sources else 0,
                'top_path': top_source.get('path', '') if sources else '',
                'top_tripletta': top_source.get('tripletta', '') if sources else '',
                'top_assegnazione': top_source.get('assegnazione', '') if sources else '',
                'top_marca': top_source.get('marca', '') if sources else '',
                'response_preview': response[:300],
                'tripletta_ok': tripletta_ok,
                'assegnazione_ok': assegnazione_ok,
                'marca_ok': marca_ok
            })

            print(f"   OK {test['id']} (iter {i + 1}) - {latency_ms:.2f}ms", end="\r")
    print()
    return results


def compute_metrics(results):
    """Calcola metriche aggregate"""
    latencies = [r['latency_ms'] for r in results]
    latencies_sorted = sorted(latencies)
    n = len(latencies_sorted)

    p95_idx = int(0.95 * n)
    p95 = latencies_sorted[p95_idx] if p95_idx < n else latencies_sorted[-1]

    intra_query_variance = 0
    if len(set(r['test_id'] for r in results)) > 1:
        test_ids = set(r['test_id'] for r in results)
        intra_variances = []
        for tid in test_ids:
            tid_latencies = [r['latency_ms'] for r in results if r['test_id'] == tid]
            if len(tid_latencies) > 1:
                intra_variances.append(statistics.variance(tid_latencies))
        intra_query_variance = statistics.mean(intra_variances) if intra_variances else 0

    return {
        'total_tests': len(results),
        'unique_queries': len(set(r['test_id'] for r in results)),
        'avg_latency_ms': statistics.mean(latencies),
        'median_latency_ms': statistics.median(latencies),
        'p50_latency_ms': statistics.median(latencies),
        'p95_latency_ms': p95,
        'min_latency_ms': min(latencies),
        'max_latency_ms': max(latencies),
        'std_latency_ms': statistics.stdev(latencies) if len(latencies) > 1 else 0,
        'intra_query_variance_ms': intra_query_variance,
        'avg_num_sources': statistics.mean([r['num_sources'] for r in results]),
        'avg_score': statistics.mean([r['avg_score'] for r in results]),
        'avg_top_score': statistics.mean([r['top_score'] for r in results]),
        'tripletta_accuracy': sum(1 for r in results if r['tripletta_ok']) / len(results) * 100,
        'assegnazione_accuracy': sum(1 for r in results if r['assegnazione_ok']) / len(results) * 100,
        'marca_accuracy': sum(1 for r in results if r['marca_ok']) / len(results) * 100,
        'overall_accuracy': sum(
            1 for r in results if r['tripletta_ok'] and r['assegnazione_ok']
        ) / len(results) * 100
    }


def generate_report(metrics, results, output_path):
    report = {
        'timestamp': datetime.now().isoformat(),
        'metrics': metrics,
        'results': results
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Report salvato in {output_path}")


def plot_results(results, metrics, output_path):
    df = pd.DataFrame(results)
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    test_medians = df.groupby('test_id')['latency_ms'].median().sort_values()
    axes[0, 0].barh(test_medians.index, test_medians.values, color='steelblue')
    axes[0, 0].axvline(x=500, color='red', linestyle='--', label='Target 500ms')
    axes[0, 0].set_title('Latenza Mediana per Query')
    axes[0, 0].set_xlabel('ms')
    axes[0, 0].legend()

    axes[0, 1].hist(df['latency_ms'], bins=20, color='skyblue', edgecolor='black')
    axes[0, 1].axvline(
        metrics['avg_latency_ms'],
        color='green',
        label=f"Media: {metrics['avg_latency_ms']:.1f}ms"
    )
    axes[0, 1].set_title('Distribuzione delle Latenze')
    axes[0, 1].set_xlabel('ms')
    axes[0, 1].legend()

    accuracies = ['tripletta_accuracy', 'assegnazione_accuracy', 'marca_accuracy', 'overall_accuracy']
    values = [metrics[a] for a in accuracies]
    axes[1, 0].bar(
        ['Tripletta', 'Assegnazione', 'Marca', 'Overall'],
        values,
        color=['#2ecc71', '#2ecc71', '#2ecc71', '#3498db']
    )
    axes[1, 0].axhline(y=90, color='red', linestyle='--', label='Target 90%')
    axes[1, 0].set_title('Accuratezza sul top chunk (%)')
    axes[1, 0].set_ylim(0, 100)
    axes[1, 0].legend()

    test_ids = df['test_id'].unique()
    axes[1, 1].boxplot(
        [df[df['test_id'] == tid]['top_score'] for tid in test_ids],
        tick_labels=test_ids
    )
    axes[1, 1].set_title('Distribuzione Top Score per Query')
    axes[1, 1].set_ylabel('Score')
    axes[1, 1].tick_params(axis='x', rotation=45)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    print(f"Grafico salvato in {output_path}")
    plt.close()


def print_summary(metrics):
    """Stampa un riassunto formattato del benchmark"""
    print("\n" + "=" * 70)
    print("RIEPILOGO BENCHMARK")
    print("=" * 70)

    print("\nLatenza:")
    print(f"   Media:     {metrics['avg_latency_ms']:.2f} ms")
    print(f"   Mediana:   {metrics['median_latency_ms']:.2f} ms")
    print(f"   P95:       {metrics['p95_latency_ms']:.2f} ms")
    print(f"   Min/Max:   {metrics['min_latency_ms']:.2f} / {metrics['max_latency_ms']:.2f} ms")
    print(f"   Dev. Std:  {metrics['std_latency_ms']:.2f} ms (tra query diverse)")
    print(f"   Varianza intra-query: {metrics.get('intra_query_variance_ms', 0):.2f} ms²")

    print("\nRetrieval:")
    print(f"   Fonti medie:     {metrics['avg_num_sources']:.1f} chunk")
    print(f"   Score medio:     {metrics['avg_score']:.3f}")
    print(f"   Top score medio: {metrics['avg_top_score']:.3f}")

    print("\nAccuratezza (sul top chunk):")
    print(f"   Tripletta:      {metrics['tripletta_accuracy']:.1f}%")
    print(f"   Assegnazione:   {metrics['assegnazione_accuracy']:.1f}%")
    print(f"   Marca:          {metrics['marca_accuracy']:.1f}%")
    print(f"   OVERALL:        {metrics['overall_accuracy']:.1f}%")

    print("\nCampione test:")
    print(f"   Totale test:    {metrics['total_tests']}")
    print(f"   Query uniche:   {metrics['unique_queries']}")


if __name__ == "__main__":
    print("=" * 70)
    print("EON RAG - BENCHMARK COMPLETO")
    print("=" * 70)

    if not (INDEX_DIR / "docstore.json").exists():
        print(f"Indice non trovato in {INDEX_DIR}")
        exit(1)

    setup_llama()
    index = load_index(INDEX_DIR)
    query_engine = create_query_engine(index, use_rerank=True)

    golden_queries = load_golden_queries(GOLDEN_QUERIES_PATH)
    print(f"Caricate {len(golden_queries)} query di benchmark\n")

    results = run_benchmark(query_engine, golden_queries, iterations=3)
    metrics = compute_metrics(results)

    generate_report(metrics, results, REPORT_PATH)
    print_summary(metrics)
    plot_results(results, metrics, PLOT_PATH)

    print("\nBenchmark completato!")
    print(f"Report: {REPORT_PATH}")
    print(f"Grafico: {PLOT_PATH}")
