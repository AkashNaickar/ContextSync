import asyncio
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request

from app.models import (
    ChatRequest,
    ChatResponse,
    ContextObject,
    ExplainRequest,
    ExplainResponse,
    StatsObject,
    StatsRequest,
)
from app.services.data_processing import (
    process_confluence_data,
    process_jira_data,
    process_notion_data,
    process_slack_data,
)
from app.services.integrations import IntegrationService
from app.services.rag import RAGService

load_dotenv()

rag_service = None
integration_service = None
# Config from environment (see .env.example)
SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID", "")
JIRA_JQL = "resolution = Unresolved ORDER BY created DESC"
CONFLUENCE_CQL = 'type=page AND title ~ "Payment" ORDER BY lastmodified DESC'
NOTION_QUERY = os.environ.get("NOTION_SEARCH_QUERY", "")

async def sync_data():
    """Fetches and ingests real-time data."""
    try:
        print("Syncing real-time data...")
        if not integration_service or not rag_service:
            print("Services not ready, skipping sync.")
            return {"status": "skipped", "message": "Services not ready"}

        # Fetch Data
        slack_msgs = integration_service.fetch_channel_history(SLACK_CHANNEL_ID, limit=10)
        jira_tickets = integration_service.search_jira_tickets(JIRA_JQL, limit=10)
        confluence_pages = integration_service.search_confluence_pages(CONFLUENCE_CQL, limit=5)
        notion_pages = integration_service.search_notion_pages(NOTION_QUERY, limit=5)
        
        # Process & Ingest
        new_docs = []
        if slack_msgs:
            new_docs.extend(process_slack_data(slack_msgs, SLACK_CHANNEL_ID))
        if jira_tickets:
            new_docs.extend(process_jira_data(jira_tickets))
        if confluence_pages:
            new_docs.extend(process_confluence_data(confluence_pages))
        if notion_pages:
            new_docs.extend(process_notion_data(notion_pages))
        
        if new_docs:
            rag_service.add_documents(new_docs)
            print(f"Synced {len(new_docs)} items.")
            return {"status": "success", "items_synced": len(new_docs)}
        
        return {"status": "success", "items_synced": 0}
        
    except Exception as e:
        print(f"Error in sync: {e}")
        return {"status": "error", "message": str(e)}

async def background_sync():
    """Polls Slack and Jira for new data every 60 seconds."""
    print("Starting background sync loop...")
    while True:
        await sync_data()
        await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global rag_service, integration_service
    rag_service = RAGService()
    integration_service = IntegrationService()
    
    # Start background task
    task = asyncio.create_task(background_sync())
    
    yield
    
    # Clean up
    task.cancel()

app = FastAPI(title="ContextSync Backend", lifespan=lifespan)

@app.get("/")   # GET http request
async def root():  
    return {"message": "ContextSync Context Engine is Running"}

@app.post("/explain", response_model=ExplainResponse)  # POST http request
async def explain_code(request: ExplainRequest):
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG Service not initialized")
        
    markdown_response = await rag_service.explain_code(
        request.code_snippet, 
        request.file_path, 
        request.line_numbers
    )
    
    return ExplainResponse(markdown=markdown_response)

@app.post("/context/retrieve", response_model=list[ContextObject])  # POST http request
async def retrieve_context(request: ExplainRequest):
    """Returns structured context objects for the IDE."""
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG Service not initialized")
    
    return await rag_service.get_context_objects(request.code_snippet)

@app.post("/context/ingest")
async def ingest_webhook(request: Request):
    """Mock webhook receiver for Slack/Jira events."""
    data = await request.json()
    print(f"Received webhook event: {data}")
    # In a real app, this would trigger the ingestion pipeline
    return {"status": "received"}

@app.post("/context/sync")
async def manual_sync():
    """Manually triggers the data sync logic."""
    return await sync_data()

@app.post("/context/stats", response_model=list[StatsObject])
async def context_stats(request: StatsRequest):
    """Returns context stats for a list of code snippets."""
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG Service not initialized")
    
    stats_list = await rag_service.get_context_stats_batch(request.snippets)
    return [StatsObject(**s) for s in stats_list]

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """Chat with Gemini 3 Pro."""
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG Service not initialized")
    
    reply = await rag_service.chat_with_gemini(
        message=request.message,
        history=request.history,
        context=request.context
    )
    
    return ChatResponse(reply=reply)
