import os
import time
import json
from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_openai import ChatOpenAI, data
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
    LLMContextPrecisionWithReference,
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
import numpy as np
from openai import OpenAI
import pandas as pd
import ast
from langchain_core.output_parsers import JsonOutputParser
from langchain_nomic import NomicEmbeddings
from pathlib import Path

# logging.basicConfig(level=logging.INFO)
langchain.debug = True

load_dotenv(dotenv_path=Path(__file__).with_name(".env"))
genai.configure(api_key=os.getenv("GENAI_API_KEY"))
BASE_DIR = Path(__file__).resolve().parent

DATA_PATH = "synthetic_data/"
CHROMA_PATH_ANTIMATERIA = "../generate_vector_DB/chroma_db_ANTIMATERIA/"
# CHROMA_PATH_AETERNA = "../generate_vector_DB/chroma_db_AETERNA/"
CHROMA_PATH_AETERNA = str(BASE_DIR.parent / "generate_vector_DB" / "chroma_db_AETERNA")
QUESTION_PATH = "../generate_synthetic_data/golden_dataset.json"


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
SYSTEM_PROMPT = """You are a helpful assistant for answering questions based on the provided context."""
SYSTEM_DECOMPOSITION_PROMPT = """
        Sei un ingegnere software esperto di sistemi RAG e architetture dati (telemetria, monitoraggio, pipeline di remediation).
        Il tuo compito è prendere una macro-domanda complessa (Multi-hop) e scomporla in sotto-domande atomiche, semplici e INDIPENDENTI.

        REGOLE TASSATIVE DI SCOMPOSIZIONE:
            1. NO COPIA-INCOLLA: Ogni sotto-domanda deve essere breve (massimo 10-15 parole) e focalizzata su UN SOLO concetto specifico. Non riprodurre l'intera stringa della domanda originale in ogni sotto-domanda.
            2. DIVISIONE DEL FLUSSO: Se la domanda richiede una pipeline o un flusso (es. raccolta, aggregazione, analisi, remediation), spacca il flusso in step cronologici o logici indipendenti (es. Ingestione dati, Storage/Analisi, Azioni di Remediation).
            3. NON separare artificialmente 'fasi' e 'componenti' se riguardano lo stesso step tecnico (es. Invece di chiedere 'quali fasi' e 'quali componenti' per la raccolta, chiedi: 'Come e tramite quali componenti avviene la raccolta dei dati?').
            4. MASSIMO 3-4 sotto-domande in totale.

        Devi rispondere TASSATIVAMENTE in formato JSON con la chiave 'sub_questions' contenente una lista di stringhe.
        Esempio di output: {{"sub_questions": ["Come avviene la raccolta e l'aggregazione delle metriche?", "Come funziona il flusso di alerting e remediation?", "In che modo il Ledger garantisce sicurezza e compliance?"]}}
        """
DECOMPOSITION_PROMPT = """Scomponi questa domanda: {question}"""
SYSTEM_PROMPT_RAG = (
    "Sei un assistente tecnico. Rispondi solo basandoti sul contesto fornito."
)
PROMPT_TEMPLATE = "Contesto:\n{context}\n\nDomanda: {question}"


def get_embeddings_function():
    return OllamaEmbeddings(model="nomic-embed-text-v2-moe")
    # return NomicEmbeddings(model="nomic-embed-text-v2")
    # return OllamaEmbeddings(model="bge-m3")


def create_chroma_db():
    return Chroma(
        persist_directory=CHROMA_PATH_AETERNA,
        embedding_function=get_embeddings_function(),
        collection_metadata={"hnsw:space": "cosine"},
    )


def get_model(temperature=0):
    # return ChatOllama(
    #     model="qwen2.5:1.5b",
    #     temperature=temperature,
    #     num_predict=512,
    #     timeout=300,
    # )
    return ChatOpenAI(
        model="gpt-4.1",
        api_key="any",
        openai_api_base="http://100.120.12.105:14141/v1",
        temperature=0,
        max_retries=5,
        timeout=300,
    )


def get_evaluation_model(temperature=0):
    # return ChatOllama(
    #     model="qwen2.5:7b",
    #     temperature=temperature,
    #     format="json",
    #     num_predict=512,
    #     timeout=300,
    #     verbose=True,
    #     num_ctx=8192,
    # )
    # return ChatGroq(
    #     temperature=0,
    #     model_name="llama-3.3-70b-versatile",
    #     groq_api_key=os.getenv("GROQ_API_KEY"),
    #     max_retries=3,
    #     timeout=60,
    #     model_kwargs={"response_format": {"type": "text"}},
    # )
    # return ChatGoogleGenerativeAI(
    #     model="gemini-2.5-flash",
    #     api_key=os.getenv("GENAI_API_KEY"),
    #     temperature=0,
    #     max_retries=5,
    #     timeout=300,
    # )
    # https://openrouter.ai
    # return ChatOpenAI(
    #     model_name="poolside/laguna-m.1:free",
    #     openai_api_key=os.getenv("OPENROUTER_API_KEY"),
    #     openai_api_base="https://openrouter.ai/api/v1",
    #     temperature=0,
    #     max_retries=3,
    #     timeout=180,
    # )
    return ChatOpenAI(
        # model="gpt-5-mini",
        model="gpt-4.1",
        api_key="any",
        openai_api_base="http://100.120.12.105:14141/v1",
        temperature=temperature,
        max_retries=3,
        timeout=300,
    )


