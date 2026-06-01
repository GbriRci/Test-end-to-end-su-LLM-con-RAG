# python -m evaluation_benchmark.evaluationBenchmarks
import ast
import json
import pandas as pd
from chatbot_Ollama.chatbot import (
    query_rag,
    get_ragas_database,
    get_ragas_metrics,
    ragas_evaluation,
)


def benchmark_answer_and_evaluation():
    with open("./golden_dataset/question.json", "r", encoding="utf-8") as f:
        file = json.load(f)
    results = []
    for row in file:
        print(f"Valutando: {row['question']}")
        response_stream, sources, texts, retrieval_scores = query_rag(row["question"])
        response_text = "".join(
            chunk.content for chunk in response_stream if hasattr(chunk, "content")
        )
        dataset = get_ragas_database(
            row["question"], texts, row["groundtruth"], response_text
        )
        metrics = ragas_evaluation(dataset, get_ragas_metrics())
        row = {
            "question": [row["question"]],
            "groundtruth": [row["groundtruth"]],
            "difficulty": [row["difficulty"]],
            "response": response_text,
            "scores": retrieval_scores,
            "sources": sources,
        }
        row.update(metrics)
        results.append(row)
    return results


def benchmark_evaluation_only():
    with open("risultati/AETERNA/risultati_gen_Ollama.csv", "r", encoding="utf-8") as f:
        file_rows = pd.read_csv(f).to_dict(orient="records")
    target_rows = file_rows[0:50]
    dataset = get_ragas_database(target_rows)
    all_metrics = get_ragas_metrics()
    df_scores = ragas_evaluation(dataset, all_metrics)
    if df_scores is not None:
        df_originale = pd.DataFrame(target_rows)
        df_scores = df_scores.drop(columns=["user_input", "response", "retrieved_contexts", "reference"], errors="ignore")
        df_finale = pd.concat([df_originale, df_scores], axis=1)
        return df_finale.to_dict(orient="records")
    return target_rows


if __name__ == "__main__":
    # raw_results = benchmark_answer_and_evaluation()
    raw_results = benchmark_evaluation_only()
    df = pd.DataFrame(raw_results)
    filename = "risultati/risultati_eval_5-mini.csv"
    df.to_csv(filename, index=False, encoding="utf-8-sig")
    print(f"\nDati salvati in: {filename}")
    # print("\n--- MEDIE TOTALI ---")
    # print(
    #     df.drop(
    #         columns=[
    #             "question",
    #             "groundtruth",
    #             "difficulty",
    #             "response",
    #             "scores",
    #             "sources",
    #         ]
    #     ).mean()
    # )
