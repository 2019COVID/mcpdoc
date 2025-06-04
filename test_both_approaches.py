#!/usr/bin/env python3
"""Test both smart query and agent choice approaches"""

import asyncio
import httpx
from markdownify import markdownify
from urllib.parse import urlparse
import re

def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/"

async def test_both_approaches():
    """Test both query approaches with OpenRouter"""
    
    llms_txt_url = "https://openrouter.ai/docs/llms.txt"
    
    print("🔍 Testing Both MCP Documentation Query Approaches")
    print("=" * 60)
    print(f"Target: {llms_txt_url}")
    print()
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        
        # Approach 1: Smart Query (Server-side matching)
        print("📋 APPROACH 1: Smart Query (Server-side matching)")
        print("-" * 40)
        print("Query: 'structured' → automatic string matching")
        
        try:
            # Simulate query_external_docs_smart
            response = await client.get(llms_txt_url)
            response.raise_for_status()
            llms_content = response.text
            llms_domain = extract_domain(llms_txt_url)
            
            # Parse URLs
            html_urls = re.findall(r'href="([^"]*)"', llms_content)
            text_urls = re.findall(r'https?://[^\s\)\]]+', llms_content)
            
            available_urls = []
            all_found_urls = html_urls + text_urls
            
            for url in all_found_urls:
                url = url.strip().rstrip(')')
                if url.startswith('http') and url not in available_urls:
                    if url.startswith(llms_domain):
                        available_urls.append(url)
            
            # String matching
            query = "structured"
            matching_urls = []
            for url in available_urls:
                if query.lower() in url.lower():
                    matching_urls.append(url)
            
            print(f"✅ Found {len(matching_urls)} matching URLs:")
            for url in matching_urls:
                print(f"   • {url}")
            
            if matching_urls:
                target_url = matching_urls[0]
                doc_response = await client.get(target_url)
                doc_response.raise_for_status()
                content = markdownify(doc_response.text)
                print(f"✅ Retrieved {len(content)} characters")
                print(f"📄 Title: {content.split('\\n')[0][:50]}...")
            
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print()
        print("=" * 60)
        
        # Approach 2: Agent Choice (List then select)
        print("📋 APPROACH 2: Agent Choice (List then select)")  
        print("-" * 40)
        print("Step 1: List all available docs")
        
        try:
            # Simulate list_external_docs
            print(f"📄 Found {len(available_urls)} documentation URLs:")
            
            # Show categorized URLs for agent to choose from
            categories = {}
            for url in available_urls:
                path = url.replace(llms_domain, '').strip('/')
                category = path.split('/')[0] if '/' in path else 'general'
                if category not in categories:
                    categories[category] = []
                categories[category].append((path, url))
            
            for category, urls in categories.items():
                print(f"\\n📁 {category.upper()}:")
                for path, url in urls[:3]:  # Show first 3 in each category
                    print(f"   • {path}")
                if len(urls) > 3:
                    print(f"   ... and {len(urls) - 3} more")
            
            print("\\nStep 2: Agent analyzes and selects based on semantic understanding")
            print("Agent reasoning: 'structured outputs' relates to API response formatting")
            print("Agent chooses: docs/features/structured-outputs.mdx")
            
            # Agent's choice
            target_url = "https://openrouter.ai/docs/features/structured-outputs.mdx"
            print(f"\\n📖 Fetching agent's choice: {target_url}")
            
            doc_response = await client.get(target_url)
            doc_response.raise_for_status()
            content = markdownify(doc_response.text)
            print(f"✅ Retrieved {len(content)} characters")
            print(f"📄 Title: {content.split('\\n')[0][:50]}...")
            
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print()
        print("=" * 60)
        print("📊 COMPARISON:")
        print("Smart Query    → Fast, limited to URL string matching")
        print("Agent Choice   → Flexible, enables semantic reasoning")
        print("Use Smart for  → Simple, direct queries ('auth', 'api')")  
        print("Use Agent for  → Complex queries ('JSON validation', 'type safety')")

if __name__ == "__main__":
    asyncio.run(test_both_approaches())