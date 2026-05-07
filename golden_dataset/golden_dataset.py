# python -m golden_dataset.golden_dataset
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
    with open(
        "./golden_dataset/risultati/risultati_eval_Ollama.csv", "r", encoding="utf-8"
    ) as f:
        file = pd.read_csv(f).to_dict(orient="records")
    results = []
    for row in file[1:8]:
        print(f"Valutando: {row['question']}")
        try:
            retrieved_chunks = ast.literal_eval(row["retrieved_chunks_text"])
        except:
            retrieved_chunks = [row["retrieved_chunks_text"]]
        dataset = get_ragas_database(
            row["question"],
            retrieved_chunks,
            row["groundtruth"],
            row["response"],
        )
        metrics = ragas_evaluation(dataset, get_ragas_metrics())
        row = {
            "question": row["question"],
            "groundtruth": row["groundtruth"],
            "difficulty": [row["difficulty"]],
            "response": row["response"],
            "scores": row["scores"],
            "sources": row["retrieved_chunks_text"],
        }
        row.update(metrics)
        results.append(row)
    return results


if __name__ == "__main__":
    # raw_results = benchmark_answer_and_evaluation()
    raw_results = benchmark_evaluation_only()
    df = pd.DataFrame(raw_results)
    filename = "./golden_dataset/risultati/nuovo.csv"
    df.to_csv(filename, index=False, encoding="utf-8-sig")
    print(f"\nDati salvati in: {filename}")
    print("\n--- MEDIE TOTALI ---")
    print(
        df.drop(
            columns=[
                "question",
                "groundtruth",
                "difficulty",
                "response",
                "scores",
                "sources",
            ]
        ).mean()
    )
