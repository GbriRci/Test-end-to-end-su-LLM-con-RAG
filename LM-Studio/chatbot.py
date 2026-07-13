from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from ragas import EvaluationDataset, evaluate
from ragas.metrics import (
    ContextPrecision,
    # NoiseSensitivity,
    ContextRecall,
    AnswerAccuracy,
    FactualCorrectness,
    SemanticSimilarity,
    AnswerRelevancy,
    Faithfulness,
    ContextEntityRecall,
)
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
import traceback

DATA_PATH = "synthetic_data/"
CHROMA_PATH = "chatbot_LMStudio/chroma_db/"
PROPT_TEMPLATE = """
        Answer the question based only on the following context: {context}
        
        ---
        Answer the question based on the above context: {question}
        """
TESTING_PROMT = """
        Expected response: {expected_response}
        Actual response: {actual_response}
        ---
        (Answere with 'true' or 'false') Does the actual response match the expected response?
        """
SYSTEM_PROMPT = (
    "You are a helpful assistant for answering questions based on the provided context."
)


# LOAD DATAS
def load_documents():
    document_loader = PyPDFDirectoryLoader(DATA_PATH)
    return document_loader.load()


# SPLITTING => per creare i chunk
def split_documents(documents: list[Document]):
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=80,
        length_function=len,
        is_separator_regex=False,
    )
    return text_splitter.split_documents(documents)


# EMBEDDING => ritorna una funzionalità di embedding (perchè la usi sia per creare il db che per rispondere)
# DEVE ESSERE LA STESSA CHE USI PER CREARE IL DB, ALTRIMENTI NON FUNZIONA
def get_embeddings_function():
    embeddings = OpenAIEmbeddings(
        base_url="http://localhost:1234/v1",
        model="text-embedding-nomic-embed-text-v1.5@q8_0",
        api_key="lm-studio",
        check_embedding_ctx_length=False,
        # nomic-embed non supportano la normalizzazione automatica lato server
        # model_kwargs={"normalize_embeddings": True}
    )
    return embeddings


# istanzioaione del db
def create_chroma_db():
    return Chroma(
        persist_directory=CHROMA_PATH,
        embedding_function=get_embeddings_function(),
        collection_metadata={"hnsw:space": "cosine"},
    )


# istazionae del modello
def get_model():
    return ChatOpenAI(
        base_url="http://localhost:1234/v1",
        model="qwen2.5-1.5b-instruct",
        api_key="lm-studio",  # Chiave finta ma richiesta
        temperature=0,
        max_tokens=2048,
        top_p=0.1,
        seed=26,
        timeout=600,
        max_retries=5,
    )


# ID UNIVOCO CHUNK => per la modifica del DB
def calculate_chunk_ids(chunks):
    last_page_id = None
    current_chunk_index = 0
    for chunk in chunks:
        source = chunk.metadata.get("source")
        page = chunk.metadata.get("page")
        current_page_id = f"{source}:{page}"
        if current_page_id == last_page_id:
            current_chunk_index += 1
        else:
            current_chunk_index = 0
        chunk_id = f"{current_page_id}:{current_chunk_index}"
        last_page_id = current_page_id
        chunk.metadata["id"] = chunk_id
    return chunks


# CREARE IL VECTOR DB (questa funzione permette anche la modifica)
def add_to_chroma(chunks: list[Document]):
    db = create_chroma_db()
    # id sono sempre inclisi di defautl
    existing_items = db.get(include=[])
    existing_ids = set(existing_items["ids"])
    print(f"Erano già presenti id: {len(existing_ids)}")
    chunks_with_ids = calculate_chunk_ids(chunks)
    new_chunks = []
    for chunk in chunks_with_ids:
        if chunk.metadata["id"] not in existing_ids:
            new_chunks.append(chunk)
    if len(new_chunks):
        print(f"Aggiunta di {len(new_chunks)} nuovi chunk...")
        new_chunks_ids = [chunk.metadata["id"] for chunk in new_chunks]
        db.add_documents(new_chunks, ids=new_chunks_ids)
    else:
        print("Nessun nuovo documento da aggiungere.")


