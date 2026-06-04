# python -m evaluation_benchmark.evaluationBenchmarks
import ast
import json
import os
import pandas as pd
import re
from chatbot_Ollama.chatbot import (
    query_rag,
    get_ragas_database,
    get_ragas_metrics,
    ragas_evaluation,
    get_evaluation_model,
)

TESTING_PROMT = """
        Analizza la corrispondenza semantica globale tra la risposta attesa e la risposta generata dal sistema.

        risposta attesa: {expected_response}
        risposta generata: {answer}
        ---
        Fornisci la tua valutazione sulla correttezza globale usando esclusivamente un valore numerico tra 0.0 e 1.0, dove:
            - 0.0: Risposta totalmente sbagliata, incompleta o allucinata.
            - 0.25: Risposta prevalentemente errata o fuori tracciato.
            - 0.50: Risposta parzialmente corretta ma mancano concetti fondamentali.
            - 0.75: Risposta quasi totalmente corretta con minime omissioni.
            - 1.0: Risposta totalmente corretta e coincidente con la risposta attesa.

        Scrivi SOLO il numero decimale del voto, senza preamboli o spiegazioni (es: 0.75).
        """
TRASH_HOLD_VALUE = 0.5


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
    with open("./risultati_gen_GPT4.1.csv", "r", encoding="utf-8") as f:
        file_rows = pd.read_csv(f).to_dict(orient="records")
    target_rows = file_rows[:20]
    all_metrics = get_ragas_metrics()
    nomi_metriche = [m.name for m in all_metrics]

    for i, row in enumerate(target_rows):
        print(f"Valutazione in corso riga {i+1}/{len(target_rows)}...")

        llm_as_judge_value = llm_as_judge(row["response"], row["groundtruth"])
        print(f"Giudizio preliminare LLM-as-a-Judge: {llm_as_judge_value}")
        row["judge_pre_score"] = llm_as_judge_value

        if llm_as_judge_value >= TRASH_HOLD_VALUE:
            dataset = get_ragas_database([row])
            df_scores = ragas_evaluation(dataset, all_metrics)
            if df_scores is not None:
                df_originale = pd.DataFrame([row])
                df_scores = df_scores.drop(
                    columns=[
                        "user_input",
                        "response",
                        "retrieved_contexts",
                        "reference",
                    ],
                    errors="ignore",
                )
                df_finale = pd.concat([df_originale, df_scores], axis=1)
                yield df_finale.to_dict(orient="records")[0]
            else:
                for metrica in nomi_metriche:
                    row[metrica] = None
                yield row
        else:
            print(f"Risposta insufficiente.")
            for metrica in nomi_metriche:
                if metrica != "noise_sensitivity(mode=relevant)":
                    row[metrica] = 0.0
                else:
                    row[metrica] = 1.0
            yield row


def llm_as_judge(answer: str, expected_response: str):
    prompt = TESTING_PROMT.format(expected_response=expected_response, answer=answer)
    print("\n" + answer + "\n")
    try:
        result = get_evaluation_model().invoke(prompt)
        text_result = result.content.strip()
        match = re.search(r"[-+]?\d*\.\d+|\d+", text_result)
        if match:
            return float(match.group())
        else:
            print(f"Testo ricevuto: '{text_result}' => default 0.0")
            return 0.0
    except Exception as e:
        print(f"Errore: {e} => default 0.0")
        return 0.0


if __name__ == "__main__":
    filename = "./ALTRI_risultati_eval_GPT-4.1.csv"
    if os.path.exists(filename):
        os.remove(filename)

    # raw_results = benchmark_answer_and_evaluation()
    results = []
    for i, riga_valutata in enumerate(benchmark_evaluation_only()):
        results.append(riga_valutata)
        df_parziale = pd.DataFrame(results)
        df_parziale.to_csv(filename, index=False, encoding="utf-8-sig")
        print(f"{i+1} salvata")
