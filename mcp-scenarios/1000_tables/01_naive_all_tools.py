"""
Scenario 1: Naive Approach - Register ALL 1000 Tables as Tools

This is an ANTI-PATTERN demonstration showing what NOT to do.

=============================================================================
🚨 BAD COP REVIEW - CRITICAL ISSUES 🚨
=============================================================================

PROBLEM 1: CONTEXT WINDOW EXPLOSION
- Each tool definition is ~200-500 tokens
- 1000 tools × 300 tokens = 300,000 tokens JUST for tool definitions
- Most LLMs have 8K-128K context windows
- You've used ALL context before the user even asks a question!

PROBLEM 2: TOOL SELECTION CONFUSION
- LLMs struggle to pick the right tool from 1000 options
- Similar names cause hallucinations (orders_0001 vs orders_0002)
- No semantic grouping = random tool selection

PROBLEM 3: RESPONSE LATENCY
- Every request sends ALL 1000 tool definitions
- Network overhead: 300KB+ per request
- API costs: You're paying for 300K tokens EVERY call

PROBLEM 4: NO SCALING PATH
- What happens when you have 10,000 tables?
- This approach has O(n) complexity for EVERY operation

VERDICT: ❌ DO NOT USE IN PRODUCTION
=============================================================================
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Any, Dict, List
from config import generate_sample_tables, TableMetadata
from utils import MCPTool, generate_tool_for_table


class NaiveMCPServer:
    """
    ANTI-PATTERN: Registers all 1000 tables as individual tools.
    
    DO NOT USE THIS APPROACH IN PRODUCTION.
    """
    
    def __init__(self):
        self.tools: Dict[str, MCPTool] = {}
        self.tables: List[TableMetadata] = []
    
    def initialize(self, tables: List[TableMetadata]) -> None:
        """
        🚨 BAD: Loads ALL tables into memory and creates ALL tools.
        
        This will:
        - Consume excessive memory
        - Take a long time to initialize
        - Create an unusable tool list
        """
        self.tables = tables
        
        print(f"⚠️  WARNING: Loading {len(tables)} tables as individual tools...")
        print("⚠️  This is an anti-pattern and should NOT be used in production!")
        
        for table in tables:
            tool = generate_tool_for_table(
                table_name=table.name,
                schema=table.schema,
                columns=table.columns,
            )
            self.tools[tool.name] = tool
        
        print(f"❌ Created {len(self.tools)} tools - THIS IS TOO MANY!")
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """
        🚨 BAD: Returns ALL 1000 tools in every response.
        
        Problems:
        - Response size: ~300KB of JSON
        - Token count: ~300,000 tokens
        - LLM confusion: Can't choose from 1000 options
        """
        return [tool.to_dict() for tool in self.tools.values()]
    
    def calculate_token_overhead(self) -> Dict[str, int]:
        """Calculate the token overhead of this approach."""
        import json
        
        tools_json = json.dumps(self.list_tools())
        estimated_tokens = len(tools_json) // 4  # rough estimate
        
        return {
            "total_tools": len(self.tools),
            "json_bytes": len(tools_json),
            "estimated_tokens": estimated_tokens,
            "typical_context_window": 128000,
            "context_used_percent": round(estimated_tokens / 128000 * 100, 1),
        }
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool by name."""
        if name not in self.tools:
            raise ValueError(f"Tool '{name}' not found")
        
        # In reality, this would query the database
        return {"status": "success", "data": [], "message": f"Executed {name}"}


def demonstrate_problems():
    """
    Demonstrate why this approach is terrible.
    """
    print("=" * 70)
    print("DEMONSTRATION: Why Naive Approach Fails")
    print("=" * 70)
    
    # Generate 1000 tables
    tables = generate_sample_tables(1000)
    
    # Initialize the naive server
    server = NaiveMCPServer()
    server.initialize(tables)
    
    # Calculate overhead
    stats = server.calculate_token_overhead()
    
    print("\n📊 STATISTICS:")
    print(f"   Total tools: {stats['total_tools']}")
    print(f"   JSON size: {stats['json_bytes']:,} bytes ({stats['json_bytes']/1024:.1f} KB)")
    print(f"   Estimated tokens: {stats['estimated_tokens']:,}")
    print(f"   Context window usage: {stats['context_used_percent']}%")
    
    print("\n🚨 CRITICAL ISSUES:")
    print("   1. Context window nearly exhausted before user query")
    print("   2. Every API call costs ~300K tokens ($$$)")
    print("   3. LLM cannot effectively choose from 1000 tools")
    print("   4. No semantic organization")
    print("   5. Massive network overhead per request")
    
    print("\n💡 BETTER ALTERNATIVES:")
    print("   - 02_lazy_loading.py: Load tools on-demand")
    print("   - 03_domain_grouping.py: Group by business domain")
    print("   - 04_search_discovery.py: Search-based discovery")
    print("   - 05_hybrid_approach.py: Combined best practices")
    
    print("\n" + "=" * 70)
    print("VERDICT: ❌ DO NOT USE THIS APPROACH")
    print("=" * 70)


# ============================================================================
# 🚨 BAD COP FINAL REVIEW 🚨
# ============================================================================
#
# WHAT THIS CODE DOES WRONG:
# 1. Registers ALL tools upfront - wasteful and slow
# 2. Returns ALL tools in list_tools() - context explosion
# 3. No pagination - O(n) for every operation
# 4. No caching - repeated serialization
# 5. No search - LLM must guess from 1000 options
#
# WHEN THIS APPROACH MIGHT BE ACCEPTABLE:
# - Never. Even with 10 tables, use domain grouping.
# - The only exception: you're building a demo that never goes to production.
#
# COST ANALYSIS (assuming GPT-4 pricing):
# - Input tokens: ~300,000 per request × $0.03/1K = $9.00 per request!
# - 100 requests/day = $900/day = $27,000/month
# - Compare to lazy loading: ~$270/month (100x cheaper)
#
# ============================================================================


if __name__ == "__main__":
    demonstrate_problems()
