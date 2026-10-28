from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
import os
import aiohttp
import uuid
import tempfile
import asyncio
import json
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Load configuration from .env file
load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Asynchronously initialize connection to centralized MCP server
    asyncio.create_task(mcp_initialize())
    yield

app = FastAPI(
    title="Sovereign On-Premise Agentic AI Workbench",
    description="Confidential Industrial AI Workbench using Open-Weight Multimodal LLMs & Centralized Knowledge Graph",
    version="1.1.0",
    lifespan=lifespan
)

# Allow CORS for front-end
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Centralized Atomic MCP server configuration
MCP_URL = os.getenv("MCP_URL", "http://localhost:8080/mcp")
AUTH_HEADER = os.getenv("MCP_AUTH_HEADER", "Bearer at_aoUQcp-j1DfR8cbEDhY7pEEuBgSqn7e0Xf5qkWFE1lo")

# Academic search & LLM configurations
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "70df7ca148311e422f45db74d365ff8bfcde7463435305070f6787156f4745cf")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5-7b-instruct-1m")
LLM_API_KEY = os.getenv("LLM_API_KEY", "1234")

async def search_scholar(keyword: str):
    params = {
        "engine": "google_scholar",
        "q": keyword,
        "hl": "en",
        "as_sdt": "0,5",
        "api_key": SERPAPI_KEY
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://serpapi.com/search", params=params) as response:
                data = await response.json()
                results = []
                for r in data.get("organic_results", []):
                    results.append({"title": r.get("title"), "link": r.get("link")})
                return results
    except Exception as e:
        print(f"Scholar search error for '{keyword}': {e}")
        return []

# Dummy DB to store user info if we wanted sessions
users = {}

# Global sumy cache
summary_cache = {}

# Global MCP session state
mcp_session_id = None
mcp_message_id = 1

async def mcp_initialize():
    global mcp_session_id
    global mcp_message_id
    
    # Initialize via JSON-RPC POST
    init_msg = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "atomic_agent", "version": "1.0.0"}
        },
        "id": mcp_message_id
    }
    mcp_message_id += 1
    
    headers = {
        "Authorization": AUTH_HEADER,
        "Content-Type": "application/json"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(MCP_URL, json=init_msg, headers=headers, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                mcp_session_id = resp.headers.get("mcp-session-id")
                if not mcp_session_id:
                    print("Warning: No mcp-session-id returned by MCP server.")
                    return
        print(f"MCP Initialized successfully with session {mcp_session_id}")
        
        # Send initialized notification
        notif_msg = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        await mcp_send_request(notif_msg, wait_for_response=False)
    except Exception as e:
        print(f"[Info] MCP server not reachable at {MCP_URL} ({e}). Running in sovereign standalone mode.")

async def mcp_send_request(payload, wait_for_response=True, retry_on_404=True):
    if not mcp_session_id:
        if retry_on_404:
            await mcp_initialize()
            if not mcp_session_id:
                return {"error": "MCP server offline or unavailable"}
        else:
            return {"error": "MCP not connected yet"}
        
    headers = {
        "Authorization": AUTH_HEADER,
        "Content-Type": "application/json",
        "mcp-session-id": mcp_session_id
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(MCP_URL, json=payload, headers=headers) as resp:
                if not wait_for_response:
                    return None
                if resp.status >= 400:
                    body = await resp.text()
                    if resp.status == 404 and "Session not found" in body and retry_on_404:
                        print("MCP session lost. Re-initializing...")
                        await mcp_initialize()
                        # Retry once
                        return await mcp_send_request(payload, wait_for_response, retry_on_404=False)
                    return {"error": f"HTTP {resp.status}", "details": body}
                
                # The rmcp server returns the result directly in the POST body as SSE
                full_text = await resp.text()
                for line in full_text.splitlines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            return json.loads(data_str)
                        except Exception as e:
                            return {"error": "Failed to parse JSON response", "details": str(e), "raw": data_str}
                return {"error": "No SSE data block found in response"}
    except Exception as e:
        return {"error": "MCP request failed", "details": str(e)}



async def call_mcp_tool(tool_name: str, args: dict):
    global mcp_message_id
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": args
        },
        "id": mcp_message_id
    }
    mcp_message_id += 1
    
    return await mcp_send_request(payload)

@app.get("/")
def read_root():
    return {
        "status": "Sovereign Industrial Agent Backend is active",
        "llm_endpoint": LLM_BASE_URL,
        "llm_model": LLM_MODEL,
        "mcp_url": MCP_URL
    }

@app.post("/login")
def login(username: str):
    # Dummy session authentication
    token = str(uuid.uuid4())
    users[token] = username
    return {"token": token, "username": username}

def get_current_user(token: str):
    if token not in users:
        raise HTTPException(status_code=401, detail="Invalid token")
    return users[token]

@app.post("/agent/query")
async def query_agent(query: str, token: str):
    user = get_current_user(token)
    
    try:
        from langchain_openai import ChatOpenAI
        try:
            from langchain.agents import create_agent
        except ImportError:
            from langgraph.prebuilt import create_react_agent as create_agent
        from langchain.tools import tool
    except Exception as e:
        return {
            "user": user,
            "query": query,
            "agent_response": f"Failed to load LangChain components: {str(e)}. Please install dependencies with: pip install -r requirements.txt"
        }

    @tool
    async def semantic_search_tool(search_query: str) -> str:
        """Searches the centralized industrial knowledge graph for relevant chunks of information. Input should be a search query."""
        result = await call_mcp_tool("semantic_search", {"query": search_query})
        return json.dumps(result)

    @tool
    async def get_wiki_tool(tag: str) -> str:
        """Returns a synthesized wiki overview for a tag (a topic name such as "hydrocracking") from the knowledge graph with citations. Input is the tag name."""
        result = await call_mcp_tool("get_wiki", {"tag": tag})
        return json.dumps(result)

    @tool
    def generate_word_report_tool(executive_summary: str, math_output: str) -> str:
        """Combines the LLM executive summary and the verified math output into a styled Word document."""
        try:
            import docx
            from docx.shared import Pt
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            
            doc = docx.Document()
            
            # Add styled title
            title = doc.add_heading('Sovereign Industrial Agent Report', 0)
            title.alignment = WD_ALIGN_PARAGRAPH.CENTER
            
            # Add Executive Summary
            doc.add_heading('Executive Summary', level=1)
            summary_para = doc.add_paragraph(executive_summary)
            
            # Add Math Sandbox Output
            doc.add_heading('Verified Calculation & Sandbox Output', level=1)
            math_para = doc.add_paragraph()
            math_run = math_para.add_run(math_output)
            math_run.font.name = 'Courier New' # Sandbox code-like style
            
            filepath = os.path.join(os.getcwd(), 'sandbox_report.docx')
            doc.save(filepath)
            
            return f"Successfully generated Word document saved directly to disk at: {filepath}"
        except Exception as e:
            return f"Failed to generate Word document: {str(e)}. (Ensure python-docx is installed)"

    tools = [semantic_search_tool, get_wiki_tool, generate_word_report_tool]
    
    base_url = os.getenv("LLM_BASE_URL", LLM_BASE_URL)
    model_name = os.getenv("LLM_MODEL", LLM_MODEL)
    api_key = os.getenv("LLM_API_KEY", LLM_API_KEY)
    
    if "OPENAI_API_KEY" not in os.environ:
        os.environ["OPENAI_API_KEY"] = api_key
    
    try:
        llm = ChatOpenAI(
            temperature=0,
            model=model_name,
            base_url=base_url,
            api_key=api_key
        )
        
        agent = create_agent(
            model=llm,
            tools=tools,
            system_prompt="You are an intelligent sovereign industrial knowledge agent. Use the tools provided to look up confidential engineering information if necessary, and then answer the operator precisely."
        )
        
        # Run agent asynchronously
        res = await agent.ainvoke({"messages": [("user", query)]})
        response_text = res["messages"][-1].content
        
        # Build thinking and execution trace
        thinking = []
        for msg in res["messages"][1:-1]: # Skip first human msg and final answer
            if getattr(msg, "tool_calls", None):
                for t in msg.tool_calls:
                    thinking.append(f"🧠 Agent decided to use tool: [{t['name']}] with arguments {t['args']}")
            elif getattr(msg, "name", None): # A ToolMessage
                thinking.append(f"🛠️ Tool [{msg.name}] returned: {str(msg.content)[:200]}...")
            elif msg.content:
                thinking.append(f"💭 Agent thought: {msg.content}")

        thinking_text = "\n".join(thinking)
        
        # Keyword extraction & Scholar search
        scholar_results = {}
        try:
            extraction_prompt = f"Task: Extract 2 to 6 specific, domain-relevant engineering or scientific keywords from the following text to search on Google Scholar. Return ONLY comma-separated keywords, nothing else.\nText: {response_text}"
            keyword_res = await agent.ainvoke({"messages": [("user", extraction_prompt)]})
            extracted_text = keyword_res["messages"][-1].content
            
            # Parse keywords
            words = [w.strip() for w in extracted_text.split(',')]
            keywords = [w for w in words if w][:6]
            
            # Fetch concurrently
            tasks = [search_scholar(kw) for kw in keywords]
            results = await asyncio.gather(*tasks)
            
            for i, kw in enumerate(keywords):
                if results[i]:
                    scholar_results[kw] = results[i][:5]
        except Exception as e:
            print("Scholar search error:", e)

    except Exception as e:
        # Fallback intelligent response when local inference engine is offline or unreachable
        response_text = (
            f"### [Sovereign Air-Gapped Fallback]\n\n"
            f"**Inference Note:** The agent could not reach the local LLM endpoint at `{base_url}` ({str(e)}).\n\n"
            f"**Query Received:** {query}\n\n"
            f"**Operational Notice:**\n"
            f"- To enable live open-weight model reasoning, start your local inference engine (e.g., LM Studio or Ollama with `{model_name}`) on `{base_url}`.\n"
            f"- Alternatively, update `LLM_BASE_URL` and `LLM_MODEL` in your `backend/.env` file.\n"
            f"- Google Scholar research literature matching your query concepts has been retrieved below."
        )
        thinking_text = f"Fallback mechanism activated: Local inference node ({base_url}) unreachable ({str(e)}). Proceeding with domain heuristic search."
        
        # Extract meaningful keywords from user query for Scholar search
        raw_words = [w.strip("?,.:;\"'()[]{}!").capitalize() for w in query.split() if len(w) > 3]
        stopwords = {"What", "Where", "When", "Which", "Who", "How", "Tell", "Explain", "About", "Does", "Have", "With", "From", "This", "That", "There", "Query", "Please"}
        filtered = [w for w in raw_words if w not in stopwords]
        keywords = filtered[:3] if filtered else ["Process Engineering", "Industrial Automation", "Safety Standards"]
        scholar_results = {}
        
        try:
            tasks = [search_scholar(kw) for kw in keywords]
            results = await asyncio.gather(*tasks)
            
            for i, kw in enumerate(keywords):
                if results[i]:
                    scholar_results[kw] = results[i][:5]
        except Exception as fallback_err:
            print("Scholar search error during fallback:", fallback_err)
    
    return {
        "user": user,
        "query": query,
        "agent_response": response_text,
        "agent_thinking": thinking_text,
        "scholar_results": scholar_results
    }

@app.post("/agent/tool")
async def direct_tool_call(tool_name: str, args: dict, token: str):
    # Direct access to the centralized KG through tools.
    user = get_current_user(token)
    result = await call_mcp_tool(tool_name, args)
    return result

@app.post("/ingest/pdf")
async def ingest_pdf(file: UploadFile = File(...), token: str = ""):
    if not token or token not in users:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    try:
        import pypdf
        import io
    except Exception as e:
        return {"error": f"Failed to import pypdf: {str(e)}. Run pip install pypdf"}
        
    try:
        content = await file.read()
        pdf_reader = pypdf.PdfReader(io.BytesIO(content))
        
        text_pages = []
        for i, page in enumerate(pdf_reader.pages):
            page_text = page.extract_text()
            if page_text:
                text_pages.append(f"## Page {i+1}\n{page_text}")
                
        markdown_content = "\n\n".join(text_pages)
        if not markdown_content.strip():
            markdown_content = "(No extractable text found in PDF)"
        
        # Ingest as an atom in the centralized Knowledge Graph via MCP
        tool_args = {
            "title": file.filename,
            "content": markdown_content,
            "tags": ["pdf_ingest", file.filename]
        }
        kg_result = await call_mcp_tool("create_atom", tool_args)
        
        snippet = markdown_content[:200] + "..." if len(markdown_content) > 200 else markdown_content
        return {
            "status": "success",
            "message": "PDF converted to text and ingested into Centralized Knowledge Graph",
            "markdown_snippet": snippet,
            "kg_result": kg_result
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/agent/summarize")
async def summarize_paper(url: str, title: str):
    if url in summary_cache:
        return summary_cache[url]
        
    import requests
    import asyncio
    try:
        import trafilatura
        from sumy.parsers.plaintext import PlaintextParser
        from sumy.nlp.tokenizers import Tokenizer
        from sumy.summarizers.lex_rank import LexRankSummarizer
        import nltk
        try:
            nltk.data.find('tokenizers/punkt_tab')
        except LookupError:
            try:
                nltk.download('punkt', quiet=True)
                nltk.download('punkt_tab', quiet=True)
            except:
                pass
    except Exception as e:
        return {"title": title, "short_summary": [f"Pipeline init failed: {e}"], "full_summary": [], "source_domain": "", "status": "error"}

    from urllib.parse import urlparse
    domain = urlparse(url).netloc.replace('www.', '')
    
    # 1. Fetch content
    try:
        resp = await asyncio.to_thread(
            requests.get, url, 
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, 
            timeout=8
        )
        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code}")
        html = resp.text
    except Exception as e:
        res = {
            "title": title,
            "short_summary": ["Preview unavailable due to source access restrictions."],
            "full_summary": ["Unable to dynamically fetch context. This may be due to an academic paywall, access control, or an expired link."],
            "source_domain": domain,
            "status": "fallback"
        }
        summary_cache[url] = res
        return res
        
    # 2. Extract article text
    extracted_text = trafilatura.extract(html)
    if not extracted_text:
        res = {
            "title": title,
            "short_summary": ["Content preview temporarily unavailable."],
            "full_summary": ["Extraction pipeline could not separate article body from document boilerplate. Open the original link for full access."],
            "source_domain": domain,
            "status": "fallback"
        }
        summary_cache[url] = res
        return res
        
    try:
        # 3. Summarize using LexRank
        parser = PlaintextParser.from_string(extracted_text, Tokenizer("english"))
        summarizer = LexRankSummarizer()
        summary = summarizer(parser.document, 6)
        sentences = [str(s) for s in summary]
        
        short_summary = sentences[:3] if len(sentences) >= 3 else sentences
        full_summary = sentences if len(sentences) > 0 else ["No significant content extracted."]
        
        res = {
            "title": title,
            "short_summary": short_summary,
            "full_summary": full_summary,
            "source_domain": domain,
            "status": "ok"
        }
        summary_cache[url] = res
        return res
    except Exception as e:
        return {
            "title": title,
            "short_summary": ["Summarization pipeline crashed."],
            "full_summary": [f"Error: {str(e)}"],
            "source_domain": domain,
            "status": "error"
        }

@app.post("/dummy_tool")
async def use_dummy_tool(input_val: str, token: str):
    user = get_current_user(token)
    return {"status": "success", "user": user, "message": f"Diagnostic sandbox tool invoked with input: {input_val}"}

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    print(f"Starting Sovereign Agent Backend on http://{host}:{port}")
    uvicorn.run("main:app", host=host, port=port, reload=True)
