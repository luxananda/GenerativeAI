"""
Scenario 6: Separate Servers Pattern - One MCP Server Per System

Each backend system (Oracle, SAP, Salesforce) gets its own dedicated MCP server.
The client connects to multiple MCP servers independently.

=============================================================================
✅ GOOD COP REVIEW - BENEFITS
=============================================================================
+ Complete isolation: One system's issues don't affect others
+ Independent scaling: Scale each server based on its load
+ Technology-specific optimization: Each server tailored to its system
+ Clear ownership: Team A owns Oracle MCP, Team B owns SAP MCP
+ Simple implementation: Each server is straightforward
=============================================================================

=============================================================================
🚨 BAD COP REVIEW - CRITICAL ISSUES
=============================================================================
🚨 ISSUE 1: CLIENT COMPLEXITY
- Client must manage 3+ MCP connections
- Each connection has its own lifecycle
- Retry logic multiplied by number of connections

🚨 ISSUE 2: CROSS-SYSTEM QUERIES IMPOSSIBLE
- "Join Oracle customers with SAP orders" requires client-side logic
- LLM cannot reason across systems easily
- Data integration becomes client responsibility

🚨 ISSUE 3: TOOL NAMING CONFLICTS
- Oracle might have "query_customers", SAP might too
- Need naming conventions or namespacing
- LLM confusion about which system to use

⚠️ ISSUE 4: CREDENTIAL MANAGEMENT
- Each server needs its own credentials
- Client must secure 3+ sets of credentials
- More attack surface

VERDICT: ✅ GOOD - Use for truly independent systems with no cross-queries
=============================================================================
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
from abc import ABC, abstractmethod
from config import SystemType, DatabaseConfig, SYSTEM_CONFIGS


class BaseMCPServer(ABC):
    """Base class for system-specific MCP servers."""
    
    def __init__(self, system_type: SystemType, config: DatabaseConfig):
        self.system_type = system_type
        self.config = config
        self.server_name = f"{system_type.value}_mcp"
    
    @abstractmethod
    def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools for this system."""
        pass
    
    @abstractmethod
    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool."""
        pass


class OracleMCPServer(BaseMCPServer):
    """
    MCP Server for Oracle Database.
    
    Features specific to Oracle:
    - PL/SQL procedure execution
    - Materialized view refresh
    - Oracle-specific data types (CLOB, BLOB, etc.)
    """
    
    def __init__(self, config: DatabaseConfig):
        super().__init__(SystemType.ORACLE, config)
        self._tables = self._discover_tables()
    
    def _discover_tables(self) -> Dict[str, Dict]:
        """Discover Oracle tables."""
        # In production: query DBA_TABLES, ALL_TAB_COLUMNS, etc.
        return {
            "CUSTOMERS": {"columns": ["CUSTOMER_ID", "NAME", "EMAIL"], "rows": 50000},
            "ORDERS": {"columns": ["ORDER_ID", "CUSTOMER_ID", "TOTAL"], "rows": 200000},
            "PRODUCTS": {"columns": ["PRODUCT_ID", "NAME", "PRICE"], "rows": 5000},
            "INVENTORY": {"columns": ["PRODUCT_ID", "WAREHOUSE", "QTY"], "rows": 25000},
        }
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """Return Oracle-specific tools."""
        tools = [
            {
                "name": "oracle_query",
                "description": "Execute a SELECT query on Oracle database. Supports PL/SQL.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "sql": {"type": "string", "description": "SQL query to execute"},
                        "params": {"type": "object", "description": "Bind parameters"},
                        "limit": {"type": "integer", "default": 100},
                    },
                    "required": ["sql"],
                },
            },
            {
                "name": "oracle_list_tables",
                "description": "List all tables in the Oracle database with their schemas.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "oracle_describe_table",
                "description": "Get detailed schema for an Oracle table.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "table_name": {"type": "string"},
                    },
                    "required": ["table_name"],
                },
            },
            {
                "name": "oracle_execute_procedure",
                "description": "Execute a PL/SQL stored procedure.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "procedure_name": {"type": "string"},
                        "params": {"type": "object"},
                    },
                    "required": ["procedure_name"],
                },
            },
        ]
        return tools
    
    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Execute Oracle-specific tools."""
        if name == "oracle_list_tables":
            return {"tables": list(self._tables.keys())}
        
        if name == "oracle_describe_table":
            table = arguments.get("table_name")
            if table in self._tables:
                return self._tables[table]
            return {"error": f"Table {table} not found"}
        
        if name == "oracle_query":
            return {"status": "success", "rows": [], "message": "Query executed"}
        
        if name == "oracle_execute_procedure":
            return {"status": "success", "message": "Procedure executed"}
        
        return {"error": f"Unknown tool: {name}"}


