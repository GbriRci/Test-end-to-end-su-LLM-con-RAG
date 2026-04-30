import streamlit as st
import phoenix as px
from phoenix.otel import register
from openinference.instrumentation.langchain import LangChainInstrumentor
from chatbot import (
    query_rag,
    validate,
    ragas_evaluation,
    get_ragas_database,
    get_ragas_metrics,
)
import pandas as pd

# Phoenix e OpenTelemetry setup
if "phoenix_session" not in st.session_state:
    st.session_state.phoenix_session = px.launch_app()
if "tracer_provider" not in st.session_state:
    st.session_state.tracer_provider = register(project_name="anti-bot")
if "instrumented" not in st.session_state:
    LangChainInstrumentor(tracer_provider=st.session_state.tracer_provider).instrument()
    st.session_state.instrumented = True


# Interfaccia Streamlit
st.title("Anti-Bot")
st.markdown("Fornito di documentazione tecnica sull'Antimateria.")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Chiedi qualcosa sull'Antimateria..."):
    st.session_state.last_question = prompt
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Consultando i manuali..."):
            stream, sources, retrieved = query_rag(prompt)
            full_response_text = st.write_stream(stream)
            st.session_state.response_content = full_response_text
            st.session_state.resources = sources
            st.session_state.retrived = retrieved
    st.session_state.messages.append(
        {"role": "assistant", "content": full_response_text}
    )
    st.rerun()

with st.sidebar:
    st.header("Testing delle risposte")
    if "last_question" in st.session_state:
        st.write(f"Ultima domanda: *{st.session_state.last_question}*")
        expected = st.text_input(
            "Risposta attesa:",
            placeholder="Inserisci la risposta corretta qui...",
        )
        if not expected:
            st.warning("Inserisci la risposta attesa per il test.")
        if st.button("Valida con LLM-as-a-Judge") and expected:
            with st.status("L'LLM sta valutando..."):
                result_LLAMJ = validate(st.session_state.last_question, expected)
            if "true" in result_LLAMJ.lower():
                st.success("Seconto LLM: Test Superato!")
            else:
                st.error("Seconto LLM: Test Fallito!")
        if st.button("Valida con RAGAS") and expected:
            with st.status("L'LLM sta valutando..."):
                database = get_ragas_database(
                    st.session_state.last_question,
                    st.session_state.retrived,
                    expected,
                    st.session_state.response_content,
                )
                result_ragas = ragas_evaluation(database, get_ragas_metrics())
            if result_ragas:
                st.write("RAGAS:")
                # st.dataframe([result_ragas])
                st.bar_chart(pd.DataFrame(result_ragas, index=[0]).T.rename(columns={0: "Score"}))
        st.write(f"Risorse:\n{st.session_state.resources}\n")
    else:
        st.info("Fai una domanda nella chat per poterla validare.")
