# app/services/rag.py

import os
import re

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from app.models import ContextObject


class RAGService:
    def __init__(self):
        self._init_resources()

    def _init_resources(self):
        """Initialize ChromaDB and LLM."""
        # Calculate absolute path to backend root
        current_dir = os.path.dirname(os.path.abspath(__file__)) # app/services
        backend_root = os.path.dirname(os.path.dirname(current_dir)) # backend
        db_path = os.path.join(backend_root, "chroma_db")

        try:
            self.db = Chroma(
                persist_directory=db_path,
                embedding_function=GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
            )
            self.llm = ChatGoogleGenerativeAI(
                model="gemini-3-pro-preview",
                temperature=0.2,
                convert_system_message_to_human=True
            )
            print("RAG Service Initialized.")
        except Exception as e:
            print(f"Failed to initialize RAG Service: {e}")
            self.db = None
            self.llm = None

    def _extract_keywords(self, code_snippet: str) -> str:
        """Extracts potential keywords (function names, variables) from code."""
        # Simple regex to find words that look like identifiers
        identifiers = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', code_snippet)
        # Filter out common keywords could be added here, but for now just unique them
        unique_identifiers = list(set(identifiers))
        return " ".join(unique_identifiers[:10]) # Limit to top 10 to avoid noise

    def retrieve(self, query: str, k: int = 15):
        """Hybrid-ish retrieval: simply uses the vector store for now."""
        # In a real hybrid setup, we might combine BM25 with Vector search.
        # For this MVP, we rely on the semantic power of the embedding model,
        # but we augment the query with extracted code keywords to ensure specificity.
        if not self.db:
            return []
        return self.db.similarity_search(query, k=k)

    async def explain_code(self, code_snippet: str, file_path: str, line_numbers: str) -> str:
        if not self.db or not self.llm:
            return "### Error\nContext Engine is not initialized. Please check server logs."

        # 1. Augment Query
        keywords = self._extract_keywords(code_snippet)
        search_query = f"{code_snippet}\nKeywords: {keywords}"
        
        # 2. Retrieve Context
        print(f"Retrieving context for: {search_query[:50]}...")
        docs = self.retrieve(search_query)
        
        context_str = "\n\n".join([
            f"--- SOURCE: {doc.metadata.get('source', 'unknown')} ---\n"
            f"{doc.page_content}" 
            for doc in docs
        ])

        # 3. Construct Prompt
        system_prompt = """You are ContextSync, an AI assistant that bridges the gap between Code and Context (Slack/Jira).

        ### 🧠 Reasoning Loop
        Before answering, analyze the provided CONTEXT against the CODE SNIPPET.
        1.  **Analyze Intent**: What is the code trying to do?
        2.  **Verify Match**: Does the Slack thread or Jira ticket explicitly mention this feature, variable, or bug?
        3.  **Filter Noise**: Ignore context that is about a different part of the system, even if keywords match.

        ### 📝 Output Format (Markdown)
        
        ## ⚡ Context Analysis
        * **Relevance**: [High/Medium/Low] - [One sentence explanation]
        
        ## 💡 Intent & Backstory
        [Explain *why* this code exists based on the filtered context]

        ### 🔍 Decision Trail
        - **[Source: Date/Author]**: [Key insight directly related to this code]
        
        ### 🔗 References
        - [Link/ID] - [Title]
        
        If NO relevant context is found, state: "No direct Slack/Jira context found for this logic." and provide a technical explanation only.
        """
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", "{user_input}")
        ])

        user_input_str = f"Context:\n{context_str}\n\nCode ({file_path}:{line_numbers}):\n```python\n{code_snippet}\n```"

        # 4. Generate
        chain = prompt | self.llm | StrOutputParser()
        response = await chain.ainvoke({
            "user_input": user_input_str
        })
        return response

    async def _summarize_doc(self, content: str) -> str:
        """Summarizes a single document using the LLM."""
        # prompt_text = f"Summarize this context in one concise sentence for a developer:\n\n{content}"
        # summary = await self.llm.ainvoke(prompt_text)
        # return f"**Summary**: {summary.content}\n\n**Raw Source**:\n{content}"
        return f"**Snippet**: {content[:300]}...\n\n**Raw Source**:\n{content}"

    async def get_context_objects(self, code_snippet: str) -> list[ContextObject]:
        """Retrieves structured context objects with LLM summaries."""
        keywords = self._extract_keywords(code_snippet)
        search_query = f"{code_snippet}\nKeywords: {keywords}"
        docs = self.retrieve(search_query)
        
        import asyncio
        
        # Summarize in parallel
        summary_tasks = [self._summarize_doc(doc.page_content) for doc in docs]
        summaries = await asyncio.gather(*summary_tasks)
        
        objects = []
        for doc, summary in zip(docs, summaries):
            # Map Chroma metadata to ContextObject
            source = doc.metadata.get("source", "unknown")
            title_or_user = doc.metadata.get("user") or doc.metadata.get("title") or doc.metadata.get("id") or "Unknown"
            
            obj = ContextObject(
                source=source,
                title_or_user=title_or_user,
                url=doc.metadata.get("url"), 
                content_summary=summary,
                relevance_score=0.0, # Placeholder, would need vector score
                related_code_files=[]
            )
            objects.append(obj)
        return objects

    async def chat_with_gemini(self, message: str, history: list[dict] | None = None, context: str | None = None) -> str:
        """Chats with Gemini, optionally using provided context."""
        if not self.llm:
            return "Context Engine is not initialized."

        history = history or []

        # Construct Prompt
        system_prompt = """You are ContextSync, an intelligent coding assistant integrated into VS Code.
        You have access to context from Slack, Jira, Confluence, and Notion.
        
        Your goal is to help the developer understand the codebase, debug issues, and navigate the project.
        
        If 'Current Context' is provided below, use it to answer the user's question if relevant.
        If the user asks a general coding question, answer it directly.
        Be concise, helpful, and developer-focused.
        """
        
        messages = [("system", system_prompt)]
        
        # Add history
        for msg in history:
            role = "user" if msg.get("role") == "user" else "assistant"
            content = msg.get("content", "")
            # Escape curly braces for LangChain PromptTemplate
            content = content.replace("{", "{{").replace("}", "}}")
            messages.append((role, content))
            
        # Add current context if available
        # Fix: We want to treat the user's message as a VARIABLE, not part of the template structure.
        # This prevents curly braces in code from breaking the PromptTemplate.

        user_content_str = message
        
        if context:
            user_content_str = f"Current Context:\n{context}\n\nUser Question:\n{message}"
            
        messages.append(("user", "{user_input}"))
        
        prompt = ChatPromptTemplate.from_messages(messages)
        
        chain = prompt | self.llm | StrOutputParser()
        
        response = await chain.ainvoke({
            "user_input": user_content_str
        })
        return response

    def add_documents(self, documents: list[Document]):
        """Adds new documents to the vector store."""
        if not self.db:
            return
        
        # Split text (reuse same splitter logic)
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        splits = text_splitter.split_documents(documents)
        
        if splits:
            import hashlib
            # Generate deterministic IDs based on content hash to prevent duplicates
            full_ids = [hashlib.md5(doc.page_content.encode()).hexdigest() for doc in splits]
            
            # Deduplicate within this batch
            unique_ids = []
            unique_splits = []
            seen_ids = set()
            for i, doc_id in enumerate(full_ids):
                if doc_id not in seen_ids:
                    unique_ids.append(doc_id)
                    unique_splits.append(splits[i])
                    seen_ids.add(doc_id)
            
            print(f"Adding/Updating {len(unique_splits)} unique chunks in Vector Store...")
            try:
                self.db.add_documents(unique_splits, ids=unique_ids)
            except Exception as e:
                if "Duplicate" in str(e) or "already exists" in str(e).lower():
                    print("Some documents already exist. Updating by deletion/insertion...")
                    try:
                        self.db.delete(ids=unique_ids)
                        self.db.add_documents(unique_splits, ids=unique_ids)
                    except Exception as delete_error:
                        print(f"Error during upsert (delete+add): {delete_error}")
                else:
                    print(f"Error adding documents: {e}")

    async def get_context_stats_batch(self, snippets: list[str]) -> list[dict]:
        """Retrieves stats for a list of code snippets."""
        if not self.db:
            return [{"slack_count": 0, "jira_count": 0, "open_jira_count": 0} for _ in snippets]

        stats_results = []
        for snippet in snippets:
            # We use a smaller k for stats to be faster/more focused
            keywords = self._extract_keywords(snippet)
            search_query = f"{snippet}\nKeywords: {keywords}"
            docs = self.retrieve(search_query, k=10)
            
            slack_count = 0
            jira_count = 0
            open_jira_count = 0
            
            for doc in docs:
                source = doc.metadata.get("source")
                if source == "slack":
                    slack_count += 1
                elif source == "jira":
                    jira_count += 1
                    status = doc.metadata.get("status", "").lower()
                    # Count as open if status is valid and NOT done/closed
                    if status and status not in ["done", "closed", "resolved"]:
                        open_jira_count += 1
            
            stats_results.append({
                "slack_count": slack_count,
                "jira_count": jira_count,
                "open_jira_count": open_jira_count
            })
            
        return stats_results

