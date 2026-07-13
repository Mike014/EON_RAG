import json
import os
import time
from functools import lru_cache
from pathlib import Path

from llama_index.core import Settings, StorageContext, load_index_from_storage
from llama_index.core.postprocessor import SentenceTransformerRerank
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
INDEX_DIR = PROJECT_DIR / "output" / "index"
RESULTS_PATH = PROJECT_DIR / "output" / "query_results.json"

global_query_engine = None


def setup_llama():
    """Configura embedding e LLM"""
    api_key = os.getenv("OPENAI_API_KEY")

    if api_key:
        Settings.embed_model = OpenAIEmbedding(
            model="text-embedding-3-small",
            api_key=api_key
        )
        print("Embedding: text-embedding-3-small")

        Settings.llm = OpenAI(
            model="gpt-4o-mini",
            api_key=api_key,
            temperature=0.1,
            max_tokens=512
        )
        print("LLM: gpt-4o-mini")
        return

    try:
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")
        print("Embedding: BAAI/bge-small-en-v1.5 (locale)")
    except ImportError:
        raise RuntimeError(
            "OPENAI_API_KEY non impostata e llama-index-embeddings-huggingface non installato."
        )

    print("LLM non disponibile -> modalita solo retrieval")
    Settings.llm = None


def load_index(persist_dir):
    """Carica l'indice salvato su disco"""
    print(f"Caricamento indice da {persist_dir}...")
    storage_context = StorageContext.from_defaults(persist_dir=str(persist_dir))
    index = load_index_from_storage(storage_context)
    print(f"Indice caricato ({len(index.docstore.docs)} documenti)")
    return index


def create_query_engine(index, use_rerank=True):
    """Crea il query engine con retrieval + reranking"""
    retriever = VectorIndexRetriever(
        index=index,
        similarity_top_k=5,
        verbose=False
    )

    node_postprocessors = []
    if use_rerank:
        rerank_models = [
            "cross-encoder/ms-marco-MiniLM-L-6-v2",
            "BAAI/bge-reranker-v2-m3",
        ]
        for model_name in rerank_models:
            try:
                rerank = SentenceTransformerRerank(top_n=3, model=model_name)
                node_postprocessors.append(rerank)
                print(f"Reranking attivato ({model_name})")
                break
            except Exception as exc:
                print(f"Reranking non disponibile per {model_name}: {exc}")

    query_engine = RetrieverQueryEngine.from_args(
        retriever=retriever,
        node_postprocessors=node_postprocessors,
        response_mode="compact",
        verbose=True
    )
    return query_engine


def format_retrieval_response(sources):
    """Formatta una risposta strutturata dai metadata quando non c'e LLM"""
    if not sources:
        return "Nessuna soluzione rilevante trovata."

    source = sources[0]
    return (
        f"Tripletta: {source['tripletta']}\n"
        f"Note Standard: {source['note_standard']}\n"
        f"Assegnazione: {source['assegnazione']}\n"
        f"Script: {source['text_preview']}"
    )


def query_with_metadata(query_engine, question):
    """Esegue una query e restituisce risposta + metadata"""
    start_time = time.perf_counter()

    if Settings.llm is None:
        retriever = query_engine.retriever
        nodes = retriever.retrieve(question)
        for postprocessor in query_engine._node_postprocessors:
            nodes = postprocessor.postprocess_nodes(nodes, query_str=question)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        sources = []
        for node in nodes:
            sources.append({
                'score': float(node.score) if node.score is not None else None,
                'path': node.metadata.get('path', ''),
                'tripletta': node.metadata.get('tripletta', ''),
                'assegnazione': node.metadata.get('assegnazione', ''),
                'note_standard': node.metadata.get('note_standard', ''),
                'marca': node.metadata.get('marca', ''),
                'text_preview': node.text[:200]
            })

        return {
            'question': question,
            'response': format_retrieval_response(sources),
            'sources': sources,
            'latency_ms': elapsed_ms,
            'num_sources': len(sources)
        }

    response = query_engine.query(question)
    elapsed_ms = (time.perf_counter() - start_time) * 1000

    sources = []
    if hasattr(response, 'source_nodes'):
        for node in response.source_nodes:
            sources.append({
                'score': float(node.score) if node.score is not None else None,
                'path': node.metadata.get('path', ''),
                'tripletta': node.metadata.get('tripletta', ''),
                'assegnazione': node.metadata.get('assegnazione', ''),
                'note_standard': node.metadata.get('note_standard', ''),
                'marca': node.metadata.get('marca', ''),
                'text_preview': node.text[:200]
            })

    return {
        'question': question,
        'response': str(response),
        'sources': sources,
        'latency_ms': elapsed_ms,
        'num_sources': len(sources)
    }


