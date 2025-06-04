#!/usr/bin/env python3
"""Test script for new MCP tools"""

import asyncio
import httpx
from markdownify import markdownify
from urllib.parse import urlparse

def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/"

async def test_query_external_docs():
    """Test the query_external_docs functionality directly"""
    
    llms_txt_url = "https://openrouter.ai/docs/llms.txt"
    query = "structured"
    
    print(f"Testing query_external_docs with URL: {llms_txt_url}")
    print(f"Query: {query}")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # First, fetch the llms.txt file
            print("\n1. Fetching llms.txt file...")
            response = await client.get(llms_txt_url)
            response.raise_for_status()
            llms_content = response.text
            
            print(f"Downloaded {len(llms_content)} characters")
            print("First 500 chars:", llms_content[:500])
            
            # Extract domain for security
            llms_domain = extract_domain(llms_txt_url)
            print(f"\n2. Domain: {llms_domain}")
            
            # Parse URLs - handle both plain text and HTML formats
            import re
            
            # First try to extract URLs from HTML links
            html_urls = re.findall(r'href="([^"]*)"', llms_content)
            # Also look for URLs in plain text
            text_urls = re.findall(r'https?://[^\s\)\]]+', llms_content)
            
            available_urls = []
            all_found_urls = html_urls + text_urls
            
            for url in all_found_urls:
                # Clean up URLs and filter valid ones
                url = url.strip().rstrip(')')
                if url.startswith('http') and url not in available_urls:
                    available_urls.append(url)
            
            print(f"\n3. Found {len(available_urls)} URLs:")
            for i, url in enumerate(available_urls[:5]):
                print(f"   {i+1}. {url}")
            if len(available_urls) > 5:
                print(f"   ... and {len(available_urls) - 5} more")
            
            # Search for matching URLs
            matching_urls = []
            for url in available_urls:
                if query.lower() in url.lower():
                    matching_urls.append(url)
            
            print(f"\n4. URLs matching '{query}': {len(matching_urls)}")
            for url in matching_urls:
                print(f"   - {url}")
            
            if matching_urls:
                target_url = matching_urls[0]
                print(f"\n5. Fetching content from: {target_url}")
                
                if target_url.startswith(llms_domain):
                    doc_response = await client.get(target_url)
                    doc_response.raise_for_status()
                    content = markdownify(doc_response.text)
                    print(f"Content length: {len(content)} characters")
                    print("First 1000 chars:", content[:1000])
                else:
                    print("Security error: URL not from same domain")
            else:
                print("No matching URLs found")
                
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_query_external_docs())