class SAPMCPServer(BaseMCPServer):
    """
    MCP Server for SAP (HANA/S4HANA).
    
    Features specific to SAP:
    - BAPI/RFC calls
    - SAP-specific table naming (VBAK, VBAP, etc.)
    - Transport management awareness
    """
    
    def __init__(self, config: DatabaseConfig):
        super().__init__(SystemType.SAP, config)
        self._tables = self._discover_tables()
    
    def _discover_tables(self) -> Dict[str, Dict]:
        """Discover SAP tables."""
        # SAP table names are cryptic - descriptions are crucial
        return {
            "VBAK": {"description": "Sales Document Header", "columns": ["VBELN", "ERDAT", "KUNNR"]},
            "VBAP": {"description": "Sales Document Item", "columns": ["VBELN", "POSNR", "MATNR"]},
            "KNA1": {"description": "Customer Master", "columns": ["KUNNR", "NAME1", "LAND1"]},
            "MARA": {"description": "Material Master", "columns": ["MATNR", "MTART", "MATKL"]},
            "EKKO": {"description": "Purchase Order Header", "columns": ["EBELN", "BUKRS", "LIFNR"]},
        }
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """Return SAP-specific tools."""
        tools = [
            {
                "name": "sap_query",
                "description": "Query SAP tables. Note: SAP table names are abbreviated (VBAK=Sales Header, KNA1=Customer Master, etc.)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "table": {"type": "string", "description": "SAP table name (e.g., VBAK, KNA1)"},
                        "fields": {"type": "array", "items": {"type": "string"}},
                        "where": {"type": "string", "description": "Where clause"},
                        "limit": {"type": "integer", "default": 100},
                    },
                    "required": ["table"],
                },
            },
            {
                "name": "sap_list_tables",
                "description": "List SAP tables with their human-readable descriptions.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "sap_call_bapi",
                "description": "Call a SAP BAPI (Business Application Programming Interface).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "bapi_name": {"type": "string", "description": "BAPI name (e.g., BAPI_CUSTOMER_GETLIST)"},
                        "import_params": {"type": "object"},
                        "table_params": {"type": "object"},
                    },
                    "required": ["bapi_name"],
                },
            },
            {
                "name": "sap_search_tables",
                "description": "Search for SAP tables by description (since names are cryptic).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search term (e.g., 'sales', 'customer')"},
                    },
                    "required": ["query"],
                },
            },
        ]
        return tools
    
    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Execute SAP-specific tools."""
        if name == "sap_list_tables":
            return {
                "tables": [
                    {"name": k, "description": v["description"]}
                    for k, v in self._tables.items()
                ]
            }
        
        if name == "sap_search_tables":
            query = arguments.get("query", "").lower()
            matches = [
                {"name": k, "description": v["description"]}
                for k, v in self._tables.items()
                if query in v["description"].lower()
            ]
            return {"results": matches}
        
        if name == "sap_query":
            return {"status": "success", "rows": [], "message": "Query executed"}
        
        if name == "sap_call_bapi":
            return {"status": "success", "export_params": {}, "message": "BAPI executed"}
        
        return {"error": f"Unknown tool: {name}"}


class SalesforceMCPServer(BaseMCPServer):
    """
    MCP Server for Salesforce.
    
    Features specific to Salesforce:
    - SOQL queries
    - Object/Field API
    - Metadata API
    - REST/Bulk API support
    """
    
    def __init__(self, config: DatabaseConfig):
        super().__init__(SystemType.SALESFORCE, config)
        self._objects = self._discover_objects()
    
    def _discover_objects(self) -> Dict[str, Dict]:
        """Discover Salesforce objects."""
        return {
            "Account": {"label": "Account", "fields": ["Id", "Name", "Industry", "Website"]},
            "Contact": {"label": "Contact", "fields": ["Id", "FirstName", "LastName", "Email"]},
            "Opportunity": {"label": "Opportunity", "fields": ["Id", "Name", "Amount", "StageName"]},
            "Lead": {"label": "Lead", "fields": ["Id", "FirstName", "LastName", "Company"]},
            "Case": {"label": "Case", "fields": ["Id", "Subject", "Status", "Priority"]},
        }
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """Return Salesforce-specific tools."""
        tools = [
            {
                "name": "sf_soql_query",
                "description": "Execute a SOQL query on Salesforce objects.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "soql": {"type": "string", "description": "SOQL query (e.g., SELECT Id, Name FROM Account)"},
                    },
                    "required": ["soql"],
                },
            },
            {
                "name": "sf_list_objects",
                "description": "List all Salesforce objects (Account, Contact, Opportunity, etc.)",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "sf_describe_object",
                "description": "Get detailed metadata for a Salesforce object.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "object_name": {"type": "string", "description": "Object API name"},
                    },
                    "required": ["object_name"],
                },
            },
            {
                "name": "sf_create_record",
                "description": "Create a new record in Salesforce.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "object_name": {"type": "string"},
                        "fields": {"type": "object", "description": "Field values"},
                    },
                    "required": ["object_name", "fields"],
                },
            },
            {
                "name": "sf_update_record",
                "description": "Update an existing Salesforce record.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "object_name": {"type": "string"},
                        "record_id": {"type": "string"},
                        "fields": {"type": "object"},
                    },
                    "required": ["object_name", "record_id", "fields"],
                },
            },
        ]
        return tools
    
    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Execute Salesforce-specific tools."""
        if name == "sf_list_objects":
            return {
                "objects": [
                    {"name": k, "label": v["label"]}
                    for k, v in self._objects.items()
                ]
            }
        
        if name == "sf_describe_object":
            obj = arguments.get("object_name")
            if obj in self._objects:
                return self._objects[obj]
            return {"error": f"Object {obj} not found"}
        
        if name == "sf_soql_query":
            return {"status": "success", "records": [], "totalSize": 0}
        
        if name in ["sf_create_record", "sf_update_record"]:
            return {"status": "success", "id": "001XXXXXXXXXXXX"}
        
        return {"error": f"Unknown tool: {name}"}


