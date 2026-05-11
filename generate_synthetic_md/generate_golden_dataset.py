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

SYSTEM_PROMPT_CONTENT = f"Sei un Senior Technical Architect del {PROJECT_NAME}. {GLOBAL_BLUEPRINT} Stile accademico e rigoroso."

# --- PROMPT OTTIMIZZATI ---
PROMPT_QUESTIONS = """Genera una domanda tecnica sul capitolo:
        TITOLO: {title}
        DIFFICOLTÀ RICHIESTA: {difficulty}
        CONTENUTO: {content}

        REGOLE:
        - Rispetta RIGOROSAMENTE la difficoltà {difficulty}.
        - Se IMPOSSIBILE: la domanda deve riguardare il tema del capitolo ma richiedere dettagli tecnici (date, nomi di chip specifici, coefficienti) NON presenti nel testo.
        - Rispondi solo con la domanda, niente prefazioni."""

PROMPT_ANSWER = """Analizza il testo e rispondi alla domanda.
        TESTO: {content}
        DOMANDA: {question}

        REGOLE:
        - Sii esaustivo e tecnico.
        - Se la domanda è 'IMPOSSIBILE' (non trovi la risposta nel testo), scrivi esattamente: "L'informazione non è disponibile nel testo"."""


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
        for idx, chapter in enumerate(volume["chapters"]):
            cap_id = chapter["id"]
            cap_title = chapter["title"]
            content = get_chapter_content(volume_content, cap_id)
            difficulty = get_difficulty(idx)

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
                answer_prompt = [
                    SystemMessage(content=SYSTEM_PROMPT_CONTENT),
                    HumanMessage(
                        content=PROMPT_ANSWER.format(content=content, question=question)
                    ),
                ]
                answer = model.invoke(answer_prompt).content.strip()

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
                logging.error(
                    f"Errore => capitolo {cap_id}: {e}"
                )
    return golden_dataset


def main():
    if not os.path.exists(INPUT_FILE):
        logging.error("Filepath sbagliato")
        return
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    final_data = create_dataset(data)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f_out:
        json.dump(final_data, f_out, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    main()
