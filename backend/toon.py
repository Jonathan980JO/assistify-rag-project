"""
TOON (Token-Oriented Object Notation) Implementation
Compact format for LLM communication - saves 40-60% tokens vs JSON

Format:
  Simple values:  key: value
  Arrays:         key[length]: item1,item2,item3
  Nested:         parent.child: value (flattened)

Usage:
  to_toon(dict) -> str          # Encode dict to TOON
  from_toon(str) -> dict        # Decode TOON to dict
  format_rag_context_toon(docs) # Format RAG docs for LLM
"""


def to_toon(data: dict, prefix: str = "") -> str:
    """
    Convert Python dictionary to TOON format
    
    Args:
        data: Dictionary to convert
        prefix: Prefix for nested keys (used recursively)
    
    Returns:
        TOON-formatted string
    
    Example:
        >>> to_toon({"name": "test", "tags": ["a", "b"]})
        'name: test\\ntags[2]: a,b'
    """
    if not data:
        return ""
    
    lines = []
    
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        
        if value is None:
            # Skip None values to save tokens
            continue
        elif isinstance(value, dict):
            # Flatten nested dicts
            nested_toon = to_toon(value, prefix=full_key)
            if nested_toon:
                lines.append(nested_toon)
        elif isinstance(value, list):
            # Array format: key[length]: item1,item2,item3
            if len(value) == 0:
                lines.append(f"{full_key}[0]:")
            else:
                # Convert all items to strings and join
                items_str = ','.join(str(item) for item in value)
                lines.append(f"{full_key}[{len(value)}]: {items_str}")
        elif isinstance(value, bool):
            # Boolean as 0/1 to save tokens
            lines.append(f"{full_key}: {1 if value else 0}")
        else:
            # Simple value: key: value
            lines.append(f"{full_key}: {value}")
    
    return '\n'.join(lines)


def from_toon(toon_str: str) -> dict:
    """
    Convert TOON format back to Python dictionary
    
    Args:
        toon_str: TOON-formatted string
    
    Returns:
        Python dictionary
    
    Example:
        >>> from_toon('name: test\\ntags[2]: a,b')
        {'name': 'test', 'tags': ['a', 'b']}
    """
    if not toon_str or not toon_str.strip():
        return {}
    
    result = {}
    lines = toon_str.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or ':' not in line:
            continue
        
        # Split on first colon
        key_part, value_part = line.split(':', 1)
        key_part = key_part.strip()
        value_part = value_part.strip()
        
        # Check if it's an array: key[length]
        if '[' in key_part and ']' in key_part:
            # Extract key and length
            key = key_part[:key_part.index('[')]
            length_str = key_part[key_part.index('[')+1:key_part.index(']')]
            
            try:
                length = int(length_str)
            except ValueError:
                length = 0
            
            # Parse array values
            if length == 0 or not value_part:
                value = []
            else:
                value = [item.strip() for item in value_part.split(',')]
            
            # Handle nested keys (flatten back)
            if '.' in key:
                # For now, just use the full key
                result[key] = value
            else:
                result[key] = value
        else:
            # Simple key-value
            key = key_part
            
            # Try to preserve types (though TOON is primarily string-based)
            if value_part.isdigit():
                value = value_part  # Keep as string for safety
            elif value_part.lower() in ('true', 'false', '1', '0'):
                # Boolean detection
                value = value_part
            else:
                value = value_part
            
            # Handle nested keys
            if '.' in key:
                result[key] = value
            else:
                result[key] = value
    
    return result


def format_rag_context_toon(docs: list) -> str:
    """
    Format RAG documents in TOON format for LLM context
    
    Args:
        docs: List of document dicts with 'page_content' and 'metadata'
    
    Returns:
        TOON-formatted string ready for LLM prompt
    
    Example:
        >>> docs = [{"page_content": "Install guide", "metadata": {"source": "docs.md"}}]
        >>> format_rag_context_toon(docs)
        'doc[0]:\\n  content: Install guide\\n  source: docs.md'
    """
    if not docs:
        return ""
    
    context_parts = []
    
    for i, doc in enumerate(docs):
        doc_lines = [f"doc[{i}]:"]
        
        # Add content (most important)
        if isinstance(doc, dict):
            content = doc.get('page_content', doc.get('content', ''))
            metadata = doc.get('metadata', {})
        else:
            # Handle Document objects from ChromaDB/LangChain
            content = getattr(doc, 'page_content', str(doc))
            metadata = getattr(doc, 'metadata', {})
        
        if content:
            # Truncate very long content to save tokens
            if len(content) > 500:
                content = content[:500] + "..."
            doc_lines.append(f"  content: {content}")
        
        # Add key metadata
        if metadata:
            for key, value in metadata.items():
                if key in ['source', 'type', 'category', 'title']:
                    doc_lines.append(f"  {key}: {value}")
        
        context_parts.append('\n'.join(doc_lines))
    
    return '\n---\n'.join(context_parts)


def build_llm_prompt_with_toon(query: str, docs: list) -> str:
    """
    Build LLM prompt with TOON-formatted RAG context
    
    Args:
        query: User's question
        docs: Retrieved RAG documents
    
    Returns:
        Complete LLM prompt with TOON context
    """
    context = format_rag_context_toon(docs)
    
    prompt = f"""You are Assistify, a helpful AI assistant.

Context (TOON format):
{context}

User Question: {query}

Instructions: Answer the question using the context provided. Be concise and accurate."""
    
    return prompt


def compare_token_efficiency(data: dict) -> dict:
    """
    Compare token usage between JSON and TOON
    
    Args:
        data: Dictionary to compare
    
    Returns:
        Dict with comparison stats
    """
    import json
    
    # JSON representation
    json_str = json.dumps(data)
    json_chars = len(json_str)
    json_tokens_est = len(json_str.split())  # Rough estimate
    
    # TOON representation
    toon_str = to_toon(data)
    toon_chars = len(toon_str)
    toon_tokens_est = len(toon_str.split())  # Rough estimate
    
    # Calculate savings
    char_savings = ((json_chars - toon_chars) / json_chars) * 100 if json_chars > 0 else 0
    token_savings = ((json_tokens_est - toon_tokens_est) / json_tokens_est) * 100 if json_tokens_est > 0 else 0
    
    return {
        "json_chars": json_chars,
        "toon_chars": toon_chars,
        "json_tokens_est": json_tokens_est,
        "toon_tokens_est": toon_tokens_est,
        "char_savings_pct": round(char_savings, 1),
        "token_savings_pct": round(token_savings, 1)
    }


# Convenience exports
__all__ = [
    'to_toon',
    'from_toon',
    'format_rag_context_toon',
    'build_llm_prompt_with_toon',
    'compare_token_efficiency'
]


if __name__ == "__main__":
    # Demo
    print("TOON Format Demo")
    print("="*50)
    
    sample = {
        "title": "Installation Guide",
        "tags": ["install", "setup", "tutorial"],
        "priority": 5,
        "active": True,
        "metadata": {
            "author": "admin",
            "date": "2025-01-01"
        }
    }
    
    print("\nOriginal dict:")
    print(sample)
    
    print("\nTOON format:")
    toon = to_toon(sample)
    print(toon)
    
    print("\nDecoded back:")
    decoded = from_toon(toon)
    print(decoded)
    
    print("\nToken efficiency:")
    stats = compare_token_efficiency(sample)
    print(f"JSON: {stats['json_chars']} chars, ~{stats['json_tokens_est']} tokens")
    print(f"TOON: {stats['toon_chars']} chars, ~{stats['toon_tokens_est']} tokens")
    print(f"Savings: {stats['token_savings_pct']}%")