@lru_cache(maxsize=100)
def cached_query(question):
    return query_with_metadata(global_query_engine, question)


def run_test_queries(query_engine, test_queries_list):
    """Esegue test su query di esempio"""
    print("\n" + "=" * 80)
    print("TEST QUERY")
    print("=" * 80)

    results = []
    for i, q in enumerate(test_queries_list, 1):
        print(f"\n{'-' * 80}")
        print(f"TEST {i}: {q}")
        print(f"{'-' * 80}")

        result = query_with_metadata(query_engine, q)
        results.append(result)

        print(f"\nLATENZA: {result['latency_ms']:.2f} ms")
        print(f"FONTI: {result['num_sources']} chunk")
        print(f"\nRISPOSTA:\n{result['response'][:500]}...")

        if result['sources']:
            source = result['sources'][0]
            print(f"\nTOP SOURCE:")
            print(f"   Score: {source['score']:.4f}")
            print(f"   Path: {source['path']}")
            print(f"   Tripletta: {source['tripletta']}")
            print(f"   Assegnazione: {source['assegnazione']}")

    return results


def save_results(results, output_path):
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nRisultati salvati in {output_path}")


if __name__ == "__main__":
    print("=" * 80)
    print("EON RAG - QUERY ENGINE")
    print("=" * 80)

    if not (INDEX_DIR / "docstore.json").exists():
        print(f"Indice non trovato in {INDEX_DIR}")
        print("Esegui prima la Fase 2 (build_index.py).")
        exit(1)

    setup_llama()
    index = load_index(INDEX_DIR)

    query_engine = create_query_engine(index, use_rerank=False)
    global_query_engine = query_engine
    print("\nQuery engine pronto!\n")

    test_queries_list = [
        "Cliente ha inverter ZCS, il Wi-Fi e scollegato e non ha riavviato",
        "Inverter ZCS con codice di errore, produzione bassa, installato 3 anni fa",
        "Perdita d'acqua dalla caldaia ibrida, Daikin ha fatto collaudo",
        "Batteria ZCS spenta, riavvio fatto ma non risolve",
        "Wallbox non carica, display spento, installata da 1 anno",
        "Cliente segnala perdita di pressione sull'impianto termico, pressione sempre tra 1.5 e 2",
        "Impianto fotovoltaico con inverter Solar Edge, produzione a singhiozzo quando c'e tanto sole",
        "Cliente vuole assistenza per batterie Sonnen"
    ]

    results = run_test_queries(query_engine, test_queries_list)
    save_results(results, RESULTS_PATH)

    avg_latency = sum(r['latency_ms'] for r in results) / len(results)
    print("\n" + "=" * 80)
    print("STATISTICHE")
    print("=" * 80)
    print(f"Query totali: {len(results)}")
    print(f"Latenza media: {avg_latency:.2f} ms")
    print(f"Latenza min: {min(r['latency_ms'] for r in results):.2f} ms")
    print(f"Latenza max: {max(r['latency_ms'] for r in results):.2f} ms")
    print(f"Fonti medie: {sum(r['num_sources'] for r in results) / len(results):.1f} chunk")

    print("\nFase 3 completata! Il sistema e pronto per rispondere alle domande dei clienti.")
