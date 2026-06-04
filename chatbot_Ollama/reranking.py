import os
from sentence_transformers import CrossEncoder
from langchain_core.prompts import ChatPromptTemplate
from chatbot_Ollama.chatbot import create_chroma_db, get_model

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
    results = db.similarity_search_with_score(query_text, k=15)
    raw_docs = [doc for doc, score in results]
    print(
        "Documenti recuperati (prima del reranking):",
        [doc.metadata.get("id", "N/A") for doc in raw_docs],
    )
    reranked_docs = rerank_with_cross_encoder(query_text, raw_docs, top_n=3)
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
    return stream_generator, sources, retrieved_texts, scores


def rerank_with_cross_encoder(question: str, docs: list, top_n: int = 3):
    model = CrossEncoder("BAAI/bge-reranker-base", max_length=512)
    pairs = [[question, doc.page_content] for doc in docs]
    scores = model.predict(pairs)
    for idx, score in enumerate(scores):
        docs[idx].metadata["relevance_score"] = float(score)
    docs_ordinati = sorted(
        docs, key=lambda x: x.metadata["relevance_score"], reverse=True
    )
    return docs_ordinati[:top_n]


if __name__ == "__main__":
    question = "In che modo il protocollo Bit-Energy integra la componente di giustizia distributiva con la gestione delle transazioni energetiche e quali strumenti tecnici vengono utilizzati per garantire equità tra gli utenti?"
    stream, sources, texts, scores = query_rag(question)
    print("Sorgenti (ordinate):", sources)
    print("Punteggi del Reranker:", scores)
    print("\nRisposta in Streaming:")
    for chunk in stream:
        print(chunk, end="", flush=True)
