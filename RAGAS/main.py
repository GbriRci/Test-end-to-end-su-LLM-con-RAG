# python -m test_RAGAS.main
import os
import pandas as pd
import phoenix as px
from phoenix.otel import register
from openinference.instrumentation.langchain import LangChainInstrumentor
from chatbot.chatbot import (
    get_ragas_database,
    get_ragas_metrics,
    ragas_evaluation,
)

CSV_PATH = "./risultati/AETERNA/risultati_gen_Ollama.csv"
OUTPUT_PATH = "./risultati_prova.csv"


def benchmark_evaluation_only(data):
    # question, groundtruth, difficulty, response,scores, retrieved_contexts
    df = data.copy()
    for col in ["question", "response", "groundtruth"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)
    records = df.to_dict(orient="records")
    dataset = get_ragas_database(records)

    all_metrics = get_ragas_metrics()
    df_scores = ragas_evaluation(dataset, all_metrics)
    return df_scores


def main():
    if not os.path.exists(CSV_PATH):
        print("CSV file not found")
        return
    else:
        df = pd.read_csv(CSV_PATH)
        df = df.iloc[:3].copy()

    phoenix_session = px.launch_app()
    tracer_provider = register(project_name="metriche_ragas")
    LangChainInstrumentor(tracer_provider=tracer_provider).instrument()

    try:
        result = benchmark_evaluation_only(df)
        if result is not None:
            df_out = pd.DataFrame(result)
            df_out.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
            print(f"\nDati salvati in: {OUTPUT_PATH}")

        print("\n-----------------------------")
        print("Premi invio per terminare")
        input()
    except Exception as e:
        print(f"\nERRORE: {e}")
    finally:
        px.close_app()
        pass


if __name__ == "__main__":
    main()
