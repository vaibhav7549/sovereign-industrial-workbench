<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0f2027,50:203a43,100:2c5364&height=200&section=header&text=Sovereign%20Industrial%20Workbench&fontColor=ffffff&fontSize=38&fontAlignY=38&desc=On-Premise%20Agentic%20AI%20for%20Confidential%20Industrial%20Work&descAlignY=60&descSize=16" alt="Sovereign Industrial Workbench" width="100%"/>

### 🏭 Sovereign On-Premise Agentic AI Workbench
**Using Open-Weight Multimodal LLMs for Confidential Industrial Work**

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black)
![Vite](https://img.shields.io/badge/Vite-6+-646CFF?style=for-the-badge&logo=vite&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-Agent-1C3C3C?style=for-the-badge)
![MCP](https://img.shields.io/badge/Protocol-MCP-000000?style=for-the-badge)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)

[📌 Summary](#-executive-summary) · [🏗 Architecture](#-system-architecture) · [✨ Capabilities](#-core-capabilities) · [🚀 Run](#-how-to-run-the-application) · [🧠 LLM Setup](#-connecting-your-llm) · [📡 API](#-backend-api-endpoints) · [👥 Team](#-team)

</div>

---

## 📌 Executive Summary

Modern industrial facilities (chemical refineries, manufacturing plants, critical energy infrastructure) generate immense volumes of proprietary technical literature, standard operating procedures (SOPs) and equipment specifications. Commercial cloud-hosted AI APIs violate strict air-gap compliance and risk exposing confidential operational intelligence.

The **Sovereign On-Premise Agentic AI Workbench** is an enterprise-grade, air-gapped knowledge platform. It connects open-weight foundation models (**Qwen-2.5**, **DeepSeek**, **Llama-3**) to a centralized **Atomic Knowledge Graph** using the **Model Context Protocol (MCP)**.

> 🔒 **Zero data leaves your perimeter.** Models run on your own hardware, and every answer is traceable.

| | Highlight | What it gives plant engineers |
|:-:|:--|:--|
| 🛡️ | **Sovereign Local Inference** | Models hosted on-premise (LM Studio, Ollama or vLLM) with no data exfiltration risk |
| 🕸️ | **Centralized MCP Knowledge Graph** | Autonomous tool execution: `semantic_search`, `get_wiki`, `create_atom` |
| 📄 | **Technical Document Ingestion** | Industrial PDFs converted into graph atoms on the fly |
| 🎓 | **Academic Grounding** | Domain concepts extracted and correlated with live Google Scholar literature |
| 📊 | **Research Coverage & Synthesis** | Interactive literature-density charts and client-side LexRank summarization |
| 🧾 | **Deterministic Report Generation** | Executive summaries and verified calculations as downloadable Word (`.docx`) files |

---

## 🏗 System Architecture

```mermaid
graph TD
    subgraph Frontend ["🖥️ Frontend (Vite / React 19 SPA :5173)"]
        UI["Sovereign Operator Console"]
        Chart["Interactive SVG Research Chart"]
        LexRank["Paper LexRank Preview Modal"]
    end

    subgraph Backend ["⚡ FastAPI Gateway (:8000)"]
        API["REST API Router"]
        Agent["LangChain / LangGraph Agent Engine"]
        DocParser["PDF Ingestion Pipeline (pypdf)"]
        Scholar["Google Scholar Pipeline (SerpAPI)"]
        Sumy["Summarization Engine (LexRank + Trafilatura)"]
        Docx["Report Generator (python-docx)"]
    end

    subgraph OnPremInference ["🧠 Sovereign Local Inference (:1234 / :11434)"]
        LLM["Open-Weight LLMs (Qwen 2.5 / DeepSeek / Llama 3)"]
    end

    subgraph KnowledgeSystem ["🕸️ Centralized MCP Server (:8080)"]
        MCP["Model Context Protocol Gateway"]
        KG[("Atomic Knowledge Graph")]
    end

    UI -->|JSON / SSE| API
    API --> Agent
    Agent -->|OpenAI-Compatible API| LLM
    Agent -->|MCP Protocol / JSON-RPC| MCP
    MCP --> KG
    DocParser -->|create_atom| MCP
    Scholar -->|Domain Keywords| UI
    Sumy -->|Extractive NLP| LexRank
    Docx -->|Report Generation| API
```

---

## ✨ Core Capabilities

| Capability | Technical Mechanism | Industrial Value |
|:--|:--|:--|
| 🔒 **Air-Gapped Sovereign AI** | Open-weight models deployed locally via LM Studio / Ollama | Zero confidential data leaves the internal perimeter |
| 🤖 **Agentic Tool Calling** | LangChain / LangGraph ReAct orchestration | Autonomous query resolution and tool routing |
| 🕸️ **Knowledge Graph Interface** | Model Context Protocol (MCP) JSON-RPC client | Structured entity search and cross-linking across plant assets |
| 📥 **Automated Collateral Ingestion** | Asynchronous multi-page PDF ingestion (`pypdf`) | Converts SOPs into queryable graph nodes |
| 🎓 **Research Grounding** | Concurrent SerpAPI Scholar querying + LexRank | Validates engineering decisions against peer-reviewed literature |
| 🔍 **Auditable Execution Trace** | Granular chain-of-thought and tool step logging | Transparent verification of reasoning before plant deployment |

---

## 🛠 Technology Stack

| Layer | Technologies |
|:--|:--|
| 🎨 **Frontend** | React 19 · TypeScript · Vite · Vanilla CSS with glassmorphic styling · responsive SVG data visualization |
| ⚙️ **Backend** | Python 3.11+ · FastAPI · Uvicorn · AsyncIO · AIOHTTP |
| 🤖 **Agentic Framework** | LangChain · LangGraph (`create_agent`) · LangChain OpenAI |
| 📚 **Document Processing** | PyPDF · Python-docx · Trafilatura · Sumy · NLTK |
| 📦 **Containerization** | Docker · Docker Compose · Nginx |

---

## 📁 Project Structure

```text
sovereign-industrial-workbench/
├── 📂 backend/            # FastAPI gateway, agent engine, ingestion & summarization
├── 📂 frontend/           # React 19 + Vite operator console
├── 🐳 docker-compose.yml  # One-command full-stack deployment
├── 📄 .gitignore
└── 📘 README.md
```

---

## 🚀 How to Run the Application

You can run the workbench **locally (bare metal)** or with **Docker Compose**.

### Method 1: Local Development

**Prerequisites:** Node.js `v18+` · Python `3.10+` (3.11+ recommended)

```bash
git clone https://github.com/vaibhav7549/sovereign-industrial-workbench.git
cd sovereign-industrial-workbench
```

<table>
<tr>
<td width="50%" valign="top">

#### 🐍 Step 1: Backend (Terminal 1)

```bash
cd backend

# Create & activate a virtual environment
python -m venv venv
.\venv\Scripts\activate        # Windows
# source venv/bin/activate     # macOS / Linux

pip install -r requirements.txt

# Review LLM, MCP and port settings
# in backend/.env

python main.py
```

- API → **http://localhost:8000**
- Swagger docs → **http://localhost:8000/docs**

> **PowerShell policy error?**
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

</td>
<td width="50%" valign="top">

#### ⚛️ Step 2: Frontend (Terminal 2)

```bash
cd frontend

npm install

npm run dev
```

- Open → **http://localhost:5173**

</td>
</tr>
</table>

### Method 2: Docker Compose

With [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed, build and run everything with one command from the project root:

```bash
docker compose up --build
```

| Service | URL |
|:--|:--|
| 🖥️ Frontend UI | http://localhost:5173 |
| ⚡ Backend API | http://localhost:8000 |
| 📖 Swagger Docs | http://localhost:8000/docs |

```bash
docker compose down    # stop all containers
```

---

## 🧠 Connecting Your LLM

The workbench supports **any OpenAI-compatible endpoint**, configured in `backend/.env`.

<details open>
<summary><b>🅰️ Option A: LM Studio (recommended for Windows GUI)</b></summary>

1. Download and open [LM Studio](https://lmstudio.ai/).
2. Download an open-weight model (e.g. `Qwen2.5-7B-Instruct-GGUF` or `DeepSeek-R1-Distill-Qwen-7B`).
3. Open the **Developer / Local Server** tab (`<->` icon).
4. Select your model and click **Start Server** on port `1234`.
5. Set in `backend/.env`:

```env
LLM_BASE_URL=http://localhost:1234/v1
LLM_MODEL=qwen2.5-7b-instruct-1m
LLM_API_KEY=1234
```
</details>

<details>
<summary><b>🅱️ Option B: Ollama (recommended for command line)</b></summary>

1. Install [Ollama](https://ollama.com/) and run:

```bash
ollama run qwen2.5:7b
```

2. Set in `backend/.env`:

```env
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen2.5:7b
LLM_API_KEY=ollama
```
</details>

<details>
<summary><b>🅲 Option C: Cloud provider (OpenAI / Groq / OpenRouter)</b></summary>

If cloud access is permitted, point to any hosted provider:

```env
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-your-openai-key-here
```

> ⚠️ This breaks the air-gap guarantee. Use only where policy allows.
</details>

<details>
<summary><b>🅳 Option D: Built-in sovereign air-gapped fallback</b></summary>

If no local LLM server is active, **the application will not crash.** The backend automatically activates **Sovereign Air-Gapped Fallback mode**: it parses query concepts heuristically, executes Google Scholar retrieval, and shows a clear status notice.
</details>

---

## 💡 Step-by-Step Feature Walkthrough

Once both servers are running, open **http://localhost:5173**:

| Step | Action | What happens |
|:-:|:--|:--|
| **1️⃣** | **Authenticate Operator Session** | Enter an Operator ID (e.g. `operator.v_88`) and click **Authenticate Session**. The backend issues an isolated clearance token. |
| **2️⃣** | **Query the Knowledge Graph & Chat** | Type an industrial query (e.g. *"What are the primary safety protocols for industrial catalytic hydrocrackers?"*) and press Enter. Click **View Execution Trace** to inspect the chain-of-thought and tool calls. |
| **3️⃣** | **Explore Research Grounding** | Use the **Research Coverage Chart** under the answer. In the right panel, click a keyword pill under **RESEARCH PAPERS (SCHOLAR)** to expand paper cards. Hover for live previews and click ✨ for the **LexRank Extractive Summary** modal. |
| **4️⃣** | **Ingest Technical Documents** | Click **Ingest Document** in the sidebar and select a PDF. The backend extracts text with `pypdf`, converts it to clean markdown sections and pushes an atom into the Knowledge Graph via MCP. |
| **5️⃣** | **Diagnostic Sandbox Ping** | Click **Diagnostic Ping** to test isolated backend tool routing and session security. |

---

## ⚙️ Configuration Reference

All settings live in `backend/.env`.

| Variable | Default Value | Description |
|:--|:--|:--|
| `HOST` | `0.0.0.0` | Backend host binding |
| `PORT` | `8000` | Backend port |
| `LLM_BASE_URL` | `http://localhost:1234/v1` | OpenAI-compatible endpoint (LM Studio / Ollama / vLLM) |
| `LLM_MODEL` | `qwen2.5-7b-instruct-1m` | Open-weight model name loaded in the local engine |
| `LLM_API_KEY` | `1234` | API authorization key for the inference endpoint |
| `MCP_URL` | `http://localhost:8080/mcp` | Centralized Atomic MCP server URL |
| `MCP_AUTH_HEADER` | `Bearer <your-token>` | Authorization token for the MCP server |
| `SERPAPI_KEY` | `<your-serpapi-key>` | SerpAPI key for Google Scholar academic search |
| `VITE_API_URL` | `http://localhost:8000` | Frontend → backend gateway URL |

> 🔐 **Never commit real tokens or API keys.** Keep `.env` in `.gitignore` and rotate any key that was ever pushed publicly.

---

## 📡 Backend API Endpoints

| Method | Endpoint | Purpose |
|:-:|:--|:--|
| `GET` | `/` | Health check, active model and runtime endpoint status |
| `POST` | `/login` | Authenticates operator username and issues a session UUID |
| `POST` | `/agent/query` | Agent reasoning loop, tool execution and keyword extraction |
| `POST` | `/agent/summarize` | Scrapes paper URLs and produces a LexRank extractive summary |
| `POST` | `/agent/tool` | Direct invocation of MCP Knowledge Graph tools |
| `POST` | `/ingest/pdf` | Multipart PDF upload, text extraction and MCP atom ingestion |
| `POST` | `/dummy_tool` | Verifies air-gapped sandbox diagnostic routing |

Interactive docs are available at **`/docs`** while the backend is running.

---

## 🔧 Troubleshooting FAQ

<details>
<summary><b>Port 8000 is already in use</b></summary>

Change `PORT=8001` in `backend/.env` and update `VITE_API_URL=http://localhost:8001` in `frontend/src/App.tsx`.
</details>

<details>
<summary><b>PowerShell script execution error</b></summary>

Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in your PowerShell window before activating the virtual environment.
</details>

<details>
<summary><b>Docker cannot reach local LM Studio / Ollama</b></summary>

Use `http://host.docker.internal:1234/v1` (or `:11434`) as defined in `docker-compose.yml` so containers can reach the host machine.
</details>

<details>
<summary><b>NLTK tokenizer warnings</b></summary>

The backend automatically downloads missing `punkt` and `punkt_tab` datasets at startup and inside Docker.
</details>

---

## 👥 Team

<div align="center">

**Department of Information Technology**
**Walchand College of Engineering, Sangli**

| 👤 Name | 🎓 Roll No. |
|:--|:-:|
| **Ahaan Dhar** | 246109020 |
| **Sharvaj Sandeep Fulgaonkar** | 246109030 |
| **Vaibhav Krishna Chaudhari** | 246109002 |

</div>

---

## 📚 Project Citation

> **Sovereign On-Premise Agentic AI Workbench using Open-Weight Multimodal LLMs for Confidential Industrial Work**
> Mini Project · Department of Information Technology · Walchand College of Engineering, Sangli

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:2c5364,50:203a43,100:0f2027&height=100&section=footer" width="100%" alt=""/>

⭐ **If you find this project useful, give it a star!** ⭐

</div>
