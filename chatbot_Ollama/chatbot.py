import os
import time
from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_openai import ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import OllamaEmbeddings
from ragas import EvaluationDataset, RunConfig, evaluate
from ragas.metrics import (
    Faithfulness,
    AnswerRelevancy,
    ContextRecall,
    ContextPrecision,
    NoiseSensitivity,
    SemanticSimilarity,
    AnswerCorrectness,
)
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_core.runnables import RunnablePassthrough
import traceback
from langchain_groq import ChatGroq
from pathlib import Path
from dotenv import load_dotenv
from ragas.run_config import RunConfig
from langchain_google_genai import ChatGoogleGenerativeAI
import os
import google.generativeai as genai
import langchain

# import logging
import numpy as np
from openai import OpenAI

# logging.basicConfig(level=logging.INFO)
langchain.debug = True

load_dotenv(dotenv_path=Path(__file__).with_name(".env"))
genai.configure(api_key=os.getenv("GENAI_API_KEY"))

DATA_PATH = "synthetic_data/"
CHROMA_PATH = "chatbot_Ollama/chroma_db/"
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
    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=250,
        chunk_overlap=30,
    )
    return text_splitter.split_documents(documents)


# EMBEDDING => ritorna una funzionalità di embedding (perchè la usi sia per creare il db che per rispondere)
# DEVE ESSERE LA STESSA CHE USI PER CREARE IL DB, ALTRIMENTI NON FUNZIONA
def get_embeddings_function():
    return OllamaEmbeddings(model="nomic-embed-text-v2-moe")


# istanzioaione del db
def create_chroma_db():
    return Chroma(
        persist_directory=CHROMA_PATH,
        embedding_function=get_embeddings_function(),
        collection_metadata={"hnsw:space": "cosine"},
    )


# istazionae del modello
def get_model():
    return ChatOllama(
        model="qwen2.5:1.5b",
        temperature=0,
        num_predict=256,
        timeout=300,
    )


def get_evaluation_model():
    # return ChatOllama(
    #     model="qwen2.5:7b",
    #     temperature=0,
    #     num_predict=256,
    #     timeout=300,
    #     verbose=True,
    # )
    # return ChatGroq(
    #     temperature=0,
    #     model_name="llama-3.3-70b-versatile",
    #     groq_api_key=os.getenv("GROQ_API_KEY"),
    #     max_retries=3,
    #     timeout=60,
    #     model_kwargs={"response_format": {"type": "text"}},
    # )
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        api_key=os.getenv("GENAI_API_KEY"),
        temperature=0,
        max_retries=5,
        timeout=300,
    )
    # https://openrouter.ai
    # return ChatOpenAI(
    #     model_name="poolside/laguna-m.1:free",
    #     openai_api_key=os.getenv("OPENROUTER_API_KEY"),
    #     openai_api_base="https://openrouter.ai/api/v1",
    #     temperature=0,
    #     max_retries=3,
    #     timeout=180,
    # )
    # return ChatOpenAI(
    #     model="gpt-4.1",
    #     api_key="any",
    #     openai_api_base="http://100.120.12.105:14141/v1",
    #     temperature=0,
    #     max_retries=5,
    #     timeout=300,
    # )


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
    return db


# RAG LOCALLY
def query_rag(query_text: str):
    db = create_chroma_db()
    results = db.similarity_search_with_score(query_text, k=3)
    docs = [doc for doc, score in results]
    scores = [score for doc, score in results]
    SYSTEM_PROMPT = (
        "Sei un assistente tecnico. Rispondi solo basandoti sul contesto fornito."
    )
    PROMPT_TEMPLATE = "Contesto:\n{context}\n\nDomanda: {question}"
    prompt_template = ChatPromptTemplate.from_messages(
        [("system", SYSTEM_PROMPT), ("human", PROMPT_TEMPLATE)]
    )
    context_text = "\n\n---\n\n".join([doc.page_content for doc in docs])
    model = get_model()
    chain = prompt_template | model
    stream_generator = chain.stream({"context": context_text, "question": query_text})
    sources = [doc.metadata.get("id", "N/A") for doc in docs]
    retrieved_texts = [doc.page_content for doc in docs]
    return stream_generator, sources, retrieved_texts, scores


# TESTING CON PYTEST (unit test => "LLM AS A JUDGE")
def validate(question: str, expected_response: str):
    if not question or not expected_response:
        raise ValueError("Question and expected response must be provided.")
    response_stream, _, _ = query_rag(question)
    full_response = ""
    for chunk in response_stream:
        full_response += chunk.content
    prompt = TESTING_PROMT.format(
        expected_response=expected_response,
        actual_response=full_response,
    )
    evaluation_results = get_model().invoke(prompt)
    final_result = evaluation_results.content.strip().lower()
    print(f"\n--- EVALUATION RESULT ---\n{final_result}\n")
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
    # ragas_llm_one = LangchainLLMWrapper(get_model())
    eval_model = get_evaluation_model()
    ragas_llm = LangchainLLMWrapper(eval_model)
    ollama_emb = get_embeddings_function()
    ragas_embeddings = LangchainEmbeddingsWrapper(ollama_emb)
    all_metrics = [
        # Faithfulness(llm=ragas_llm),
        # AnswerRelevancy(llm=ragas_llm, embeddings=ragas_embeddings),
        # ContextPrecision(llm=ragas_llm),
        ContextRecall(llm=ragas_llm),
        # NoiseSensitivity(llm=ragas_llm),
        # SemanticSimilarity(embeddings=ragas_embeddings),
        # AnswerCorrectness(llm=ragas_llm, embeddings=ragas_embeddings),
    ]
    return all_metrics


