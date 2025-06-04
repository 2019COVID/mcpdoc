"""MCP Llms-txt server for docs."""

import os
from urllib.parse import urlparse

import httpx
from markdownify import markdownify
from mcp.server.fastmcp import FastMCP
from typing_extensions import NotRequired, TypedDict


class DocSource(TypedDict):
    """A source of documentation for a library or a package."""

    name: NotRequired[str]
    """Name of the documentation source (optional)."""

    llms_txt: str
    """URL to the llms.txt file or documentation source."""

    description: NotRequired[str]
    """Description of the documentation source (optional)."""


def extract_domain(url: str) -> str:
    """Extract domain from URL.

    Args:
        url: Full URL

    Returns:
        Domain with scheme and trailing slash (e.g., https://example.com/)
    """
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/"


def _is_http_or_https(url: str) -> bool:
    """Check if the URL is an HTTP or HTTPS URL."""
    return url.startswith(("http:", "https:"))


def _get_fetch_description(has_local_sources: bool) -> str:
    """Get fetch docs tool description."""
    description = [
        "Fetch and parse documentation from a given URL or local file.",
        "",
        "Use this tool after list_doc_sources to:",
        "1. First fetch the llms.txt file from a documentation source",
        "2. Analyze the URLs listed in the llms.txt file",
        "3. Then fetch specific documentation pages relevant to the user's question",
        "",
    ]

    if has_local_sources:
        description.extend(
            [
                "Args:",
                "    url: The URL or file path to fetch documentation from. Can be:",
                "        - URL from an allowed domain",
                "        - A local file path (absolute or relative)",
                "        - A file:// URL (e.g., file:///path/to/llms.txt)",
            ]
        )
    else:
        description.extend(
            [
                "Args:",
                "    url: The URL to fetch documentation from.",
            ]
        )

    description.extend(
        [
            "",
            "Returns:",
            "    The fetched documentation content converted to markdown, or an error message",  # noqa: E501
            "    if the request fails or the URL is not from an allowed domain.",
        ]
    )

    return "\n".join(description)


def _normalize_path(path: str) -> str:
    """Accept paths in file:/// or relative format and map to absolute paths."""
    return (
        os.path.abspath(path[7:])
        if path.startswith("file://")
        else os.path.abspath(path)
    )


