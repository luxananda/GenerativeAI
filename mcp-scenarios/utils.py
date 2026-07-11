"""
Shared utilities for MCP scenarios.
"""
import asyncio
import logging
import time
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, TypeVar
from dataclasses import dataclass
import json
import hashlib

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class MCPTool:
    """Represents an MCP tool definition."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Optional[Callable] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


@dataclass
class MCPResource:
    """Represents an MCP resource."""
    uri: str
    name: str
    description: str
    mime_type: str = "application/json"


class SimpleCache:
    """Simple in-memory cache with TTL."""
    
    def __init__(self, ttl_seconds: int = 300):
        self._cache: Dict[str, tuple] = {}
        self._ttl = ttl_seconds
    
    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < self._ttl:
                return value
            del self._cache[key]
        return None
    
    def set(self, key: str, value: Any) -> None:
        self._cache[key] = (value, time.time())
    
    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)
    
    def clear(self) -> None:
        self._cache.clear()


def generate_tool_for_table(table_name: str, schema: str, columns: List[Dict]) -> MCPTool:
    """Generate an MCP tool definition for a database table."""
    column_desc = ", ".join([f"{c['name']} ({c['type']})" for c in columns])
    
    return MCPTool(
        name=f"query_{schema.lower()}_{table_name.lower()}",
        description=f"Query the {table_name} table in {schema}. Columns: {column_desc}",
        input_schema={
            "type": "object",
            "properties": {
                "filters": {
                    "type": "object",
                    "description": "Column filters as key-value pairs",
                },
                "columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Columns to select (default: all)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum rows to return",
                    "default": 100,
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of rows to skip",
                    "default": 0,
                },
            },
            "required": [],
        },
    )


def rate_limiter(calls_per_second: float = 10.0):
    """Decorator to rate limit function calls."""
    min_interval = 1.0 / calls_per_second
    last_call = [0.0]
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            elapsed = time.time() - last_call[0]
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
            last_call[0] = time.time()
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def chunk_list(lst: List[T], chunk_size: int) -> List[List[T]]:
    """Split a list into chunks of specified size."""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def generate_cache_key(*args, **kwargs) -> str:
    """Generate a cache key from arguments."""
    key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True)
    return hashlib.md5(key_data.encode()).hexdigest()


class ToolRegistry:
    """Registry for managing MCP tools."""
    
    def __init__(self):
        self._tools: Dict[str, MCPTool] = {}
        self._domains: Dict[str, List[str]] = {}
    
    def register(self, tool: MCPTool, domain: str = "default") -> None:
        self._tools[tool.name] = tool
        if domain not in self._domains:
            self._domains[domain] = []
        self._domains[domain].append(tool.name)
    
    def get(self, name: str) -> Optional[MCPTool]:
        return self._tools.get(name)
    
    def get_by_domain(self, domain: str) -> List[MCPTool]:
        tool_names = self._domains.get(domain, [])
        return [self._tools[name] for name in tool_names if name in self._tools]
    
    def search(self, query: str, limit: int = 20) -> List[MCPTool]:
        """Simple search across tool names and descriptions."""
        query_lower = query.lower()
        results = []
        for tool in self._tools.values():
            score = 0
            if query_lower in tool.name.lower():
                score += 10
            if query_lower in tool.description.lower():
                score += 5
            if score > 0:
                results.append((score, tool))
        results.sort(key=lambda x: x[0], reverse=True)
        return [tool for _, tool in results[:limit]]
    
    def list_all(self) -> List[MCPTool]:
        return list(self._tools.values())
    
    def list_domains(self) -> List[str]:
        return list(self._domains.keys())
    
    def count(self) -> int:
        return len(self._tools)


class CircuitBreaker:
    """Circuit breaker pattern for fault tolerance."""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time = 0.0
        self.state = "closed"
    
    def can_execute(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = "half-open"
                return True
            return False
        return True  # half-open allows one request
    
    def record_success(self) -> None:
        self.failures = 0
        self.state = "closed"
    
    def record_failure(self) -> None:
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            self.state = "open"


def format_tool_list_for_llm(tools: List[MCPTool], max_tokens: int = 4000) -> str:
    """Format tools for LLM consumption with token budget."""
    output = []
    current_tokens = 0
    
    for tool in tools:
        tool_text = f"- {tool.name}: {tool.description[:100]}..."
        estimated_tokens = len(tool_text) // 4
        
        if current_tokens + estimated_tokens > max_tokens:
            output.append(f"... and {len(tools) - len(output)} more tools")
            break
        
        output.append(tool_text)
        current_tokens += estimated_tokens
    
    return "\n".join(output)
