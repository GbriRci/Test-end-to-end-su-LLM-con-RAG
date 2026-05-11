import json
import logging
from langchain_core.messages import HumanMessage, SystemMessage
from generate_synthetic_md.generate_md import get_model

INPUT_FILE = "./json/final_instructions.json"

AMPLIFY_TEXT_PROMPT = """
        Espandi a un minimo di 300 caratteri la descrizione del capitolo seguendo queste regole:
            1. Dettaglio: Fornisci dettagli tecnici, esempi concreti e spiegazioni approfondite.
            2. Struttura: Organizza la descrizione in sezioni chiare (introduzione, dettagli tecnici, esempi, conclusioni).
            3. Linguaggio: Usa un tono accademico e rigoroso, evita generalizzazioni e sii specifico.
            4. Contesto: Considera il contesto del progetto AETERNA e le decisioni architetturali già prese nei capitoli precedenti (se disponibili).
            5. Minimo 300 caratteri: Assicurati che la descrizione sia sufficientemente dettagliata e non sintetica.
        """
AMPLIFY_CHAPTER_NUMBER_PROMPT = """
                Genera ESCLUSIVAMENTE un JSON valido, senza testo extra, senza markdown e senza commenti.
                Riceverai un volume JSON con alcuni capitoli esistenti.

                Obiettivo:
                - Aggiungere esattamente {missing} nuovi capitoli.
                - Non modificare i capitoli esistenti.
                - Restituire l'intero volume aggiornato con almeno 10 capitoli.

                Schema richiesto:
                {{
                "volume_id": int,
                "volume_title": string,
                "chapters": [
                    {{
                    "id": int,
                    "title": string,
                    "description": string (minimo 300 caratteri),
                    "specific_instructions": string
                    }}
                ]
                }}

                Volume di input:
                {volume_json.replace('{', '{{').replace('}', '}}')}
            """
SYSTEM_PROMPT = """Sei un Senior Technical Architect incaricato della documentazione del Progetto AETERNA. 
        Il tuo stile è accademico, rigoroso e molto dettagliato. Non essere mai sintetico."""


def amplify_json():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    model = get_model()
    amplified_data = []

    # scorro i volumi
    for vol in data:
        logging.info(f"Volume {vol['volume_id']}")
        new_chapters = []

        # scorro i capitoli
        for cap in vol["chapters"]:
            logging.info(f"Capitolo: {cap['id']}")
            if len(cap["description"]) >= 300:
                new_chapters.append(cap)
                continue
            try:
                response = model.invoke(
                    [
                        SystemMessage(content=SYSTEM_PROMPT),
                        HumanMessage(content=AMPLIFY_TEXT_PROMPT),
                        HumanMessage(content=cap["description"]),
                    ]
                )
                new_descrp = response.content
                cap["description"] = new_descrp
                new_chapters.append(cap)
            except Exception as e:
                logging.error(
                    f"Errore => Volume {vol.get('volume_id')}, Capitolo {cap['id']}: {e}"
                )
                new_chapters.append(cap)
        vol["chapters"] = new_chapters
        amplified_data.append(vol)
    with open(INPUT_FILE, "w", encoding="utf-8") as f_out:
        json.dump(amplified_data, f_out, indent=4, ensure_ascii=False)


def amplify_chapter_number():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    model = get_model()
    amplified_data = []

    # scorro i volumi
    for vol in data:
        current_chapters = vol.get("chapters", [])
        missing = max(0, 10 - len(current_chapters))
        if missing > 0:
            logging.info(f"Volume {vol.get('volume_id')}")
            volume_json = json.dumps(vol, ensure_ascii=False)
            prompt = AMPLIFY_CHAPTER_NUMBER_PROMPT.format(
                missing=missing, volume_json=volume_json
            )
            try:
                resp = model.invoke(
                    [
                        SystemMessage(
                            content=SYSTEM_PROMPT,
                        ),
                        HumanMessage(content=prompt),
                    ]
                )
                raw = resp.content.strip()

                if raw.startswith("```"):
                    raw = raw.strip("`")
                    if raw.startswith("json"):
                        raw = raw[4:].strip()
                parsed = json.loads(raw)

                # prendo la risposta solo se è un JSON valido con almeno 10 capitoli, altrimenti mantengo il volume originale
                if isinstance(parsed, dict) and isinstance(
                    parsed.get("chapters"), list
                ):
                    if len(parsed["chapters"]) >= 10:
                        vol = parsed

            except Exception as e:
                logging.error(f"Errore => volume {vol.get('volume_id')}: {e}.")
        amplified_data.append(vol)
    with open(INPUT_FILE, "w", encoding="utf-8") as f_out:
        json.dump(amplified_data, f_out, indent=4, ensure_ascii=False)


if __name__ == "__main__":
    amplify_json()
    # amplify_chapter_number()
