import json
import os
import logging
import re
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

logging.basicConfig(level=logging.INFO)

INPUT_FILE = "./json/final_instructions.json"
OUTPUT_FILE = "./golden_dataset.json"
INPUT_DIR = "./generated_md"
PROJECT_NAME = "Progetto AETERNA"

GLOBAL_BLUEPRINT = """AETERNA è un framework di micro-reti energetiche decentralizzate basato su tre livelli: 
        Edge (H-Node domestici), Fog (quartiere) e Cloud (analisi macro)."""

SYSTEM_PROMPT_CONTENT = f"""Sei un sistema di generazione dataset per addestramento AI. 
        Il tuo compito è creare coppie Domanda/Risposta basate ESCLUSIVAMENTE sul testo fornito.
        NON inventare nomi di hardware, date, coefficienti o specifiche tecniche se non sono esplicitamente scritti nel testo.
        Usa i termini '{PROJECT_NAME}', 'Kyoto 2.0' e 'Bit-Energy' solo se appaiono nel contenuto fornito o sono necessari per il contesto."""


PROMPT_QUESTIONS = """Analizza il TESTO fornito e genera una domanda secondo il livello di difficoltà richiesto.

        DIFFICOLTÀ {difficulty}:
        - FACILE: La risposta deve essere presente in modo esplicito nel testo.
        - MEDIA: La risposta richiede di collegare due informazioni distinte nel testo.
        - DIFFICILE: La risposta richiede di sintetizzare un intero paragrafo o processo complesso.
        - IMPOSSIBILE: 
            1. Scegli un concetto reale del testo (es. un protocollo o un hardware).
            2. Inventa una domanda su un dettaglio tecnico o economico che NON è presente (es. versioni software, costi, date esatte, nomi di produttori).
            3. La domanda deve sembrare legittima, ma la risposta NON deve essere deducibile dal testo o dalle tabelle.
            4. NON citare "il testo" o "la tabella" nella domanda.
        
        REGOLE DI FORMATTAZIONE:
        1. Scrivi SOLO il testo della domanda.
        2. NON aggiungere "Question:", "Domanda:", "D:" o prefissi simili.
        3. NON includere la risposta nella domanda.
        4. Inizia direttamente con la prima parola della domanda.

        TITOLO: {title}
        TESTO: {content}"""


PROMPT_ANSWER = """Usa il TESTO fornito per rispondere alla DOMANDA.

        REGOLE DI FORMATTAZIONE:
        1. Fornisci SOLO il testo della risposta.
        2. NON scrivere "Risposta:", "Answer:", o "Il testo dice che...".
        3. NON aggiungere analisi, premesse o conclusioni.
        4. Se la difficoltà è 'impossibile' e il dato manca, scrivi SOLO: "L'informazione non è disponibile nel testo".

        DOMANDA: {question}
        TESTO: {content}"""


def get_model(temperature=0):
    return ChatOpenAI(
        model="gpt-4.1",
        api_key="any",
        openai_api_base="http://100.120.12.105:14141/v1",
        temperature=temperature,
        max_retries=5,
        timeout=300,
    )


def generate_question(title, description, content, difficulty):
    model = get_model()
    messages = [
        SystemMessage(content=SYSTEM_PROMPT_CONTENT),
        HumanMessage(
            content=PROMPT_QUESTIONS.format(
                project_name=PROJECT_NAME,
                title=title,
                description=description,
                content=content,
                difficulty=difficulty,
            )
        ),
    ]
    response = model.invoke(messages)
    return response.content


def generate_answer(content, question):
    model = get_model()
    messages = [
        SystemMessage(content=SYSTEM_PROMPT_CONTENT),
        HumanMessage(content=PROMPT_ANSWER.format(content=content, question=question)),
    ]
    response = model.invoke(messages)
    return response.content


def get_chapter_content(volume_content, chapter_id):
    start_pattern = re.compile(rf"^# Capitolo {chapter_id}:", re.MULTILINE)
    next_cap_pattern = re.compile(rf"^# Capitolo \d+:", re.MULTILINE)
    match = start_pattern.search(volume_content)
    if not match:
        logging.warning(f"Contenuto non trovato per Capitolo {chapter_id}")
        return ""
    start_index = match.start()
    next_match = next_cap_pattern.search(volume_content, match.end())
    end_index = next_match.start() if next_match else len(volume_content)
    return volume_content[start_index:end_index].strip()


