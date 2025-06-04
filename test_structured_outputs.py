#!/usr/bin/env python3
"""Test structured outputs query with OpenRouter"""

import asyncio
import httpx
from markdownify import markdownify
from urllib.parse import urlparse
import re

def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/"

async def query_structured_outputs():
    """Test querying OpenRouter's Structured Outputs documentation"""
    
    llms_txt_url = "https://openrouter.ai/docs/llms.txt"
    query = "structured"
    
    print(f"🔍 Querying: {llms_txt_url}")
    print(f"🎯 Looking for: {query}")
    print("-" * 50)
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # Fetch llms.txt
            response = await client.get(llms_txt_url)
            response.raise_for_status()
            llms_content = response.text
            
            # Extract domain
            llms_domain = extract_domain(llms_txt_url)
            
            # Parse URLs from HTML
            html_urls = re.findall(r'href="([^"]*)"', llms_content)
            text_urls = re.findall(r'https?://[^\s\)\]]+', llms_content)
            
            available_urls = []
            all_found_urls = html_urls + text_urls
            
            for url in all_found_urls:
                url = url.strip().rstrip(')')
                if url.startswith('http') and url not in available_urls:
                    if url.startswith(llms_domain):
                        available_urls.append(url)
            
            print(f"📄 Found {len(available_urls)} documentation URLs")
            
            # Find structured outputs URLs
            matching_urls = []
            for url in available_urls:
                if query.lower() in url.lower():
                    matching_urls.append(url)
            
            print(f"🎯 Found {len(matching_urls)} URLs matching '{query}':")
            for url in matching_urls:
                print(f"   • {url}")
            
            if matching_urls:
                target_url = matching_urls[0]
                print(f"\n📖 Fetching: {target_url}")
                
                doc_response = await client.get(target_url)
                doc_response.raise_for_status()
                content = markdownify(doc_response.text)
                
                print(f"✅ Success! Retrieved {len(content)} characters")
                print("\n" + "="*60)
                print("STRUCTURED OUTPUTS DOCUMENTATION:")
                print("="*60)
                print(content[:2000])
                if len(content) > 2000:
                    print(f"\n... (showing first 2000 of {len(content)} characters)")
                    
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(query_structured_outputs())