# RAG LOCALLY
def query_rag(query_text: str):
    db = create_chroma_db()
    results = db.similarity_search_with_score(query_text, k=3)
    docs = [doc for doc, score in results]
    scores = [score for doc, score in results]
    prompt_template = ChatPromptTemplate.from_messages(
        [("system", SYSTEM_PROMPT_RAG), ("human", PROMPT_TEMPLATE)]
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


def query_decomposition(query_text: str):
    model = get_evaluation_model()
    decomposition_prompt = ChatPromptTemplate.from_messages(
        [("system", SYSTEM_DECOMPOSITION_PROMPT), ("human", DECOMPOSITION_PROMPT)]
    )
    decomposition_chain = decomposition_prompt | model | JsonOutputParser()
    original_question = query_text
    try:
        response = decomposition_chain.invoke({"question": original_question})
        sub_questions = response.get("sub_questions", [original_question])
    except Exception as e:
        print(f"Errore nella scomposizione, utilizzo la domanda originale: {e}")
        sub_questions = [original_question]
    print(f"\n--- SOTTO-DOMANDE GENERATE ---\n{sub_questions}\n")
    return sub_questions


def get_ragas_database(rows_list):
    data = []
    for row in rows_list:
        raw_context = row.get("retrieved_contexts", "")
        retrieved_chunks = []
        if isinstance(raw_context, str):
            raw_context = raw_context.strip()
            if raw_context.startswith("[") and raw_context.endswith("]"):
                try:
                    retrieved_chunks = ast.literal_eval(raw_context)
                except Exception as e:
                    print(f"[ERROR] Errore nel parsing letterale del contesto: {e}")
                    retrieved_chunks = [raw_context]
            else:
                retrieved_chunks = [raw_context]
        elif isinstance(raw_context, list):
            retrieved_chunks = [str(i) for i in raw_context]
        else:
            retrieved_chunks = [str(raw_context)]
        data.append(
            {
                "user_input": row["question"],
                "response": row["response"],
                "retrieved_contexts": retrieved_chunks,
                "reference": row["groundtruth"],
            }
        )
    return EvaluationDataset.from_list(data)


# def get_ragas_database(rows_list):
#     data = []
#     for row in rows_list:
#         try:
#             if isinstance(row["retrieved_contexts"], str):
#                 retrieved_chunks = ast.literal_eval(row["retrieved_contexts"])
#             else:
#                 retrieved_chunks = row["retrieved_contexts"]
#         except Exception:
#             retrieved_chunks = [row["retrieved_contexts"]]
#         original_question = row.get("question")
#         difficulty = str(row.get("difficulty", "facile")).lower().strip()
#         difficulty = difficulty.replace("[", "").replace("]", "").replace("'", "").replace('"', "").strip()
#         print(f"Difficulty: {difficulty}")
#         if difficulty in ["media", "difficile"]:
#             sub_questions = query_decomposition(original_question)
#             for sub_q in sub_questions:
#                 data.append(
#                     {
#                         "user_input": sub_q,
#                         "response": row["response"],
#                         "retrieved_contexts": retrieved_chunks,
#                         "reference": row["groundtruth"],
#                         "original_question": original_question
#                     }
#                 )
#         else:
#             data.append(
#                 {
#                     "user_input": original_question,
#                     "response": row["response"],
#                     "retrieved_contexts": retrieved_chunks,
#                     "reference": row["groundtruth"],
#                     "original_question": original_question
#                 }
#             )
#     return EvaluationDataset.from_list(data)


def get_ragas_metrics():
    # ragas_llm_one = LangchainLLMWrapper(get_model())
    eval_model = get_evaluation_model(0)
    ragas_llm = LangchainLLMWrapper(eval_model)
    ollama_emb = get_embeddings_function()
    ragas_embeddings = LangchainEmbeddingsWrapper(ollama_emb)
    all_metrics = [
        # AnswerCorrectness(llm=ragas_llm, embeddings=ragas_embeddings),
        # SemanticSimilarity(embeddings=ragas_embeddings),
        # Faithfulness(llm=ragas_llm),
        # ContextRecall(llm=ragas_llm),
        # ContextPrecision(llm=ragas_llm),
        # AnswerRelevancy(llm=ragas_llm, embeddings=ragas_embeddings),
        NoiseSensitivity(llm=ragas_llm),
    ]
    return all_metrics


def ragas_evaluation(dataset, all_metrics):
    run_config = RunConfig(max_workers=1, timeout=400, max_retries=32, max_wait=10)
    try:
        print(f"Avvio valutazione complessiva per {len(dataset)} righe...")
        result = evaluate(dataset=dataset, metrics=all_metrics, run_config=run_config)
        return result.to_pandas()
    except Exception as e:
        print("Errore durante la valutazione")
        traceback.print_exc()
        return None


def answer_question(data):
    results = []
    for row in data:
        question = row.get("question")
        print(f"\n--- DOMANDA ---\n{question}")
        response_stream, sources, retrieved_texts, scores = query_rag(question)
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
            "sources": sources,
            "retrieved_contexts": retrieved_texts,
        }
        results.append(final_row)
    return results