def get_difficulty(index):
    difficulties = ["facile", "media", "difficile", "impossibile"]
    return difficulties[index % len(difficulties)]


def create_dataset(data):
    golden_dataset = []
    index = 0
    for volume in data:
        vol_id = f"{volume['volume_id']:02d}"
        vol_title_clean = volume["volume_title"].replace(" ", "_").lower()
        filename = f"Volume_{vol_id}_{vol_title_clean}.md"
        filepath = os.path.join(INPUT_DIR, filename)
        if not os.path.exists(filepath):
            logging.error(f"File non trovato: {filepath}")
            continue

        logging.info(f"--- Elaborazione {filename} ---")
        with open(filepath, "r", encoding="utf-8") as f:
            volume_content = f.read()
        for chapter in volume["chapters"]:
            cap_id = chapter["id"]
            cap_title = chapter["title"]
            content = get_chapter_content(volume_content, cap_id)
            difficulty = get_difficulty(index)
            index += 1

            logging.info(f"Generando => {cap_title}")
            try:
                model = get_model()
                question_prompt = [
                    SystemMessage(content=SYSTEM_PROMPT_CONTENT),
                    HumanMessage(
                        content=PROMPT_QUESTIONS.format(
                            title=cap_title, difficulty=difficulty, content=content
                        )
                    ),
                ]
                question = model.invoke(question_prompt).content.strip()
                question = clean_string(question)

                answer_prompt = [
                    SystemMessage(content=SYSTEM_PROMPT_CONTENT),
                    HumanMessage(
                        content=PROMPT_ANSWER.format(content=content, question=question)
                    ),
                ]
                answer = model.invoke(answer_prompt).content.strip()
                answer = clean_string(answer)

                golden_dataset.append(
                    {
                        "volume": volume["volume_title"],
                        "chapter": cap_title,
                        "difficulty": difficulty,
                        "question": question,
                        "ground_truth": answer,
                    }
                )
            except Exception as e:
                logging.error(f"Errore => capitolo {cap_id}: {e}")
    return golden_dataset


def clean_string(text):
    prefixes = [
        r"^domanda:\s*",
        r"^question:\s*",
        r"^q:\s*",
        r"^d:\s*",
        r"^risposta:\s*",
        r"^answer:\s*",
        r"^r:\s*",
        r"^a:\s*",
    ]
    cleaned = text.strip()
    for pattern in prefixes:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip('"').strip("'")
    return cleaned.strip()


def impossible_question_retry(golden_dataset, original_instructions):
    updated_dataset = []
    for q in golden_dataset:
        if (
            q["difficulty"] == "impossibile"
            and q["ground_truth"] != "L'informazione non è disponibile nel testo"
        ):
            logging.info(f"Rielaborazione domanda fallita => {q['question']}")
            content = ""
            for vol in original_instructions:
                if vol["volume_title"] == q["volume"]:
                    vol_id = f"{vol['volume_id']:02d}"
                    vol_title_clean = vol["volume_title"].replace(" ", "_").lower()
                    filename = f"Volume_{vol_id}_{vol_title_clean}.md"
                    filepath = os.path.join(INPUT_DIR, filename)
                    if os.path.exists(filepath):
                        with open(filepath, "r", encoding="utf-8") as f:
                            volume_text = f.read()
                    for cap in vol["chapters"]:
                        if cap["title"] == q["chapter"]:
                            content = get_chapter_content(volume_text, cap["id"])
                            break
            if content:
                try:
                    new_q_text = generate_question(
                        q["chapter"], "", content, "impossibile"
                    )
                    new_a_text = generate_answer(content, new_q_text)
                    q["question"] = new_q_text.strip()
                    q["ground_truth"] = new_a_text.strip()
                except Exception as e:
                    logging.error(f"Errore nel retry: {e}")
        updated_dataset.append(q)
    return updated_dataset


def main():
    if not os.path.exists(INPUT_FILE):
        logging.error("Filepath sbagliato")
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    final_data = create_dataset(data)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f_out:
        json.dump(final_data, f_out, ensure_ascii=False, indent=4)

    # with open("golden_dataset_2.json", "r", encoding="utf-8") as f:
    #     current_dataset = json.load(f)

    # final_data = impossible_question_retry(current_dataset, data)

    # with open("golden_dataset.json", "w", encoding="utf-8") as f_out:
    #     json.dump(final_data, f_out, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    main()