def ragas_evaluation(dataset, all_metrics):
    final_scores = {}
    run_config = RunConfig(
        max_workers=1,
        timeout=480,
        max_retries=20,
        max_wait=60,
    )
    for metric in all_metrics:
        try:
            print(f"METRICA: {metric.name}")
            result = evaluate(dataset=dataset, metrics=[metric], run_config=run_config)
            score_dict = result.scores[0]
            print(f"--- RISULTATO {metric.name}: {score_dict} ---")
            final_scores.update(score_dict)
            time.sleep(30)
        except Exception as e:
            print(f"ERRORE CRITICO su {metric.name}:")
            traceback.print_exc()
            final_scores[metric.name] = float("nan")
    return final_scores


def main():
    # print("Verifica nuovi documenti...")
    # docs = load_documents()
    # chunks = split_documents(docs)
    # db = add_to_chroma(chunks)

    expected_response = "La Melassa di Antimateria utilizzata in Fase A deve rispettare i seguenti parametri: 34.5% di Anti-Saccarosio"
    question = "Quanto Anti-Saccarosio deve contenere la Melassa di Antimateria utilizzata in Fase A?"
    # print(f"\n--- DOMANDA ---\n{question}")

    # response_stream, sources, retrieved_texts, scores = query_rag(question)
    # full_response = ""
    # print("\n--- RISPOSTA ---")
    # for chunk in response_stream:
    #     print(chunk.content, end="", flush=True)
    #     full_response += chunk.content
    # print("\n")
    # print(f"\n--- FONTI UTILIZZATE ---\n{', '.join(sources)}\n")
    # print(f"\n--- TESTO RECUPERATO ---\n{retrieved_texts}\n")
    # print(f"\n--- PUNTEGGI ---\n{scores}\n")

    retrieved_texts = [
        "Indice di Rifrazione Emotiva1.618 Adimensionale\n1.2 Comportamento Anomalo\nL'Etere Liquido presenta memoria di forma inversa: ricorda dove NON è stato. Questo fenomeno, noto come\nEffetto Amnesia Spaziale, si manifesta a temperature superiori a +200 Gradi Fluttuanti.\n2. Composizione della Melassa di Antimateria\nLa Melassa di Antimateria utilizzata in Fase A deve rispettare i seguenti parametri:\nComponente PercentualeTolleranza\nAnti-Saccarosio 34.5% ±0.8%\nParticelle di Vuoto Condensato 28.2% ±1.2%\nEstratto di Silenzio Liquefatto 19.7% ±0.5%\nStabilizzante E-999 (Polvere di Stelle Spente)12.1% ±0.3%",
        "Logistiche e Gestione Materiali.md 2026-04-09\n2 / 4\nParametro Requisito\nRotazione stock FIFO rigoroso\nShelf life 90 giorni dalla produzione\n2.2 Melassa di Antimateria\nContenitore: Fusti schermati Classe Ω (Codice FUS-Ω-200)\nCapacità fusto: 200 kg netti\nTemperatura stoccaggio: ambiente (15-25°C terrestri)\nUmidità relativa massima: 35%\nImpilamento massimo: 2 fusti\nArea dedicata: Magazzino B, settore B-7 (superficie 85 m²)\n2.3 Sincro-Cristalli Finiti\nClasse QualitàContenitore Quantità per UnitàCodice Imballo\nPremium (P) Cofanetto antilevitazione AL-P112 cristalli PKG-PRM-12",
        "Logistiche e Gestione Materiali.md 2026-04-09\n3 / 4\nMateriale Scorta MinimaPunto di Riordino Lotto EconomicoLead Time\nEtere Liquido 8 bombole 20 bombole 12 bombole 14 giorni\nMelassa Antimateria 4 fusti 10 fusti 8 fusti 21 giorni\nVortexCat 3000 2 kg 5 kg 4 kg 7 giorni\nTè Freddo pH 9.2 200 L 500 L 400 L 3 giorni\nGuarnizioni GRN-SUV-2278 pz 20 pz 24 pz 10 giorni\n4.2 Fornitori Qualificati\nMateriale Fornitore Codice Fornitore Rating\nEtere Liquido EtherCorp UniversaleSUP-001-EC A+\nMelassa AntimateriaAntiMatter Solutions Ltd SUP-002-AM A\nVortexCat 3000 Catalysis Infinita SpASUP-003-CI A\nTè Freddo Oolong Cosmico GmbHSUP-004-OC B+",
    ]
    full_response = "La melassa di antimateria utilizzata in fase A deve contenere 34.5% di anti-saccarosio, con una toleranza di ±0.8%."

    # validate(question=question, expected_response=expected_response)
    database = get_ragas_database(
        question, retrieved_texts, expected_response, full_response
    )
    ragas_evaluation(database, get_ragas_metrics())


if __name__ == "__main__":
    main()
