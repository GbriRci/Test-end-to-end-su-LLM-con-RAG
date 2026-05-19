import pdfplumber
import pandas as pd
import re
import numpy as np
from sklearn.metrics import mean_absolute_error, cohen_kappa_score
from scipy.stats import spearmanr

DATA_PATH = "./Data.pdf"
CSV_PATH = "../risultati/AETERNA/risultati_eval_GPT4.1.csv"
METRICS = [
    "Faithfulness",
    "Answer_Relevancy",
    "Context_Precision",
    "Context_Recall",
    "Noise_Sensitivity",
    "Semantic_Similarity",
    "Answer_Correctness",
]


def extract_values(pdf_path):
    results = []
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "".join([page.extract_text() + "\n" for page in pdf.pages])
    questions = re.split(r"Question \d+:", full_text)

    for i in range(1, len(questions)):
        content = questions[i]
        domanda_text = content.split("Ground Truth:")[0].strip()
        metrics = {
            "ID": i,
            "Question": domanda_text,
            "Faithfulness": get_metric(r"Faithfulness[\s\S]*?(\d\.\d+)", content),
            "Answer_Relevancy": get_metric(
                r"Answer Relevancy[\s\S]*?(\d\.\d+)", content
            ),
            "Context_Precision": get_metric(
                r"Context Precision[\s\S]*?(\d\.\d+)", content
            ),
            "Context_Recall": get_metric(r"Context Recall[\s\S]*?(\d\.\d+)", content),
            "Noise_Sensitivity": get_metric(
                r"Noise Sensitivity[\s\S]*?(\d\.\d+)", content
            ),
            "Semantic_Similarity": get_metric(
                r"Semantic Similarity[\s\S]*?(\d\.\d+)", content
            ),
            "Answer_Correctness": get_metric(
                r"Answer Correctness[\s\S]*?(\d\.\d+)", content
            ),
        }
        results.append(metrics)
    return pd.DataFrame(results)


def get_metric(pattern, block):
    match = re.search(pattern, block, re.IGNORECASE)
    if match:
        val_str = match.group(1).replace(",", ".")
        try:
            return float(val_str)
        except ValueError:
            return np.nan
    return np.nan


def clear_csv(csv_path):
    df = pd.read_csv(csv_path)
    df["ID"] = range(1, len(df) + 1)
    df_final = df[
        [
            "ID",
            "question",
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_recall",
            "noise_sensitivity(mode=relevant)",
            "semantic_similarity",
            "answer_correctness",
        ]
    ]
    return df_final.rename(
        columns={
            "ID": "ID",
            "question": "Question",
            "faithfulness": "Faithfulness",
            "answer_relevancy": "Answer_Relevancy",
            "context_precision": "Context_Precision",
            "context_recall": "Context_Recall",
            "noise_sensitivity(mode=relevant)": "Noise_Sensitivity",
            "semantic_similarity": "Semantic_Similarity",
            "answer_correctness": "Answer_Correctness",
        }
    )


def main():
    df_manuale = extract_values(DATA_PATH)
    # print(df_manuale.head())
    df_manuale.drop("Question", axis=1, inplace=True)
    df_manuale = df_manuale.add_suffix("_man")
    # print(df_manuale.head())

    df_gpt_eval = clear_csv(CSV_PATH)
    # print(df_gpt_eval.head())
    df_gpt_eval.drop("Question", axis=1, inplace=True)
    df_gpt_eval = df_gpt_eval.add_suffix("_model")
    # print(df_gpt_eval.head())

    df = pd.merge(df_manuale, df_gpt_eval, left_on="ID_man", right_on="ID_model")
    # print(df.head())
    # print(df.info())

    for col in METRICS:
        s1 = df[f"{col}_man"]
        s2 = df[f"{col}_model"]
        mask = s1.notna() & s2.notna()
        s1_clean, s2_clean = s1[mask], s2[mask]
        if len(s1_clean) > 1:
            mae = mean_absolute_error(s1_clean, s2_clean)
            spearman = spearmanr(s1_clean, s2_clean).correlation
            cohen = cohen_kappa_score(
                (s1_clean * 3).round().astype(int), (s2_clean * 3).round().astype(int)
            )
            print(f"{col}: MAE={mae:.4f}, Spearman={spearman:.4f}, Cohen={cohen:.4f}")


if __name__ == "__main__":
    main()
