import os

from atlassian import Confluence
from jira import JIRA
from notion_client import Client
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


class IntegrationService:
    def __init__(self):
        # Slack Initialization
        self.slack_token = os.environ.get("SLACK_BOT_TOKEN")
        self.slack_client = WebClient(token=self.slack_token)
        
        # Jira Initialization
        jira_domain = os.environ.get("JIRA_DOMAIN")
        jira_email = os.environ.get("JIRA_EMAIL")
        jira_token = os.environ.get("JIRA_API_TOKEN")
        
        if jira_domain and jira_email and jira_token:
            # Ensure domain has protocol
            if not jira_domain.startswith("http"):
                jira_server = f"https://{jira_domain}"
            else:
                jira_server = jira_domain
                
            self.jira = JIRA(
                server=jira_server,
                basic_auth=(jira_email, jira_token)
            )
        else:
            self.jira = None
            print("Warning: Jira credentials missing.")

        # Confluence Initialization
        self.confluence_url = os.environ.get("CONFLUENCE_URL")
        self.confluence_username = os.environ.get("CONFLUENCE_USERNAME")
        self.confluence_token = os.environ.get("CONFLUENCE_API_TOKEN")

        if self.confluence_url and self.confluence_username and self.confluence_token:
             self.confluence = Confluence(
                url=self.confluence_url,
                username=self.confluence_username,
                password=self.confluence_token,
                cloud=True
            )
        else:
            self.confluence = None
            print("Warning: Confluence credentials missing.")

        # Notion Initialization
        self.notion_token = os.environ.get("NOTION_API_KEY")
        if self.notion_token:
            self.notion = Client(auth=self.notion_token)
        else:
            self.notion = None
            print("Warning: Notion credentials missing.")

    def get_slack_thread(self, channel_id: str, thread_ts: str):
        """Fetches the last 5 messages from a Slack thread."""
        try:
            result = self.slack_client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                limit=5
            )
            return result.get("messages", [])
        except SlackApiError as e:
            print(f"Slack API Error: {e}")
            return []

    def get_jira_ticket(self, issue_key: str):
        """Fetches issue details from Jira."""
        if not self.jira:
            return None
            
        try:
            issue = self.jira.issue(issue_key)
            return {
                "key": issue.key,
                "summary": issue.fields.summary,
                "description": issue.fields.description,
                "status": issue.fields.status.name,
                "creator": issue.fields.creator.displayName
            }
        except Exception as e:
            print(f"Jira API Error: {e}")
            return None
            
    def list_channels(self, limit=20):
        """Lists public channels to help user find IDs."""
        try:
            result = self.slack_client.conversations_list(limit=limit)
            channels = result.get("channels", [])
            return [{"id": c["id"], "name": c["name"]} for c in channels]
        except SlackApiError as e:
            print(f"Slack API Error: {e}")
            return []

    def fetch_channel_history(self, channel_id: str, limit=50):
        """Fetches recent messages from a channel."""
        try:
            result = self.slack_client.conversations_history(
                channel=channel_id,
                limit=limit
            )
            return result.get("messages", [])
        except SlackApiError as e:
            print(f"Slack API Error: {e}")
            return []

    def search_jira_tickets(self, jql: str, limit=50):
        """Searches for Jira tickets using JQL."""
        if not self.jira:
            return []
        try:
            # fields='summary,description,status,creator,created'
            issues = self.jira.search_issues(jql, maxResults=limit)
            return [{
                "key": i.key,
                "summary": i.fields.summary,
                "description": i.fields.description,
                "status": i.fields.status.name,
                "creator": i.fields.creator.displayName
            } for i in issues]
        except Exception as e:
            print(f"Jira API Error: {e}")
            return []

    def search_confluence_pages(self, cql: str, limit=10):
        """Searches for Confluence pages using CQL."""
        if not self.confluence:
            return []
        try:
            results = self.confluence.cql(cql, limit=limit)
            pages = []
            for result in results.get("results", []):
                # Fetch full content for the page
                page_id = result["content"]["id"]
                page_full = self.confluence.get_page_by_id(page_id, expand="body.storage,version")
                
                # Construct simplified URL
                base = self.confluence_url.rstrip('/')
                # result['url'] is typically /spaces/SPACE/pages/ID/Title
                relative_url = result.get("url", "")
                full_url = f"{base}{relative_url}"
                
                pages.append({
                    "id": page_id,
                    "title": result["content"]["title"],
                    "url": full_url,
                    "body": page_full["body"]["storage"]["value"],
                    "version": page_full["version"]["number"],
                    "last_modified": page_full["version"]["when"]
                })
            return pages
        except Exception as e:
            print(f"Confluence API Error: {e}")
            return []

    def search_notion_pages(self, query: str = "", limit=10):
        """Searches for Notion pages."""
        if not self.notion:
            return []
        try:
            # Search for pages/databases
            response = self.notion.search(query=query, page_size=limit)
            results = response.get("results", [])
            
            pages = []
            for page in results:
                try:
                    # We only want pages, not databases for simplicity, or handle both
                    if page["object"] == "page":
                        # Get title
                        title = "Untitled"
                        props = page.get("properties", {})
                        # Iterate to find the 'title' property type
                        for val in props.values():
                            if val["type"] == "title" and val["title"]:
                                title = val["title"][0]["plain_text"]
                                break
                        
                        # Get content (blocks)
                        # Note: Fetching blocks for each page is expensive, so we limit to top 100 blocks
                        blocks = self.notion.blocks.children.list(block_id=page["id"], page_size=100)
                        
                        content_text = ""
                        for block in blocks.get("results", []):
                            btype = block["type"]
                            text_content = ""
                            
                            # Handle different block types
                            if "rich_text" in block.get(btype, {}):
                                text_list = block[btype]["rich_text"]
                                if text_list:
                                    text_content = "".join([t["plain_text"] for t in text_list])

                            if btype == "paragraph":
                                content_text += text_content + "\n"
                            elif btype in ["heading_1", "heading_2", "heading_3"]:
                                content_text += f"\n# {text_content}\n"
                            elif btype == "bulleted_list_item":
                                content_text += f"- {text_content}\n"
                            elif btype == "numbered_list_item":
                                content_text += f"1. {text_content}\n"
                            elif btype == "code":
                                # Code blocks store text in 'rich_text' inside 'code' object, plus language
                                code_lang = block[btype].get("language", "text")
                                content_text += f"\n```{code_lang}\n{text_content}\n```\n"
                            elif btype == "to_do":
                                checked = "[x]" if block[btype].get("checked") else "[ ]"
                                content_text += f"{checked} {text_content}\n"
                        
                        pages.append({
                            "id": page["id"],
                            "title": title,
                            "url": page["url"],
                            "content": content_text,
                            "last_edited": page["last_edited_time"]
                        })
                except Exception as e:
                    print(f"Error processing Notion page {page.get('id')}: {e}")
                    continue

            return pages

        except Exception as e:
            print(f"Notion API Error: {e}")
            return []
