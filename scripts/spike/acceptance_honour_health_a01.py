"""Acceptance test - populate one real HONOUR-HEALTH-01 tab with real content.

This is the final acceptance for the fork extension work. Takes the real
blog-article markdown for A01-low-back-pain and pushes it into a tab named
"Blog Article" in the A01 condition doc via update_tab_from_markdown.

After running, the user opens the doc in a browser and visually confirms
the rendering matches the markdown source.

Usage:
    python scripts/spike/acceptance_honour_health_a01.py

Environment:
    GOOGLE_CLIENT_SECRET_PATH - path to OAuth 2.0 Desktop client JSON
    USER_GOOGLE_EMAIL - the authenticated Google account
"""

import asyncio
import os
import pathlib
import sys
import time

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

FORK_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(FORK_ROOT))

from gdocs.docs_tools import update_tab_from_markdown  # noqa: E402


SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]
TOKEN_CACHE = pathlib.Path.home() / ".workspace-mcp" / "spike_token.json"
A01_DOC_ID = "1UyL1dL6GBztnVGpLQ5H0EQ8Cfh_k6mjiRQ56MCsJnb0"
BLOG_ARTICLE_MD = pathlib.Path(
    "/Users/juliandickie/Documents/GitHub/ahpra-writing-research-cc/"
    "clients/HONOUR-HEALTH-01/content/A01-low-back-pain/"
    "honour-health-A01-low-back-pain-blog-article.md"
)


def get_credentials() -> Credentials:
    creds = Credentials.from_authorized_user_file(str(TOKEN_CACHE), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_CACHE.write_text(creds.to_json())
    return creds


def create_tab(service, doc_id: str, title: str) -> str:
    """Create a tab via direct API, return the new tab_id."""
    response = service.documents().batchUpdate(
        documentId=doc_id,
        body={
            "requests": [
                {
                    "addDocumentTab": {
                        "tabProperties": {"title": title, "index": 0},
                    }
                }
            ]
        },
    ).execute()
    return response["replies"][0]["addDocumentTab"]["tabProperties"]["tabId"]


async def main() -> None:
    if not BLOG_ARTICLE_MD.exists():
        sys.exit(f"ERROR - blog article fixture not found at {BLOG_ARTICLE_MD}")

    markdown_text = BLOG_ARTICLE_MD.read_text()
    print(f"Source - {BLOG_ARTICLE_MD.name} ({len(markdown_text)} chars, {markdown_text.count(chr(10))} newlines)")
    print(f"Target doc - https://docs.google.com/document/d/{A01_DOC_ID}/edit")

    creds = get_credentials()
    service = build("docs", "v1", credentials=creds)

    tab_title = f"Acceptance - Blog Article {int(time.time())}"
    print(f"\nStep 1 - Create tab '{tab_title}'")
    tab_id = create_tab(service, A01_DOC_ID, tab_title)
    print(f"  tab_id = {tab_id}")

    print(f"\nStep 2 - Call update_tab_from_markdown")
    # Unwrap the MCP decorator stack
    fn = update_tab_from_markdown
    while hasattr(fn, "fn"):
        fn = fn.fn
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__

    result = await fn(
        service=service,
        user_google_email=os.environ.get("USER_GOOGLE_EMAIL", "unknown"),
        document_id=A01_DOC_ID,
        tab_id=tab_id,
        markdown_text=markdown_text,
        replace_existing=True,
    )
    print(f"  success = {result['success']}")
    print(f"  requests_applied = {result['requests_applied']}")

    print(f"\nStep 3 - Verify by reading back the tab")
    doc = service.documents().get(
        documentId=A01_DOC_ID,
        includeTabsContent=True,
    ).execute()
    for t in doc.get("tabs", []):
        if t.get("tabProperties", {}).get("tabId") == tab_id:
            body = t.get("documentTab", {}).get("body", {})
            content = body.get("content", [])
            chars = sum(
                len(run.get("textRun", {}).get("content", ""))
                for elem in content
                for run in elem.get("paragraph", {}).get("elements", [])
            )
            heading_count = sum(
                1 for elem in content
                if elem.get("paragraph", {}).get("paragraphStyle", {}).get("namedStyleType", "").startswith("HEADING")
            )
            print(f"  Tab body - {len(content)} structural elements, {chars} characters, {heading_count} headings")
            break

    print("\n" + "=" * 70)
    print("ACCEPTANCE TAB READY FOR VISUAL REVIEW")
    print("=" * 70)
    print(f"\nOpen in browser - https://docs.google.com/document/d/{A01_DOC_ID}/edit")
    print(f"Click the tab named - '{tab_title}' in the left sidebar")
    print(f"\nLook for -")
    print("  - Multiple H1 and H2 headings rendering with the doc's heading style")
    print("  - Bold and italic inline formatting in paragraphs")
    print("  - Bulleted lists")
    print("  - Links clickable with their URL preserved")
    print("  - No bare <script> or <div> HTML remnants")
    print("  - No missing content compared to the source markdown")
    print(f"\nSource to compare against - {BLOG_ARTICLE_MD}")


if __name__ == "__main__":
    asyncio.run(main())
