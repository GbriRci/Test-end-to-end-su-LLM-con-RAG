from langchain_openai import ChatOpenAI
from ragas import EvaluationDataset, evaluate
from ragas.metrics import Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall
from ragas.metrics import NoiseSensitivity, AnswerAccuracy, ContextRelevance, ResponseGroundedness
from ragas.metrics import FactualCorrectness, SemanticSimilarity
from ragas.llms import LangchainLLMWrapper
from langchain_huggingface import HuggingFaceEmbeddings
from ragas.embeddings import LangchainEmbeddingsWrapper
import traceback
import os

os.environ["HF_TOKEN"] = os.getenv("HF_TOKEN")

llm = ChatOpenAI(
    base_url="http://127.0.0.1:1234/v1",
    api_key="lm-studio",
    model_name="qwen2.5-1.5b-instruct",
    temperature=0,
)

hf_embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={'device': 'cpu'}
)
ragas_embeddings = LangchainEmbeddingsWrapper(hf_embeddings)

ragas_llm = LangchainLLMWrapper(llm)

# question = "Quanti stadi ha la luna?"
# context = ["La luna ha 8 stadi principali: nuova, crescente, primo quarto, gibbosa crescente, piena, gibbosa calante, ultimo quarto e calante."]
# ground_truth_text = "La luna ha 8 stadi."
question="What is the Life Insurance Corporation of India (LIC) known for?"
context="The Life Insurance Corporation of India (LIC) is the largest insurance company in India, established in 1956 through the nationalization of the insurance industry. It is known for managing a large portfolio of investments."
retrieved_contexts=[
    "The Life Insurance Corporation of India (LIC) was established in 1956 following the nationalization of the insurance industry in India.",
    "LIC is the largest insurance company in India, with a vast network of policyholders and huge investments.",
    "As the largest institutional investor in India, LIC manages substantial funds, contributing to the financial stability of the country.",
    "The Indian economy is one of the fastest-growing major economies in the world, thanks to sectors like finance, technology, manufacturing etc."
]

answer = llm.invoke(f"Answer just based on the provided context: {context}. Question: {question}").content

# print(type(question), type(context), type(answer), type(retrieved_contexts), retrieved_contexts)

data = [
    {
        "user_input": question,
        "response": answer,
        # quello che trova, (chiunk)
        "retrieved_contexts": retrieved_contexts,
        # testo roiginale nel vector db
        "reference": context
    }
]
dataset = EvaluationDataset.from_list(data)

all_metrics = [
    ("faithfulness", Faithfulness(llm=ragas_llm)),
    ("answer_relevancy", AnswerRelevancy(llm=ragas_llm, embeddings=ragas_embeddings)),
    ("context_precision", ContextPrecision(llm=ragas_llm)),
    ("context_recall", ContextRecall(llm=ragas_llm)),
    # ("noise_sensitivity", NoiseSensitivity(llm=ragas_llm)),
    ("answer_accuracy", AnswerAccuracy(llm=ragas_llm)),
    ("context_relevance", ContextRelevance(llm=ragas_llm)),
    ("response_groundedness", ResponseGroundedness(llm=ragas_llm)),
    ("factual_correctness", FactualCorrectness(llm=ragas_llm)),
    ("semantic_similarity", SemanticSimilarity(embeddings=ragas_embeddings)),
]

print(question)
print(answer)

for name, m in all_metrics:
    try:
        r = evaluate(dataset=dataset, metrics=[m], raise_exceptions=True)
        print(name, r)
    except Exception as e:
        print(f"\n--- {name} FAILED ---")
        traceback.print_exc()