"""
Scenario 3: Domain Grouping Pattern - Organize Tables by Business Domain

Instead of 1000 individual table tools, expose domain-level tools that
handle all tables within that domain.

=============================================================================
✅ GOOD COP REVIEW - BENEFITS
=============================================================================
+ Natural organization: Matches how businesses think
+ Reduced tool count: 6-10 domain tools instead of 1000
+ Better LLM understanding: "query_sales" is clearer than "query_tbl_0842"
+ Easier maintenance: Add tables without adding tools
=============================================================================

=============================================================================
🚨 BAD COP REVIEW - REMAINING ISSUES
=============================================================================
⚠️ ISSUE 1: DOMAIN AMBIGUITY
- Where does "customer_orders" belong? Sales? CRM?
- Cross-domain queries become complicated
- Requires careful upfront domain modeling

⚠️ ISSUE 2: UNEVEN DISTRIBUTION
- Some domains may have 500 tables, others 10
- Large domains still have discovery problems
- Need sub-domain grouping for scale

⚠️ ISSUE 3: SCHEMA COMPLEXITY HIDDEN
- LLM doesn't see individual table schemas
- Must describe columns dynamically in tool output
- Risk of incorrect column name guesses

⚠️ ISSUE 4: RIGID STRUCTURE
- Adding new domains requires tool changes
- Renaming domains breaks existing prompts
- Not flexible for ad-hoc exploration

VERDICT: ✅ GOOD - Use for well-structured enterprise data (50-300 tables)
=============================================================================
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from config import generate_sample_tables, TableMetadata, DOMAIN_MAPPINGS
from utils import MCPTool, SimpleCache


@dataclass
class DomainInfo:
    """Information about a domain."""
    name: str
    description: str
    tables: List[TableMetadata]
    
    @property
    def table_count(self) -> int:
        return len(self.tables)
    
    @property
    def total_rows(self) -> int:
        return sum(t.row_count for t in self.tables)


class DomainGroupingMCPServer:
    """
    Domain Grouping Pattern: Tables are organized by business domain.
    
    Architecture:
    1. Group all tables into logical domains (sales, hr, finance, etc.)
    2. Expose one "query" tool per domain
    3. Domain tools accept table name + query parameters
    4. Provide domain exploration tools
    
    Example flow:
    1. User asks: "Show me recent orders"
    2. LLM calls: explore_domain(domain="sales")
    3. LLM learns: orders_0001, orders_0002, etc. exist
    4. LLM calls: query_sales_domain(table="orders_0001", filters={...})
    """
    
    # Domain descriptions for better LLM understanding
    DOMAIN_DESCRIPTIONS = {
        "sales": "Orders, customers, products, invoices, quotes, and sales opportunities",
        "hr": "Employees, departments, payroll, benefits, timesheets, and performance reviews",
        "finance": "Accounts, transactions, budgets, financial reports, audits, and taxes",
        "inventory": "Items, warehouses, shipments, suppliers, stock levels, and transfers",
        "manufacturing": "Work orders, bills of material, routing, quality control, and equipment",
        "crm": "Contacts, leads, marketing campaigns, activities, support cases, and contracts",
    }
    
    def __init__(self):
        self._domains: Dict[str, DomainInfo] = {}
        self._table_to_domain: Dict[str, str] = {}
        self._cache = SimpleCache(ttl_seconds=300)
    
    def initialize(self, tables: List[TableMetadata]) -> None:
        """Organize tables by domain."""
        print(f"📁 Organizing {len(tables)} tables into domains...")
        
        # Group tables by domain
        domain_tables: Dict[str, List[TableMetadata]] = {}
        for table in tables:
            domain = table.domain
            if domain not in domain_tables:
                domain_tables[domain] = []
            domain_tables[domain].append(table)
            self._table_to_domain[table.name] = domain
        
        # Create domain info objects
        for domain, tables_list in domain_tables.items():
            self._domains[domain] = DomainInfo(
                name=domain,
                description=self.DOMAIN_DESCRIPTIONS.get(domain, f"Tables for {domain}"),
                tables=tables_list,
            )
            print(f"   📂 {domain}: {len(tables_list)} tables")
        
        print(f"✅ Organized into {len(self._domains)} domains")
    
    def _create_domain_tools(self) -> List[MCPTool]:
        """Create one query tool per domain + exploration tools."""
        tools = []
        
        # Create exploration tool
        tools.append(MCPTool(
            name="list_domains",
            description="List all available data domains with their descriptions and table counts.",
            input_schema={
                "type": "object",
                "properties": {},
            },
        ))
        
        # Create per-domain exploration tool
        tools.append(MCPTool(
            name="explore_domain",
            description="List all tables within a specific domain, with their columns and descriptions.",
            input_schema={
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": f"Domain name. Options: {', '.join(self._domains.keys())}",
                        "enum": list(self._domains.keys()),
                    },
                    "search": {
                        "type": "string",
                        "description": "Optional: Filter tables by keyword",
                    },
                },
                "required": ["domain"],
            },
        ))
        
        # Create per-domain query tool
        for domain, info in self._domains.items():
            table_names = [t.name for t in info.tables[:20]]  # Show first 20 as examples
            more_count = len(info.tables) - 20 if len(info.tables) > 20 else 0
            
            tools.append(MCPTool(
                name=f"query_{domain}_domain",
                description=(
                    f"Query tables in the {domain.upper()} domain. "
                    f"{info.description}. "
                    f"Contains {info.table_count} tables including: {', '.join(table_names)}"
                    f"{f' and {more_count} more' if more_count else ''}. "
                    f"Use explore_domain first to see all table schemas."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "table": {
                            "type": "string",
                            "description": f"Table name within the {domain} domain",
                        },
                        "columns": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Columns to select (use explore_domain to see available columns)",
                        },
                        "filters": {
                            "type": "object",
                            "description": "Column filters as key-value pairs",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum rows to return",
                            "default": 100,
                        },
                    },
                    "required": ["table"],
                },
            ))
        
        return tools
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """Return domain-level tools."""
        tools = self._create_domain_tools()
        return [tool.to_dict() for tool in tools]
    
    async def list_domains(self) -> List[Dict[str, Any]]:
        """List all available domains."""
        return [
            {
                "name": domain,
                "description": info.description,
                "table_count": info.table_count,
                "total_rows": info.total_rows,
            }
            for domain, info in self._domains.items()
        ]
    
    async def explore_domain(
        self, 
        domain: str, 
        search: Optional[str] = None
    ) -> Dict[str, Any]:
        """Explore tables within a domain."""
        if domain not in self._domains:
            return {"error": f"Domain '{domain}' not found"}
        
        info = self._domains[domain]
        tables = info.tables
        
        # Filter by search if provided
        if search:
            search_lower = search.lower()
            tables = [t for t in tables if search_lower in t.name.lower() or 
                      search_lower in t.description.lower()]
        
        return {
            "domain": domain,
            "description": info.description,
            "total_tables": len(info.tables),
            "showing": len(tables),
            "tables": [
                {
                    "name": t.name,
                    "description": t.description,
                    "columns": [
                        {"name": c["name"], "type": c["type"]}
                        for c in t.columns
                    ],
                    "row_count": t.row_count,
                }
                for t in tables[:50]  # Limit to 50 tables per response
            ],
        }
    
    async def query_domain(
        self,
        domain: str,
        table: str,
        columns: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Query a table within a domain."""
        # Validate domain
        if domain not in self._domains:
            return {"error": f"Domain '{domain}' not found"}
        
        # Validate table belongs to domain
        expected_domain = self._table_to_domain.get(table)
        if expected_domain != domain:
            return {
                "error": f"Table '{table}' not found in {domain} domain",
                "hint": f"Table belongs to '{expected_domain}' domain" if expected_domain else "Table not found",
            }
        
        # Get table metadata
        table_meta = next(
            (t for t in self._domains[domain].tables if t.name == table),
            None
        )
        
        if not table_meta:
            return {"error": f"Table '{table}' not found"}
        
        # In reality, execute SQL query here
        return {
            "success": True,
            "domain": domain,
            "table": table,
            "columns_requested": columns or ["*"],
            "filters_applied": filters or {},
            "limit": limit,
            "data": [],  # Would contain actual query results
            "metadata": {
                "available_columns": [c["name"] for c in table_meta.columns],
                "row_count": table_meta.row_count,
            },
        }
    
    def calculate_token_overhead(self) -> Dict[str, int]:
        """Calculate token overhead."""
        import json
        
        tools = self.list_tools()
        tools_json = json.dumps(tools)
        estimated_tokens = len(tools_json) // 4
        
        return {
            "domain_count": len(self._domains),
            "total_tools": len(tools),
            "json_bytes": len(tools_json),
            "estimated_tokens": estimated_tokens,
            "vs_naive_tokens": 300000,
            "savings_percent": round((1 - estimated_tokens / 300000) * 100, 1),
        }


