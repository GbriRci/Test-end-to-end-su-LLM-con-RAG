# python .\chatbot_Ollama\reranking.py
import os
from sentence_transformers import CrossEncoder
from langchain_core.prompts import ChatPromptTemplate
import json
import pandas as pd
from chatbot import clean_sources, create_chroma_db, get_model, create_chroma_db

os.environ["HF_TOKEN"] = os.getenv("HF_TOKEN")

SYSTEM_PROMPT_RAG = """
        Sei un assistente tecnico. Rispondi solo basandoti sul contesto fornito.
    """

PROMPT_TEMPLATE = """
        Contesto: {context}
        
        Rispondi alla domanda basandoti solo sul contesto fornito:
        Domanda: {question}
    """


def query_rag(query_text: str):
    db = create_chroma_db()
    results = db.similarity_search_with_score(query_text, k=20)
    pre_rer_docs = [doc for doc, score in results]
    print(
        "Documenti pre-reranking:",
        [doc.metadata.get("id", "N/A") for doc in pre_rer_docs],
    )
    reranked_docs = reraker_function(query_text, pre_rer_docs, top_n=3)
    sources = [doc.metadata.get("id", "N/A") for doc in reranked_docs]
    retrieved_texts = [doc.page_content for doc in reranked_docs]
    scores = [doc.metadata.get("relevance_score", 0.0) for doc in reranked_docs]
    context_text = "\n\n---\n\n".join(retrieved_texts)
    prompt_template = ChatPromptTemplate.from_messages(
        [("system", SYSTEM_PROMPT_RAG), ("human", PROMPT_TEMPLATE)]
    )
    model = get_model()
    chain = prompt_template | model
    stream_generator = chain.stream({"context": context_text, "question": query_text})
    return stream_generator, sources, retrieved_texts, scores, pre_rer_docs


def reraker_function(question: str, docs: list, top_n: int = 3):
    model = CrossEncoder("BAAI/bge-reranker-base", max_length=512)
    # la struttura per il reranking è una lista di coppie (domanda, testo del documento)
    pairs = [[question, doc.page_content] for doc in docs]
    scores = model.predict(pairs)
    for idx, score in enumerate(scores):
        docs[idx].metadata["relevance_score"] = float(score)
    docs_ordinati = sorted(
        docs, key=lambda x: x.metadata["relevance_score"], reverse=True
    )
    return docs_ordinati[:top_n]

def search_by_id(id_da_cercare: list):
    db = create_chroma_db()
    for target_id in id_da_cercare:
        risultato = db.get(ids=[target_id])
        
        if risultato and risultato['documents']:
            testo_chunk = risultato['documents'][0]
            metadati_chunk = risultato['metadatas'][0]
            print("--------")
            print(testo_chunk) 
            print("--------")          
        else:
            print(f"Chunk non trovati")

  
def answer_question(data):
    results = []
    for row in data:
        question = row.get("question")
        print(f"\n--- DOMANDA ---\n{question}")
        response_stream, sources, retrieved_texts, scores, pre_rer_docs = query_rag(question)
        response_text = "".join(
            chunk.content for chunk in response_stream if hasattr(chunk, "content")
        )
        sources = clean_sources(sources)
        final_row = {
            "question": question,
            "groundtruth": row["ground_truth"],
            "difficulty": row["difficulty"],
            "response": response_text,
            "scores": scores,
            "sources_before_reranking": pre_rer_docs,
            "sources_after_reranking": sources,
            "retrieved_contexts": retrieved_texts,
        }
        results.append(final_row)
    return results


if __name__ == "__main__":
    with open(
        "./generate_synthetic_data/golden_dataset.json", "r", encoding="utf-8"
    ) as f:
        data = json.load(f)

    results = answer_question(data)

    df = pd.DataFrame(results)
    filename = "./risultati_gen_reranking.csv"
    df.to_csv(filename, index=False, encoding="utf-8-sig")

    # print ("Testi Reranking:")
    # for text in retrieved_texts:
    #     print(text)
    # print("\nRisposta in Streaming:")
    # for chunk in stream:
    #     print(chunk.content, end="", flush=True)
    
    # synthetic_data_AETERNA\\
    # id_da_cercare = [
    #     "synthetic_data_AETERNA\\Volume_07_smart_contract_e_tokenizzazione_energetica.md:0:62",
    # ]
    # search_by_id(id_da_cercare)
