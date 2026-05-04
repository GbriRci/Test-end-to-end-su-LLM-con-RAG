import google.generativeai as genai
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv(dotenv_path=Path(__file__).with_name(".env"))
genai.configure(api_key=os.getenv("GENAI_API_KEY"))

def main():
    for m in genai.list_models():
        if "generateContent" in m.supported_generation_methods:
            print(f"Modello: {m.name} - Display Name: {m.display_name}")


if __name__ == "__main__":
    main()