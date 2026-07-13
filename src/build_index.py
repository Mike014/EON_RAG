import json
import os
from pathlib import Path

from llama_index.core import Document, VectorStoreIndex, Settings
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
CHUNKS_PATH = PROJECT_DIR / "output" / "chunks.json"
INDEX_DIR = PROJECT_DIR / "output" / "index"


def load_chunks(json_path):
    """Carica i chunk dal file JSON della Fase 1"""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def create_documents(chunks):
    """Converte i chunk in Document di LlamaIndex"""
    documents = []

    for chunk in chunks:
        text = f"""Percorso: {' -> '.join(chunk.get('path', []))}

Tripletta: {chunk.get('tripletta', '')}
Note Standard: {chunk.get('note_standard', '')}
Note: {chunk.get('note', '')}
Assegnazione: {chunk.get('assegnazione', '')}
Script: {chunk.get('script', '')}
Tempistiche: {chunk.get('tempistiche', '')}
"""

        doc = Document(
            text=text.strip(),
            metadata={
                'id': chunk.get('id', ''),
                'page': chunk.get('page', 0),
                'path': ' -> '.join(chunk.get('path', [])),
                'tripletta': chunk.get('tripletta', ''),
                'assegnazione': chunk.get('assegnazione', ''),
                'marca': chunk.get('marca', 'Sconosciuta'),
                'note_standard': chunk.get('note_standard', '')
            }
        )
        documents.append(doc)

    return documents


def configure_models():
    """Configura embedding e LLM (OpenAI con fallback HuggingFace locale)"""
    api_key = os.getenv("OPENAI_API_KEY")

    if api_key:
        Settings.embed_model = OpenAIEmbedding(
            model="text-embedding-3-small",
            api_key=api_key
        )
        print("Embedding: OpenAI text-embedding-3-small")

        Settings.llm = OpenAI(
            model="gpt-4o-mini",
            api_key=api_key,
            temperature=0.1
        )
        print("LLM: OpenAI gpt-4o-mini")
        return

    try:
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")
        print("Embedding: HuggingFace bge-small-en-v1.5 (locale)")
    except ImportError:
        raise RuntimeError(
            "OPENAI_API_KEY non impostata e llama-index-embeddings-huggingface non installato.\n"
            "Imposta OPENAI_API_KEY oppure installa: pip install llama-index-embeddings-huggingface"
        )

    print("LLM OpenAI non configurato -> solo retrieval")
    Settings.llm = None


def build_index(documents, persist_dir):
    """Costruisce e salva l'indice vettoriale"""
    print(f"Creazione indice con {len(documents)} documenti...")

    configure_models()

    index = VectorStoreIndex.from_documents(
        documents,
        show_progress=True
    )

    persist_dir.mkdir(parents=True, exist_ok=True)
    index.storage_context.persist(persist_dir=str(persist_dir))
    print(f"Indice salvato correttamente in: {persist_dir}")

    return index


def test_index(index):
    """Test di retrieval con query di esempio"""
    print("\n" + "=" * 70)
    print("TEST DI RETRIEVAL")
    print("=" * 70)

    test_queries = [
        "Cliente ha inverter ZCS con Wi-Fi scollegato, non ha riavviato",
        "Perdita d'acqua dalla caldaia ibrida Daikin dopo collaudo",
        "Batteria ZCS completamente spenta dopo riavvio"
    ]

    if Settings.llm is None:
        retriever = index.as_retriever(similarity_top_k=3)
        for query in test_queries:
            print(f"\nQuery: {query}")
            nodes = retriever.retrieve(query)
            print(f"Fonti recuperate: {len(nodes)}")
            for i, node in enumerate(nodes[:2]):
                path = node.metadata.get('path', 'N/A')
                print(f"   {i + 1}. Score: {node.score:.3f} | {path[:70]}...")
        return

    query_engine = index.as_query_engine(similarity_top_k=3, response_mode="compact")

    for query in test_queries:
        print(f"\nQuery: {query}")
        response = query_engine.query(query)
        print(f"Risposta: {str(response)[:280]}...")

        if hasattr(response, 'source_nodes'):
            print(f"Fonti recuperate: {len(response.source_nodes)}")
            for i, node in enumerate(response.source_nodes[:2]):
                path = node.metadata.get('path', 'N/A')
                print(f"   {i + 1}. Score: {node.score:.3f} | {path[:70]}...")


if __name__ == "__main__":
    if not CHUNKS_PATH.exists():
        print(f"File non trovato: {CHUNKS_PATH}")
        print("Esegui prima la Fase 1 (parse_pdf.py).")
        exit(1)

    chunks = load_chunks(CHUNKS_PATH)
    print(f"Caricati {len(chunks)} chunk dalla Fase 1")

    documents = create_documents(chunks)
    index = build_index(documents, INDEX_DIR)
    test_index(index)

    print("\nFase 2 completata con successo! L'indice vettoriale e pronto.")
