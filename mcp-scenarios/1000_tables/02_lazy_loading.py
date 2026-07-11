"""
Scenario 2: Lazy Loading Pattern - Load Tools On-Demand

Instead of registering all 1000 tools upfront, expose a discovery mechanism
and load specific tools only when requested.

=============================================================================
✅ GOOD COP REVIEW - BENEFITS
=============================================================================
+ Minimal initial context: Only ~10 tools shown by default
+ Fast initialization: No upfront loading of 1000 tables
+ Scalable: Works the same for 100 or 100,000 tables
+ Cost efficient: Pay only for tools actually used
=============================================================================

=============================================================================
🚨 BAD COP REVIEW - REMAINING ISSUES
=============================================================================
⚠️ ISSUE 1: TWO-STEP DISCOVERY
- User must first "discover" then "use" a table
- Extra latency for every new table access
- LLM might not understand the discovery flow

⚠️ ISSUE 2: SESSION STATE MANAGEMENT
- Need to track which tools are "activated" per session
- State management adds complexity
- What happens on session timeout?

⚠️ ISSUE 3: DISCOVERY QUALITY
- Simple keyword search may miss relevant tables
- No semantic understanding of table relationships
- User needs to know approximate table names

VERDICT: ✅ GOOD - Use for medium complexity (50-500 tables)
=============================================================================
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field
from config import generate_sample_tables, TableMetadata
from utils import MCPTool, generate_tool_for_table, SimpleCache


@dataclass
class Session:
    """Represents a user session with activated tools."""
    session_id: str
    activated_tools: Set[str] = field(default_factory=set)
    max_tools: int = 50


class LazyLoadingMCPServer:
    """
    Lazy Loading Pattern: Tools are loaded on-demand, not upfront.
    
    Architecture:
    1. Start with minimal "meta-tools" for discovery
    2. User searches for tables they need
    3. System activates requested tools for that session
    4. Only activated tools appear in tool list
    """
    
    def __init__(self, max_active_tools: int = 50):
        # Table metadata index (loaded once at startup)
        self._table_index: Dict[str, TableMetadata] = {}
        
        # Session-specific active tools
        self._sessions: Dict[str, Session] = {}
        
        # Cache for generated tool definitions
        self._tool_cache = SimpleCache(ttl_seconds=3600)
        
        # Configuration
        self.max_active_tools = max_active_tools
        
        # Meta-tools (always available)
        self._meta_tools = self._create_meta_tools()
    
    def _create_meta_tools(self) -> Dict[str, MCPTool]:
        """Create the discovery/management tools."""
        return {
            "discover_tables": MCPTool(
                name="discover_tables",
                description="Search for available database tables by keyword. Returns matching table names and descriptions. Use this FIRST to find tables before querying them.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search keyword (e.g., 'customer', 'order', 'inventory')",
                        },
                        "domain": {
                            "type": "string",
                            "description": "Optional: Filter by domain (sales, hr, finance, etc.)",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum results to return",
                            "default": 20,
                        },
                    },
                    "required": ["query"],
                },
            ),
            "activate_table": MCPTool(
                name="activate_table",
                description="Activate a table for querying. After discovery, use this to enable a specific table's query tool.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "table_name": {
                            "type": "string",
                            "description": "The exact table name from discover_tables results",
                        },
                    },
                    "required": ["table_name"],
                },
            ),
            "list_active_tables": MCPTool(
                name="list_active_tables",
                description="List all currently activated tables that can be queried.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
            ),
            "deactivate_table": MCPTool(
                name="deactivate_table",
                description="Deactivate a table to free up space for other tables.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "table_name": {
                            "type": "string",
                            "description": "The table name to deactivate",
                        },
                    },
                    "required": ["table_name"],
                },
            ),
        }
    
    def initialize(self, tables: List[TableMetadata]) -> None:
        """Index tables for fast lookup (metadata only, not full tools)."""
        print(f"📇 Indexing {len(tables)} tables (metadata only)...")
        for table in tables:
            self._table_index[table.name] = table
        print(f"✅ Indexed {len(self._table_index)} tables")
    
    def get_or_create_session(self, session_id: str) -> Session:
        """Get or create a session."""
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(
                session_id=session_id,
                max_tools=self.max_active_tools,
            )
        return self._sessions[session_id]
    
    def list_tools(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Return meta-tools + session's activated tools.
        
        This is the key difference from naive approach:
        - Always returns meta-tools for discovery
        - Only returns activated table tools (max 50)
        - Total tools in response: ~54 instead of 1000
        """
        session = self.get_or_create_session(session_id)
        
        # Start with meta-tools (always available)
        tools = [tool.to_dict() for tool in self._meta_tools.values()]
        
        # Add activated table tools
        for table_name in session.activated_tools:
            tool = self._get_or_create_tool(table_name)
            if tool:
                tools.append(tool.to_dict())
        
        return tools
    
    def _get_or_create_tool(self, table_name: str) -> Optional[MCPTool]:
        """Get tool from cache or create it."""
        # Check cache first
        cached = self._tool_cache.get(table_name)
        if cached:
            return cached
        
        # Create tool if table exists
        table = self._table_index.get(table_name)
        if not table:
            return None
        
        tool = generate_tool_for_table(
            table_name=table.name,
            schema=table.schema,
            columns=table.columns,
        )
        
        # Cache for future use
        self._tool_cache.set(table_name, tool)
        return tool
    
    async def discover_tables(
        self, 
        query: str, 
        domain: Optional[str] = None, 
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Search for tables matching a query."""
        query_lower = query.lower()
        results = []
        
        for name, table in self._table_index.items():
            # Skip if domain filter doesn't match
            if domain and table.domain != domain:
                continue
            
            # Simple keyword matching
            score = 0
            if query_lower in name.lower():
                score += 10
            if query_lower in table.description.lower():
                score += 5
            if query_lower in table.domain.lower():
                score += 3
            
            if score > 0:
                results.append({
                    "name": name,
                    "schema": table.schema,
                    "domain": table.domain,
                    "description": table.description,
                    "row_count": table.row_count,
                    "relevance_score": score,
                })
        
        # Sort by relevance and limit
        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        return results[:limit]
    
    async def activate_table(self, session_id: str, table_name: str) -> Dict[str, Any]:
        """Activate a table for a session."""
        session = self.get_or_create_session(session_id)
        
        # Check if table exists
        if table_name not in self._table_index:
            return {
                "success": False,
                "error": f"Table '{table_name}' not found",
            }
        
        # Check if already activated
        if table_name in session.activated_tools:
            return {
                "success": True,
                "message": f"Table '{table_name}' is already active",
            }
        
        # Check limit
        if len(session.activated_tools) >= session.max_tools:
            return {
                "success": False,
                "error": f"Maximum {session.max_tools} tables can be active. Deactivate some first.",
                "active_tables": list(session.activated_tools),
            }
        
        # Activate
        session.activated_tools.add(table_name)
        
        return {
            "success": True,
            "message": f"Table '{table_name}' is now active",
            "total_active": len(session.activated_tools),
        }
    
    async def deactivate_table(self, session_id: str, table_name: str) -> Dict[str, Any]:
        """Deactivate a table for a session."""
        session = self.get_or_create_session(session_id)
        
        if table_name not in session.activated_tools:
            return {
                "success": False,
                "error": f"Table '{table_name}' is not active",
            }
        
        session.activated_tools.discard(table_name)
        
        return {
            "success": True,
            "message": f"Table '{table_name}' deactivated",
            "total_active": len(session.activated_tools),
        }
    
    def calculate_token_overhead(self, session_id: str) -> Dict[str, int]:
        """Calculate token overhead for this session."""
        import json
        
        tools = self.list_tools(session_id)
        tools_json = json.dumps(tools)
        estimated_tokens = len(tools_json) // 4
        
        return {
            "meta_tools": len(self._meta_tools),
            "active_table_tools": len(tools) - len(self._meta_tools),
            "total_tools": len(tools),
            "json_bytes": len(tools_json),
            "estimated_tokens": estimated_tokens,
            "vs_naive_tokens": 300000,  # Naive approach estimate
            "savings_percent": round((1 - estimated_tokens / 300000) * 100, 1),
        }


async def demonstrate():
    """Demonstrate the lazy loading pattern."""
    print("=" * 70)
    print("DEMONSTRATION: Lazy Loading Pattern")
    print("=" * 70)
    
    # Generate 1000 tables
    tables = generate_sample_tables(1000)
    
    # Initialize server
    server = LazyLoadingMCPServer(max_active_tools=50)
    server.initialize(tables)
    
    session_id = "user_session_123"
    
    # Show initial state
    print("\n📊 INITIAL STATE:")
    stats = server.calculate_token_overhead(session_id)
    print(f"   Meta tools: {stats['meta_tools']}")
    print(f"   Active table tools: {stats['active_table_tools']}")
    print(f"   Estimated tokens: {stats['estimated_tokens']:,}")
    print(f"   Savings vs naive: {stats['savings_percent']}%")
    
    # Simulate discovery flow
    print("\n🔍 STEP 1: Discover tables")
    results = await server.discover_tables("orders", domain="sales", limit=5)
    print(f"   Found {len(results)} tables matching 'orders':")
    for r in results[:3]:
        print(f"   - {r['name']}: {r['description'][:50]}...")
    
    # Activate some tables
    print("\n✅ STEP 2: Activate tables")
    for r in results[:3]:
        result = await server.activate_table(session_id, r['name'])
        print(f"   {result['message']}")
    
    # Show updated state
    print("\n📊 AFTER ACTIVATION:")
    stats = server.calculate_token_overhead(session_id)
    print(f"   Meta tools: {stats['meta_tools']}")
    print(f"   Active table tools: {stats['active_table_tools']}")
    print(f"   Total tools: {stats['total_tools']}")
    print(f"   Estimated tokens: {stats['estimated_tokens']:,}")
    print(f"   Savings vs naive: {stats['savings_percent']}%")
    
    print("\n" + "=" * 70)
    print("VERDICT: ✅ GOOD - Recommended for medium-scale scenarios")
    print("=" * 70)


# ============================================================================
# 🚨 BAD COP FINAL REVIEW 🚨
# ============================================================================
#
# WHAT THIS CODE DOES RIGHT:
# ✅ Minimal initial footprint
# ✅ On-demand tool loading
# ✅ Session isolation
# ✅ Tool caching
# ✅ Clear discovery flow
#
# WHAT THIS CODE DOES WRONG:
# ⚠️ Simple keyword search (no semantic search)
# ⚠️ No fuzzy matching for typos
# ⚠️ No table relationship understanding
# ⚠️ Session state management complexity
# ⚠️ Max 50 active tables might be limiting
#
# WHEN TO USE THIS PATTERN:
# - 50-500 tables
# - Users typically query same tables repeatedly
# - Tables have clear, searchable names
#
# WHEN TO AVOID THIS PATTERN:
# - Users need to explore unknown data
# - Tables have cryptic names (e.g., "TBL_X_1234")
# - Cross-table queries are common
#
# BETTER ALTERNATIVES FOR LARGE SCALE:
# - 04_search_discovery.py: Better search with embeddings
# - 05_hybrid_approach.py: Combines multiple strategies
#
# ============================================================================


if __name__ == "__main__":
    asyncio.run(demonstrate())
