import os
import shutil

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")

from app.services.integrations import IntegrationService

# User Configuration
SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID", "")
JIRA_JQL = os.environ.get("JIRA_JQL", "text ~ 'Gateway V2' ORDER BY created DESC")

def load_real_data():
    """Fetches real data from Slack and Jira."""
    service = IntegrationService()
    
    print(f"Fetching Slack messages from {SLACK_CHANNEL_ID}...")
    slack_data = service.fetch_channel_history(SLACK_CHANNEL_ID, limit=50)
    
    print(f"Fetching Jira tickets ({JIRA_JQL})...")
    jira_data = service.search_jira_tickets(JIRA_JQL, limit=50)
    
    return slack_data, jira_data

def process_slack_data(data):
    """Converts Slack messages into documents with metadata."""
    documents = []
    for msg in data:
        # Skip messages without text (e.g. join events)
        if "text" not in msg:
            continue
            
        # Create "Meta-Chunk": Prepend Date and Author
        # Note: Slack API returns 'ts' (timestamp) and 'user' (user ID)
        content = f"Date: {msg.get('ts')} | Author: {msg.get('user')} | Channel: {SLACK_CHANNEL_ID}\nMessage: {msg.get('text')}"
        meta = {
            "source": "slack",
            "user": msg.get('user'),
            "channel": SLACK_CHANNEL_ID,
            "timestamp": msg.get('ts'),
            "url": f"https://slack.com/archives/{SLACK_CHANNEL_ID}/p{msg.get('ts').replace('.', '')}" if msg.get('ts') else None
        }
        documents.append(Document(page_content=content, metadata=meta))
    return documents

def process_jira_data(data):
    """Converts Jira tickets into documents with metadata."""
    documents = []
    for ticket in data:
        # Create "Meta-Chunk"
        content = f"Ticket: {ticket['key']} | Title: {ticket['summary']}\nDescription: {ticket['description'] or 'No description'}"
        meta = {
            "source": "jira",
            "id": ticket['key'],
            "title": ticket['summary'],
            "status": ticket['status'],
            "creator": ticket['creator']
        }
        documents.append(Document(page_content=content, metadata=meta))
    return documents

def ingest():
    """Main ingestion function."""
    # Check for API KEY and channel config
    if not os.getenv("GOOGLE_API_KEY"):
        print("CRITICAL: GOOGLE_API_KEY not found in environment variables. Please set it in a .env file.")
        return
    if not SLACK_CHANNEL_ID:
        print("CRITICAL: SLACK_CHANNEL_ID not set. Please set it in a .env file.")
        return

    print("Loading REAL data from Integrations...")
    slack_data, jira_data = load_real_data()
    
    docs = []
    docs.extend(process_slack_data(slack_data))
    docs.extend(process_jira_data(jira_data))
    print(f"Loaded {len(docs)} documents ({len(slack_data)} Slack, {len(jira_data)} Jira).")

    # Chunking
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    splits = text_splitter.split_documents(docs)
    print(f"Created {len(splits)} text chunks.")

    # Embedding & Storage
    print("Initializing Vector Store (ChromaDB)...")
    try:
        embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
        
        # Reset DB if exists to avoid duplicates in this simple script
        if os.path.exists(DB_PATH):
            shutil.rmtree(DB_PATH)

        Chroma.from_documents(
            documents=splits,
            embedding=embeddings,
            persist_directory=DB_PATH
        )
        print(f"Success! Ingested {len(splits)} chunks into {DB_PATH}")
    except Exception as e:
        print(f"Error during ingestion: {e}")

if __name__ == "__main__":
    ingest()

