from langchain_community.document_loaders import (
    DirectoryLoader,
    PyPDFDirectoryLoader,
    UnstructuredMarkdownLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from torch import chunk


CHROMA_PATH = "./chroma_db_AETERNA/"
DATA_PATH = "../synthetic_data_AETERNA"


def load_documents():
    # document_loader = PyPDFDirectoryLoader(DATA_PATH) # => PDF
    document_loader = DirectoryLoader(
        DATA_PATH, glob="**/*.md", loader_cls=UnstructuredMarkdownLoader  # => MD
    )
    return document_loader.load()


def split_documents(documents: list[Document]):
    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=250,
        chunk_overlap=30,
    )
    return text_splitter.split_documents(documents)


def get_embeddings_function():
    return OllamaEmbeddings(model="nomic-embed-text-v2-moe")


def calculate_chunk_ids(chunks):
    last_page_id = None
    current_chunk_index = 0
    for chunk in chunks:
        source = chunk.metadata.get("source")
        page = chunk.metadata.get("page", 0)
        current_page_id = f"{source}:{page}"
        if current_page_id == last_page_id:
            current_chunk_index += 1
        else:
            current_chunk_index = 0
        chunk_id = f"{current_page_id}:{current_chunk_index}"
        last_page_id = current_page_id
        chunk.metadata["id"] = chunk_id
    return chunks


def create_chroma_db():
    return Chroma(
        persist_directory=CHROMA_PATH,
        embedding_function=get_embeddings_function(),
        collection_metadata={"hnsw:space": "cosine"},
    )


def add_to_chroma(chunks: list[Document]):
    db = create_chroma_db()
    existing_items = db.get(include=[])
    existing_ids = set(existing_items["ids"])
    print(f"Erano già presenti id: {len(existing_ids)}")
    chunks_with_ids = calculate_chunk_ids(chunks)
    new_chunks = []
    for chunk in chunks_with_ids:
        if chunk.metadata["id"] not in existing_ids:
            new_chunks.append(chunk)
    if len(new_chunks):
        print(f"Aggiunta di {len(new_chunks)} nuovi chunk...")
        new_chunks_ids = [chunk.metadata["id"] for chunk in new_chunks]
        db.add_documents(new_chunks, ids=new_chunks_ids)
    else:
        print("Nessun nuovo documento da aggiungere.")
    return db


def main():
    docs = load_documents()
    chunks = split_documents(docs)
    add_to_chroma(chunks)


if __name__ == "__main__":
    main()