# RAG LOCALLY
def query_rag(query_text: str):
    db = create_chroma_db()
    docs_with_scores = db.similarity_search_with_score(query_text, k=5)
    retrieved_texts = [doc.page_content for doc, _score in docs_with_scores]
    sources = [doc.metadata.get("id", "N/A") for doc, _score in docs_with_scores]
    scores = [score for _doc, score in docs_with_scores]
    context_text = "\n\n---\n\n".join(retrieved_texts)
    model = get_model()
    prompt_template = ChatPromptTemplate.from_messages(
        [("system", SYSTEM_PROMPT), ("human", PROPT_TEMPLATE)]
    )
    chain = prompt_template | model
    stream_generator = chain.stream({"context": context_text, "question": query_text})
    return stream_generator, sources, scores, retrieved_texts


# TESTING CON PYTEST (unit test => "LLM AS A JUDGE")
def validate(question: str, expected_response: str):
    if not question or not expected_response:
        raise ValueError("Question and expected response must be provided.")
    response_text, _, _, _ = query_rag(question)
    prompt = TESTING_PROMT.format(
        expected_response=expected_response, actual_response=response_text
    )
    evaluation_results = get_model().invoke(prompt)
    final_result = evaluation_results.content.strip().lower()
    print(f"\n--- VALUTAZIONE LLM AS A JUDGE ---\n{final_result}")
    if "true" in final_result:
        print("Test passed!")
    elif "false" in final_result:
        print("Test failed!")
    else:
        print("Unexpected evaluation result:", evaluation_results.content)
    return evaluation_results.content


# RAGAS
def get_ragas_database(question, retrieved_chunks, gound_truth, response):
    # il retrived context è sempre una lista di stringhe
    if isinstance(retrieved_chunks, str):
        retrieved_chunks = [retrieved_chunks]
    data = [
        {
            "user_input": question,
            "response": response,
            "retrieved_contexts": retrieved_chunks,
            "reference": gound_truth,
        }
    ]
    dataset = EvaluationDataset.from_list(data)
    return dataset


def get_ragas_metrics():
    ragas_llm = LangchainLLMWrapper(get_model())
    ragas_embeddings = LangchainEmbeddingsWrapper(get_embeddings_function())
    all_metrics = [
        Faithfulness(llm=ragas_llm),
        AnswerRelevancy(llm=ragas_llm, embeddings=ragas_embeddings),
        ContextPrecision(llm=ragas_llm),
        ContextRecall(llm=ragas_llm),
        AnswerAccuracy(llm=ragas_llm),
        FactualCorrectness(llm=ragas_llm),
        SemanticSimilarity(embeddings=ragas_embeddings),
        ContextEntityRecall(llm=ragas_llm),
    ]
    return all_metrics


def ragas_evaluation(dataset, all_metrics):
    final_scores = {}
    for metric in all_metrics:
        try:
            result = evaluate(
                dataset=dataset,
                metrics=[metric],
            )
            print (f"\n--- RISULTATI METRICA: {metric.__class__.__name__} ---\n{result.scores[0]}\n")
            final_scores.update(result.scores[0])
        except Exception as e:
            print(f"Error evaluating metric {metric.__class__.__name__}: {e}")
            traceback.print_exc()
    return final_scores


def main():
    print("Verifica nuovi documenti...")
    docs = load_documents()
    chunks = split_documents(docs)
    add_to_chroma(chunks)

    expected_response = "La Melassa di Antimateria utilizzata in Fase A deve rispettare i seguenti parametri: 34.5% di Anti-Saccarosio"
    question = "Qunato Anti-Saccarosio deve contenere la Melassa di Antimateria utilizzata in Fase A?"
    print(f"\n--- DOMANDA ---\n{question}")

    response_stream, sources, scores, retrieved_texts = query_rag(question)

    full_response = ""
    for chunk in response_stream:
        print(chunk.content, end="", flush=True)
        full_response += chunk.content
    print("\n")
    print(f"\n--- RISPOSTA ---\n{full_response}")
    print(f"\n--- FONTI UTILIZZATE ---\n{', '.join(sources)}")
    print(f"\n--- SCORE ---\n{scores}")

    validate(question=question, expected_response=expected_response)

    database = get_ragas_database(
        question, retrieved_texts, expected_response, full_response
    )
    ragas_evaluation(database, get_ragas_metrics())


if __name__ == "__main__":
    main()
