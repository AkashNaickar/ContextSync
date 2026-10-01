
import re

from langchain_core.documents import Document


def process_slack_data(data, channel_id):
    """Converts Slack messages into documents with metadata."""
    documents = []
    for msg in data:
        # Skip messages without text (e.g. join events)
        if "text" not in msg:
            continue
            
        # Create "Meta-Chunk": Prepend Date and Author
        content = f"Date: {msg.get('ts')} | Author: {msg.get('user')} | Channel: {channel_id}\nMessage: {msg.get('text')}"
        meta = {
            "source": "slack",
            "user": msg.get('user'),
            "channel": channel_id,
            "timestamp": msg.get('ts'),
            "url": f"https://slack.com/archives/{channel_id}/p{msg.get('ts').replace('.', '')}" if msg.get('ts') else None
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

def process_confluence_data(pages):
    """Converts Confluence pages into documents with metadata."""
    documents = []
    for page in pages:
        body = page.get('body', '') or ''
        # Strip HTML tags likely (simple approach) or keep as raw text
        clean_body = re.sub('<[^<]+?>', '', body)
        
        content = f"Page: {page.get('title', 'Untitled')} | Last Modified: {page.get('last_modified', 'N/A')}\nContent: {clean_body}"
        meta = {
            "source": "confluence",
            "id": page.get('id'),
            "title": page.get('title'),
            "url": page.get('url'),
            "version": page.get('version')
        }
        documents.append(Document(page_content=content, metadata=meta))
    return documents

def process_notion_data(pages):
    """Converts Notion pages into documents."""
    documents = []
    for page in pages:
        content_text = page.get('content', '') or ''
        content = f"Title: {page.get('title', 'Untitled')}\nURL: {page.get('url', 'N/A')}\nLast Edited: {page.get('last_edited', 'N/A')}\n\nContent:\n{content_text}"
        meta = {
            "source": "notion",
            "page_id": page.get('id'),
            "title": page.get('title'),
            "url": page.get('url'),
            "last_edited": page.get('last_edited')
        }
        documents.append(Document(page_content=content, metadata=meta))
    return documents