async def demonstrate():
    """Demonstrate the domain grouping pattern."""
    print("=" * 70)
    print("DEMONSTRATION: Domain Grouping Pattern")
    print("=" * 70)
    
    # Generate 1000 tables
    tables = generate_sample_tables(1000)
    
    # Initialize server
    server = DomainGroupingMCPServer()
    server.initialize(tables)
    
    # Show stats
    print("\n📊 STATISTICS:")
    stats = server.calculate_token_overhead()
    print(f"   Domains: {stats['domain_count']}")
    print(f"   Total tools: {stats['total_tools']}")
    print(f"   Estimated tokens: {stats['estimated_tokens']:,}")
    print(f"   Savings vs naive: {stats['savings_percent']}%")
    
    # Simulate usage flow
    print("\n🔍 STEP 1: List domains")
    domains = await server.list_domains()
    for d in domains:
        print(f"   📂 {d['name']}: {d['table_count']} tables - {d['description'][:40]}...")
    
    print("\n🔍 STEP 2: Explore a domain")
    exploration = await server.explore_domain("sales", search="orders")
    print(f"   Found {exploration['showing']} tables matching 'orders' in sales domain:")
    for t in exploration['tables'][:3]:
        print(f"   - {t['name']}: {len(t['columns'])} columns")
    
    print("\n🔍 STEP 3: Query a table")
    result = await server.query_domain(
        domain="sales",
        table=exploration['tables'][0]['name'],
        columns=["id", "created_at"],
        filters={"status": "active"},
        limit=10,
    )
    print(f"   Query result: {result['success']}")
    print(f"   Available columns: {result['metadata']['available_columns']}")
    
    print("\n" + "=" * 70)
    print("VERDICT: ✅ GOOD - Recommended for well-structured enterprise data")
    print("=" * 70)


