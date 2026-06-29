import asyncio
import json
from openai import OpenAI
from mcp import ClientSession, StdioServerParameters, stdio_client

SYSTEM_PROMPT = """Sei un assistente esperto del framework AETERNA. Usa il tool query_rag in modo iterativo se 
        la domanda richiede più passaggi, verifiche incrociate o dettagli approfonditi. 
        Riformula le query in modo atomico e mirato per trovare i chunk corretti."""
MAX_PASSAGGI = 5
SERVER_PARAMS = StdioServerParameters(
    command="uv",
    args=["run", "--project", "./mcp-server", "main.py"]
)


def get_model():
    return OpenAI(
        base_url="http://100.120.12.105:14141/v1",
        api_key="any"
    )


async def agent_rag(query: str):
    contesti_accumulati = []
    # Avvia il server MCP
    async with stdio_client(SERVER_PARAMS) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # Handshake
            await session.initialize()
            # Lista tool
            mcp_tools = await session.list_tools()
            openai_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema
                    }
                }
                for tool in mcp_tools.tools
            ]
            print(f"\nTool disponibili: {[tool['function']['name'] for tool in openai_tools]}\n")
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": query}
            ]
            client = get_model()
            for passaggio in range(MAX_PASSAGGI):
                # Invia lo stato attuale della conversazione al modello
                response = client.chat.completions.create(
                    model="gpt-4.1",
                    messages=messages,
                    tools=openai_tools,
                    tool_choice="auto"
                )
                response_message = response.choices[0].message
                msg_dict = response_message.model_dump(exclude_none=True)
                if "tool_calls" in msg_dict:
                    messages.append({
                        "role": "assistant",
                        "content": response_message.content,
                        "tool_calls": msg_dict["tool_calls"]
                    })
                else:
                    messages.append({"role": "assistant", "content": response_message.content})
                # il modello vuole chiamare un tool?
                if response_message.tool_calls:
                    for tool_call in response_message.tool_calls:
                        if tool_call.function.name == "query_rag":
                            # Estrae gli argomenti generati dinamicamente dall'LLM
                            args = json.loads(tool_call.function.arguments)
                            query_generata = args.get("query_text")
                            k_initial = args.get("k_initial", 20)
                            top_n = args.get("top_n", 5)
                            print(f"Passaggio {passaggio+1} => query: '{query_generata}', k: {k_initial}, top_n: {top_n}")
                            # Esegue la chiamata REALE al tuo server MCP/ChromaDB
                            risultato_mcp = await session.call_tool(
                                "query_rag", 
                                arguments=
                                    {
                                        "query_text": query_generata, 
                                        "k_initial": k_initial, 
                                        "top_n": top_n
                                    }
                                )
                            testo_chunk = risultato_mcp.content[0].text
                            contesti_accumulati.append(testo_chunk)
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": "query_rag",
                                "content": testo_chunk
                            })
                else:
                    print(f"\nRagionamento completato => {passaggio+1} passaggi.\n")
                    return {
                        "query": query,
                        "response": response_message.content,
                        "contexts": contesti_accumulati,
                        "total_hops": passaggio + 1
                    }
            print("ERRORE: limite massimo di passaggi.")
            return {
                "query": query,
                "response": response_message.content,
                "contexts": contesti_accumulati,
                "total_hops": MAX_PASSAGGI
            }
      
            
if __name__ == "__main__":
    test_query = "Quale protocollo viene utilizzato in AETERNA principalmente per il controllo in tempo reale di attuatori come l’illuminazione pubblica e gli switch energetici?"
    risultato = asyncio.run(agent_rag(test_query))
    print("\n--- RISPOSTA FINALE AGENTE ---")
    print(risultato["response"])
    print(f"\nHop Totali: {risultato['total_hops']}")