@dataclass
class MultiServerClient:
    """
    Client that manages connections to multiple MCP servers.
    
    This is what the LLM client would need to implement.
    """
    servers: Dict[str, BaseMCPServer]
    
    def list_all_tools(self) -> Dict[str, List[Dict[str, Any]]]:
        """List tools from all connected servers."""
        result = {}
        for name, server in self.servers.items():
            result[name] = server.list_tools()
        return result
    
    def get_combined_tool_count(self) -> int:
        """Total tools across all servers."""
        return sum(len(s.list_tools()) for s in self.servers.values())
    
    async def route_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Route a tool call to the appropriate server."""
        # Determine which server handles this tool
        for name, server in self.servers.items():
            tool_names = [t["name"] for t in server.list_tools()]
            if tool_name in tool_names:
                return await server.execute_tool(tool_name, arguments)
        
        return {"error": f"No server found for tool: {tool_name}"}


def demonstrate():
    """Demonstrate the separate servers pattern."""
    print("=" * 70)
    print("DEMONSTRATION: Separate MCP Servers Pattern")
    print("=" * 70)
    
    # Create individual servers
    oracle_server = OracleMCPServer(SYSTEM_CONFIGS[SystemType.ORACLE])
    sap_server = SAPMCPServer(SYSTEM_CONFIGS[SystemType.SAP])
    sf_server = SalesforceMCPServer(SYSTEM_CONFIGS[SystemType.SALESFORCE])
    
    # Create multi-server client
    client = MultiServerClient(servers={
        "oracle": oracle_server,
        "sap": sap_server,
        "salesforce": sf_server,
    })
    
    # Show tools per server
    print("\n📊 TOOLS PER SERVER:")
    all_tools = client.list_all_tools()
    for server_name, tools in all_tools.items():
        print(f"\n   🖥️  {server_name.upper()} ({len(tools)} tools):")
        for tool in tools[:3]:
            print(f"      - {tool['name']}: {tool['description'][:50]}...")
        if len(tools) > 3:
            print(f"      ... and {len(tools) - 3} more")
    
    print(f"\n📈 TOTAL TOOLS: {client.get_combined_tool_count()}")
    
    # Show the challenge
    print("\n⚠️  CHALLENGES WITH THIS APPROACH:")
    print("   1. Client manages 3 separate MCP connections")
    print("   2. Cross-system query example:")
    print("      'Find Oracle customers who have Salesforce opportunities'")
    print("      → Requires client to query both and join in memory")
    print("   3. Tool naming: oracle_query vs sap_query vs sf_soql_query")
    print("      → LLM must learn different naming for similar operations")
    
    print("\n" + "=" * 70)
    print("VERDICT: ✅ GOOD - For truly independent systems")
    print("=" * 70)


# ============================================================================
# 🚨 BAD COP FINAL REVIEW 🚨
# ============================================================================
#
# WHAT THIS CODE DOES RIGHT:
# ✅ Clean separation of concerns
# ✅ System-specific optimizations
# ✅ Independent failure domains
# ✅ Clear tool naming (prefixed by system)
# ✅ Easy to add new systems
#
# WHAT THIS CODE DOES WRONG:
# ⚠️ Client must manage multiple connections
# ⚠️ No cross-system query support
# ⚠️ Inconsistent tool interfaces
# ⚠️ No unified schema view
# ⚠️ Credential sprawl
#
# USE CASE ANALYSIS:
#
# GOOD FIT:
# - Each system serves different teams
# - No cross-system queries needed
# - Systems have very different APIs
# - Strong isolation requirements
#
# BAD FIT:
# - Unified analytics across systems
# - LLM needs holistic data view
# - Common operations across systems
# - Single team manages all systems
#
# MIGRATION PATH:
# Start here → Add gateway when cross-queries needed → Federate for scale
#
# ============================================================================


if __name__ == "__main__":
    demonstrate()