def clean_sources(sources):
    if not sources:
        return []
    prefix = "..\\synthetic_data_AETERNA\\"
    cleaned = []
    for s in sources:
        try:
            if isinstance(s, str) and s.startswith(prefix):
                cleaned.append(s[len(prefix) :])
            else:
                cleaned.append(s)
        except Exception:
            cleaned.append(s)
    return cleaned


def main():
    # print("Verifica nuovi documenti...")
    # docs = load_documents()
    # chunks = split_documents(docs)
    # db = add_to_chroma(chunks)

    # expected_response = "La Melassa di Antimateria utilizzata in Fase A deve rispettare i seguenti parametri: 34.5% di Anti-Saccarosio"
    # question = "Quanto Anti-Saccarosio deve contenere la Melassa di Antimateria utilizzata in Fase A?"
    # question = "Qual è il periodo minimo di autonomia operativa richiesto per una micro-grid secondo lo standard Kyoto 2.0?"
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

    # retrieved_texts = [
    #     "Indice di Rifrazione Emotiva1.618 Adimensionale\n1.2 Comportamento Anomalo\nL'Etere Liquido presenta memoria di forma inversa: ricorda dove NON è stato. Questo fenomeno, noto come\nEffetto Amnesia Spaziale, si manifesta a temperature superiori a +200 Gradi Fluttuanti.\n2. Composizione della Melassa di Antimateria\nLa Melassa di Antimateria utilizzata in Fase A deve rispettare i seguenti parametri:\nComponente PercentualeTolleranza\nAnti-Saccarosio 34.5% ±0.8%\nParticelle di Vuoto Condensato 28.2% ±1.2%\nEstratto di Silenzio Liquefatto 19.7% ±0.5%\nStabilizzante E-999 (Polvere di Stelle Spente)12.1% ±0.3%",
    #     "Logistiche e Gestione Materiali.md 2026-04-09\n2 / 4\nParametro Requisito\nRotazione stock FIFO rigoroso\nShelf life 90 giorni dalla produzione\n2.2 Melassa di Antimateria\nContenitore: Fusti schermati Classe Ω (Codice FUS-Ω-200)\nCapacità fusto: 200 kg netti\nTemperatura stoccaggio: ambiente (15-25°C terrestri)\nUmidità relativa massima: 35%\nImpilamento massimo: 2 fusti\nArea dedicata: Magazzino B, settore B-7 (superficie 85 m²)\n2.3 Sincro-Cristalli Finiti\nClasse QualitàContenitore Quantità per UnitàCodice Imballo\nPremium (P) Cofanetto antilevitazione AL-P112 cristalli PKG-PRM-12",
    #     "Logistiche e Gestione Materiali.md 2026-04-09\n3 / 4\nMateriale Scorta MinimaPunto di Riordino Lotto EconomicoLead Time\nEtere Liquido 8 bombole 20 bombole 12 bombole 14 giorni\nMelassa Antimateria 4 fusti 10 fusti 8 fusti 21 giorni\nVortexCat 3000 2 kg 5 kg 4 kg 7 giorni\nTè Freddo pH 9.2 200 L 500 L 400 L 3 giorni\nGuarnizioni GRN-SUV-2278 pz 20 pz 24 pz 10 giorni\n4.2 Fornitori Qualificati\nMateriale Fornitore Codice Fornitore Rating\nEtere Liquido EtherCorp UniversaleSUP-001-EC A+\nMelassa AntimateriaAntiMatter Solutions Ltd SUP-002-AM A\nVortexCat 3000 Catalysis Infinita SpASUP-003-CI A\nTè Freddo Oolong Cosmico GmbHSUP-004-OC B+",
    # ]
    # full_response = "La melassa di antimateria utilizzata in fase A deve contenere 34.5% di anti-saccarosio, con una toleranza di ±0.8%."

    # # validate(question=question, expected_response=expected_response)
    # database = get_ragas_database(
    #     question, retrieved_texts, expected_response, full_response
    # )
    # ragas_evaluation(database, get_ragas_metrics())

    with open(
        "../generate_synthetic_data/golden_dataset.json", "r", encoding="utf-8"
    ) as f:
        data = json.load(f)

    results = answer_question(data)

    df = pd.DataFrame(results)
    filename = "./risultati_gen_GPT4.1.csv"
    df.to_csv(filename, index=False, encoding="utf-8-sig")

    # question = "Quali sono le principali fasi e componenti coinvolte nel flusso di raccolta, aggregazione, analisi e remediation automatica delle metriche di telemetria nella micro-rete energetica urbana decentralizzata del progetto AETERNA, e come queste garantiscono affidabilità, sicurezza e compliance secondo gli standard Kyoto 2.0 e Bit-Energy?"
    # query_decomposition(question)


if __name__ == "__main__":
    main()
