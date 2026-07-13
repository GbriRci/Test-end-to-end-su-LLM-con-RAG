import asyncio
import re
from langchain_openai import ChatOpenAI
from mcp.server.fastmcp import FastMCP
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from pathlib import Path
import json

BASE_DIR = Path(__file__).resolve().parent
CHROMA_PATH_AETERNA = str(BASE_DIR.parent / "generate_vector_DB" / "chroma_db_AETERNA")
RERANK_PROMPT = """
        Hai la seguente domanda: {question}
        
        E il seguente documento:
        ----------------------
            {document}
        ----------------------
        Puoi dare un punteggio di rilevanza da 0 a 1, dove 1 è altamente rilevante e 0 è irrilevante, 
        per quanto il documento risponde alla domanda? Rispondi solo con il numero.
    """
MCP = FastMCP("mcp-server")


def get_embeddings_function():
    return OllamaEmbeddings(model="nomic-embed-text-v2-moe")


def create_chroma_db():
    return Chroma(
        persist_directory=CHROMA_PATH_AETERNA,
        embedding_function=get_embeddings_function(),
        collection_metadata={"hnsw:space": "cosine"},
    )
  
    
def get_model(temperature=0):
    return ChatOpenAI(
        model="gpt-4.1",
        api_key="any",
        openai_api_base="http://100.120.12.105:14141/v1",
        temperature=temperature,
        max_retries=5,
        timeout=300,
    )


async def reranker_function(question: str, docs: list, top_n: int = 10, temp: float = 0.0):
    model = get_model(temp)
    results = await asyncio.gather(*(score_doc(model, doc, question) for doc in docs))
    docs_ordinati = sorted(results, key=lambda x: x[1], reverse=True)
    return [doc for doc, score in docs_ordinati[:top_n]]


async def score_doc(model, doc, question: str = ""):
    prompt = RERANK_PROMPT.format(question=question, document=doc.page_content)
    result = await model.ainvoke(prompt)
    text = result.content.strip()
    match = re.search(r"0\.\d+|1\.0|1|0", text)
    score = float(match.group()) if match else 0.0
    doc.metadata["relevance_score"] = score
    return (doc, score)
    

# @mcp.resource("greeting://{name}")
# def get_greeting(name: str) -> str:
#     """Get a personalized greeting"""
#     return f"Hello, {name}!"


# @mcp.prompt()
# def greet_user(name: str, style: str = "friendly") -> str:
#     """Generate a greeting prompt"""
#     styles = {
#         "friendly": "Please write a warm, friendly greeting",
#         "formal": "Please write a formal, professional greeting",
#         "casual": "Please write a casual, relaxed greeting",
#     }
#     return f"{styles.get(style, styles['friendly'])} for someone named {name}."


@MCP.tool()
async def query_rag(query_text: str, k_initial: int = 20, top_n: int = 5):
    try:
        db = create_chroma_db()
        results = db.similarity_search_with_score(query_text, k=k_initial)
        pre_rer_docs = [doc for doc, score in results]
        if not pre_rer_docs:
            return json.dumps({
                "context": "Nessun documento trovato",
                "scores": []
            })
        reranked_docs = await reranker_function(query_text, pre_rer_docs, top_n=top_n)
        scores = [doc.metadata.get("relevance_score", 0.0) for doc in reranked_docs]
        formatted_context = []
        for doc in reranked_docs:
            doc_id = doc.metadata.get("id", "N/A")
            score = doc.metadata.get("relevance_score", 0.0)
            block = f"[DOCUMENTO ID: {doc_id}] (Rerank Score: {score:.2f})\n{doc.page_content}"
            formatted_context.append(block) 
        return json.dumps({
            "context": "\n\n---\n\n".join(formatted_context),
            "scores": scores
        })
    except Exception as e:
        return json.dumps({
            "context": f"Errore nel server: {str(e)}",
            "scores": []
        })


if __name__ == "__main__":
    # mcp.run(transport="streamable-http")
    MCP.run(transport="stdio")
    # mcp.run(transport="sse")