# ============================================================================
# 🚨 BAD COP FINAL REVIEW 🚨
# ============================================================================
#
# WHAT THIS CODE DOES RIGHT:
# ✅ Natural business organization
# ✅ Minimal tool count (domains + 2 helper tools)
# ✅ Clear exploration path
# ✅ Table-to-domain validation
# ✅ Schema discovery within domains
#
# WHAT THIS CODE DOES WRONG:
# ⚠️ Hardcoded domain definitions (inflexible)
# ⚠️ Uneven domain sizes not handled well
# ⚠️ Cross-domain relationships lost
# ⚠️ No support for "I don't know which domain"
# ⚠️ Tool descriptions get long for large domains
#
# EDGE CASES NOT HANDLED:
# - Table that logically belongs to multiple domains
# - User doesn't know domain terminology
# - Schema changes requiring domain reorganization
# - Temporary/staging tables that don't fit domains
#
# WHEN TO USE THIS PATTERN:
# - Enterprise with clear organizational boundaries
# - 50-300 tables
# - Stable domain model
# - Users familiar with business terminology
#
# WHEN TO AVOID THIS PATTERN:
# - Exploratory analytics use cases
# - Rapidly changing schemas
# - Cross-domain queries are common
# - Users are technical (want direct table access)
#
# ============================================================================


if __name__ == "__main__":
    asyncio.run(demonstrate())
