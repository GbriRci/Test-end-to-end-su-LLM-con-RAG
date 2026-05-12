import json
import os
import logging
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

logging.basicConfig(level=logging.INFO)

INPUT_FILE = "./json/final_instructions.json"
OUTPUT_DIR = "./generated_md"
SUMMARY_DIR = "./generated_summary"
STATE_FILE_TEMPLATE = "last_summary_vol{vol_id}_cap{cap_id}.txt"
PROJECT_NAME = "Progetto AETERNA"

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

if not os.path.exists(SUMMARY_DIR):
    os.makedirs(SUMMARY_DIR)

GLOBAL_BLUEPRINT = """AETERNA è un framework di micro-reti energetiche decentralizzate basato su tre livelli: 
        Edge (H-Node domestici), Fog (quartiere) e Cloud (analisi macro). Utilizza blockchain per il trading P2P 
        e AI per il bilanciamento predittivo. L'obiettivo è l'autarchia energetica urbana."""

SYSTEM_PROMPT_CONTENT = f"""Sei un Senior Technical Architect del {PROJECT_NAME}.
        {GLOBAL_BLUEPRINT}
        Il tuo stile è accademico, rigoroso e molto dettagliato. Non essere mai sintetico. AETERNA è un progetto di finzione tecnologica/speculativa. 
        Se incontri termini come 'Kyoto 2.0' o 'Bit-Energy', trattali come standard interni del progetto definiti nelle descrizioni, 
        non come riferimenti storici reali."""

PROMPT_CHAPTER = """Genera il contenuto MD del capitolo corrente:
        Stai scrivendo la documentazione tecnica del {project_name}.
        CAPITOLO CORRENTE: {title}
        DESCRIZIONE: {description}

        CONTESTO PRECEDENTE (Riassunto denso delle decisioni passate):
        {prev_summary}

        REGOLE DI SCRITTURA:
        1. Formato: Markdown avanzato. Per i diagrammi Mermaid: usa ESCLUSIVAMENTE la sintassi 'graph TD' o 'sequenceDiagram', evita caratteri speciali nei nomi dei nodi e racchiudi i testi tra virgolette (es. A[\"Testo\"]).
        2. Struttura obbligatoria (espandi ogni punto):
        - Introduzione Teorica (circa 15% del testo).
        - Specifiche Tecniche e Protocolli (circa 50% del testo - il cuore del documento).
        - Diagramma e Tabelle (circa 20% del testo).
        - Impatto (circa 15% del testo).
        3. Lunghezza: Fornisci una spiegazione esaustiva, punta alla massima densità informativa.
        4. NON ripetere le spiegazioni teoriche già presenti nel CONTESTO PRECEDENTE. Dai per assodate le decisioni passate e concentrati esclusivamente sulle nuove specifiche del capitolo corrente
        {specific_instructions}"""

PROMPT_SUMMARY = """Analizza questo testo e crea un Riassunto Denso (max 300 parole).
        Estrai solo decisioni architetturali, variabili introdotte e dipendenze tecniche utili per i prossimi capitoli.
        TESTO: {content}"""


def get_model(temperature=0.3):
    return ChatOpenAI(
        model="gpt-4.1",
        api_key="any",
        openai_api_base="http://100.120.12.105:14141/v1",
        temperature=temperature,
        max_retries=5,
        timeout=300,
    )


def generate_content(title, description, prev_summary, specific_instructions):
    model = get_model(temperature=0.4)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT_CONTENT),
        HumanMessage(
            content=PROMPT_CHAPTER.format(
                project_name=PROJECT_NAME,
                title=title,
                description=description,
                prev_summary=(
                    prev_summary
                    if prev_summary
                    else "Inizio documentazione: definire le fondamenta."
                ),
                specific_instructions=specific_instructions,
            )
        ),
    ]
    response = model.invoke(messages)
    return clean_llm_output(response.content)


def clean_llm_output(text: str) -> str:
    text = text.strip()
    if text.startswith("```markdown"):
        text = text[11:].strip()
    elif text.startswith("```"):
        text = text[3:].strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    return text


def generate_dense_summary(content):
    model = get_model(temperature=0)
    prompt = PROMPT_SUMMARY.format(content=content)
    response = model.invoke([HumanMessage(content=prompt)])
    return clean_llm_output(response.content)


def generazione_md(data):
    dense_summary = ""
    # scorro tra i volumi
    for vol in data:
        vol_id = vol["volume_id"]
        vol_title = vol["volume_title"].replace(" ", "_").lower()
        filename = f"Volume_{vol_id:02d}_{vol_title}.md"
        filepath = os.path.join(OUTPUT_DIR, filename)
        logging.info(f"--- Volume {vol_id}: {vol['volume_title']} ---")

        # scorro tra i capitoli
        for cap in vol["chapters"]:
            cap_id = cap["id"]
            summary_path = os.path.join(SUMMARY_DIR, f"summary_{vol_id}_{cap_id}.txt")
            if os.path.exists(summary_path):
                with open(summary_path, "r", encoding="utf-8") as f_s:
                    dense_summary = f_s.read()
                continue
            logging.info(f"Volume {vol_id} - Capitolo {cap_id}")

            # generazione
            try:
                chapter_content = generate_content(
                    title=cap["title"],
                    description=cap["description"],
                    prev_summary=dense_summary,
                    specific_instructions=cap.get("specific_instructions", ""),
                )
                with open(filepath, "a", encoding="utf-8") as f_md:
                    f_md.write(f"\n\n# Capitolo {cap_id}: {cap['title']}\n")
                    f_md.write(chapter_content)
                    f_md.write("\n\n---\n")
                dense_summary = generate_dense_summary(chapter_content)
                with open(summary_path, "w", encoding="utf-8") as f_state:
                    f_state.write(dense_summary)
            except Exception as e:
                logging.error(f"Errore => Volume {vol_id}, Capitolo {cap_id}: {e}")
                break


def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    generazione_md(data)


if __name__ == "__main__":
    main()