def create_server(
    doc_sources: list[DocSource],
    *,
    follow_redirects: bool = False,
    timeout: float = 10,
    settings: dict | None = None,
    allowed_domains: list[str] | None = None,
) -> FastMCP:
    """Create the server and generate documentation retrieval tools.

    Args:
        doc_sources: List of documentation sources to make available
        follow_redirects: Whether to follow HTTP redirects when fetching docs
        timeout: HTTP request timeout in seconds
        settings: Additional settings to pass to FastMCP
        allowed_domains: Additional domains to allow fetching from.
            Use ['*'] to allow all domains
            The domain hosting the llms.txt file is always appended to the list
            of allowed domains.

    Returns:
        A FastMCP server instance configured with documentation tools
    """
    settings = settings or {}
    server = FastMCP(
        name="llms-txt",
        instructions=(
            "Use the list doc sources tool to see available documentation "
            "sources. Once you have a source, use fetch docs to get the "
            "documentation"
        ),
        **settings,
    )
    httpx_client = httpx.AsyncClient(follow_redirects=follow_redirects, timeout=timeout)

    local_sources = []
    remote_sources = []

    for entry in doc_sources:
        url = entry["llms_txt"]
        if _is_http_or_https(url):
            remote_sources.append(entry)
        else:
            local_sources.append(entry)

    # Let's verify that all local sources exist
    for entry in local_sources:
        path = entry["llms_txt"]
        abs_path = _normalize_path(path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"Local file not found: {abs_path}")

    # Parse the domain names in the llms.txt URLs and identify local file paths
    domains = set(extract_domain(entry["llms_txt"]) for entry in remote_sources)

    # Add additional allowed domains if specified, or set to '*' if we have local files
    if allowed_domains:
        if "*" in allowed_domains:
            domains = {"*"}  # Special marker for allowing all domains
        else:
            domains.update(allowed_domains)

    allowed_local_files = set(
        _normalize_path(entry["llms_txt"]) for entry in local_sources
    )

    @server.tool()
    def list_doc_sources() -> str:
        """List all available documentation sources.

        This is the first tool you should call in the documentation workflow.
        It provides URLs to llms.txt files or local file paths that the user has made available.

        Returns:
            A string containing a formatted list of documentation sources with their URLs or file paths
        """
        content = ""
        for entry_ in doc_sources:
            url_or_path = entry_["llms_txt"]

            if _is_http_or_https(url_or_path):
                name = entry_.get("name", extract_domain(url_or_path))
                content += f"{name}\nURL: {url_or_path}\n\n"
            else:
                path = _normalize_path(url_or_path)
                name = entry_.get("name", path)
                content += f"{name}\nPath: {path}\n\n"
        return content

    fetch_docs_description = _get_fetch_description(
        has_local_sources=bool(local_sources)
    )

    @server.tool(description=fetch_docs_description)
    async def fetch_docs(url: str) -> str:
        nonlocal domains
        # Handle local file paths (either as file:// URLs or direct filesystem paths)
        if not _is_http_or_https(url):
            abs_path = _normalize_path(url)
            if abs_path not in allowed_local_files:
                raise ValueError(
                    f"Local file not allowed: {abs_path}. Allowed files: {allowed_local_files}"
                )
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    content = f.read()
                return markdownify(content)
            except Exception as e:
                return f"Error reading local file: {str(e)}"
        else:
            # Otherwise treat as URL
            if "*" not in domains and not any(
                url.startswith(domain) for domain in domains
            ):
                return (
                    "Error: URL not allowed. Must start with one of the following domains: "
                    + ", ".join(domains)
                )

            try:
                response = await httpx_client.get(url, timeout=timeout)
                response.raise_for_status()
                return markdownify(response.text)
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                return f"Encountered an HTTP error: {str(e)}"

    @server.tool()
    async def query_external_docs_smart(llms_txt_url: str, query: str) -> str:
        """Smart query documentation from an external llms.txt file (server-side matching).
        
        This tool automatically finds and fetches the most relevant documentation based on your query.
        The server performs simple string matching on URLs (NOT semantic search).
        
        Use this when you want a quick, one-step solution and the query matches URL patterns.
        
        Args:
            llms_txt_url: URL to the llms.txt or llms-full.txt file
            query: Search query or specific URL path. Uses simple string matching on URLs,
                   e.g., "structured" matches "structured-outputs", but "JSON schema" won't.
        
        Returns:
            Documentation content that matches the query or an error message
        
        Note: This uses simple string matching, not semantic search. For complex queries,
              consider using list_external_docs + fetch_docs for better control.
        """
        try:
            # First, fetch the llms.txt file to get available URLs
            response = await httpx_client.get(llms_txt_url, timeout=timeout)
            response.raise_for_status()
            llms_content = response.text
            
            # Extract domain from the llms.txt URL for security
            llms_domain = extract_domain(llms_txt_url)
            
            # Parse the llms.txt content to find relevant URLs
            # Handle both plain text and HTML formats
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
                    # Only include URLs from the same domain for security
                    if url.startswith(llms_domain):
                        available_urls.append(url)
            
            if not available_urls:
                return f"No URLs found in llms.txt file: {llms_txt_url}"
            
            # If query looks like a URL path, try to find matching URLs
            if query.startswith('/') or query.startswith('http'):
                matching_urls = []
                for url in available_urls:
                    if query in url:
                        matching_urls.append(url)
                
                if not matching_urls:
                    return f"No URLs found matching query '{query}'. Available URLs:\n" + '\n'.join(available_urls[:10]) + ('...' if len(available_urls) > 10 else '')
                
                # Fetch the first matching URL
                target_url = matching_urls[0]
            else:
                # For text queries, return the llms.txt content and let user choose
                return f"Available documentation URLs from {llms_txt_url}:\n\n" + '\n'.join(available_urls) + "\n\nPlease use this tool again with a specific URL path from the list above."
            
            # Check if target URL is from the same domain as llms.txt for basic security
            if not target_url.startswith(llms_domain):
                return f"Security error: Target URL {target_url} is not from the same domain as llms.txt file {llms_domain}"
            
            # Fetch the target documentation
            doc_response = await httpx_client.get(target_url, timeout=timeout)
            doc_response.raise_for_status()
            
            return f"Documentation from {target_url}:\n\n" + markdownify(doc_response.text)
            
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            return f"Error fetching documentation: {str(e)}"
        except Exception as e:
            return f"Unexpected error: {str(e)}"

    @server.tool()
    async def list_external_docs(llms_txt_url: str) -> str:
        """List all available documentation URLs from an external llms.txt file (agent choice).
        
        This tool fetches an external llms.txt file and returns all available documentation URLs.
        The agent can then choose which specific URL to fetch using the fetch_docs tool.
        
        Use this when you want full control over document selection, especially for:
        - Complex queries that need semantic understanding
        - When you want to see all available options first
        - When simple string matching isn't sufficient
        
        Args:
            llms_txt_url: URL to the llms.txt or llms-full.txt file
        
        Returns:
            A formatted list of all available documentation URLs with descriptions
            
        Workflow: Use this tool first, then call fetch_docs with your chosen URL.
        """
        try:
            # Fetch the llms.txt file
            response = await httpx_client.get(llms_txt_url, timeout=timeout)
            response.raise_for_status()
            llms_content = response.text
            
            # Extract domain for security info
            llms_domain = extract_domain(llms_txt_url)
            
            # Parse URLs from both HTML and text formats
            import re
            html_urls = re.findall(r'href="([^"]*)"', llms_content)
            text_urls = re.findall(r'https?://[^\s\)\]]+', llms_content)
            
            available_urls = []
            all_found_urls = html_urls + text_urls
            
            for url in all_found_urls:
                url = url.strip().rstrip(')')
                if url.startswith('http') and url not in available_urls:
                    if url.startswith(llms_domain):
                        available_urls.append(url)
            
            if not available_urls:
                return f"No documentation URLs found in: {llms_txt_url}"
            
            # Format the response
            result = f"Available documentation from {llms_txt_url}:\n"
            result += f"Domain: {llms_domain}\n"
            result += f"Found {len(available_urls)} documentation URLs:\n\n"
            
            for i, url in enumerate(available_urls, 1):
                # Extract a readable name from the URL
                url_path = url.replace(llms_domain, '').strip('/')
                result += f"{i:2d}. {url_path}\n    URL: {url}\n\n"
            
            result += "Use fetch_docs tool with any of the above URLs to get the content."
            return result
            
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            return f"Error fetching llms.txt file: {str(e)}"
        except Exception as e:
            return f"Unexpected error: {str(e)}"

    @server.tool()
    async def add_doc_source(name: str, llms_txt_url: str, description: str = "") -> str:
        """Dynamically add a new documentation source to the server.
        
        Args:
            name: Name for the documentation source
            llms_txt_url: URL to the llms.txt file
            description: Optional description of the documentation source
        
        Returns:
            Success message or error
        """
        nonlocal doc_sources, domains
        
        try:
            # Validate the URL by trying to fetch it
            response = await httpx_client.get(llms_txt_url, timeout=timeout)
            response.raise_for_status()
            
            # Create new doc source
            new_source: DocSource = {
                "name": name,
                "llms_txt": llms_txt_url,
                "description": description
            }
            
            # Add to doc_sources list
            doc_sources.append(new_source)
            
            # Add domain to allowed domains if it's an HTTP URL
            if _is_http_or_https(llms_txt_url):
                new_domain = extract_domain(llms_txt_url)
                if "*" not in domains:
                    domains.add(new_domain)
            
            return f"Successfully added documentation source '{name}' with URL: {llms_txt_url}"
            
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            return f"Error validating URL {llms_txt_url}: {str(e)}"
        except Exception as e:
            return f"Error adding documentation source: {str(e)}"

    @server.tool()
    def remove_doc_source(name: str) -> str:
        """Remove a documentation source from the server.
        
        Args:
            name: Name of the documentation source to remove
        
        Returns:
            Success message or error
        """
        nonlocal doc_sources
        
        # Find and remove the source
        for i, source in enumerate(doc_sources):
            if source.get("name") == name:
                removed_source = doc_sources.pop(i)
                return f"Successfully removed documentation source '{name}' (URL: {removed_source['llms_txt']})"
        
        available_names = [source.get("name", "unnamed") for source in doc_sources]
        return f"Documentation source '{name}' not found. Available sources: {', '.join(available_names)}"

    return server
