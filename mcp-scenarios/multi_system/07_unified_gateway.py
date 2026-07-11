"""
Scenario 7: Unified Gateway Pattern - Single MCP Server for All Systems

A single MCP gateway server that abstracts multiple backend systems.
The client sees one unified interface regardless of how many systems exist.

=============================================================================
✅ GOOD COP REVIEW - BENEFITS
=============================================================================
+ Single connection: Client manages one MCP connection
+ Unified interface: Same query syntax for all systems
+ Cross-system queries: Gateway can join data from multiple sources
+ Centralized auth: One credential for all systems
+ Easier LLM reasoning: Consistent tool naming and behavior
=============================================================================

=============================================================================
🚨 BAD COP REVIEW - CRITICAL ISSUES
=============================================================================
🚨 ISSUE 1: SINGLE POINT OF FAILURE
- Gateway down = all systems inaccessible
- Must implement HA/failover
- Blast radius is enormous

🚨 ISSUE 2: PERFORMANCE BOTTLENECK
- All traffic flows through gateway
- Cross-system queries are N+1
- Caching becomes complex

🚨 ISSUE 3: ABSTRACTION LEAKAGE
- Lowest common denominator APIs
- System-specific features may be hidden
- Error messages lose context

⚠️ ISSUE 4: COMPLEXITY CONCENTRATION
- Gateway becomes a "god class"
- Hard to test all system combinations
- Routing logic can get messy

VERDICT: ✅ GOOD - Use for 2-5 systems with moderate cross-queries
=============================================================================
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field
from enum import Enum
import time
from config import SystemType, DatabaseConfig, SYSTEM_CONFIGS
from utils import SimpleCache, CircuitBreaker


class QueryLanguage(Enum):
    """Supported query languages."""
    SQL = "sql"
    SOQL = "soql"
    UNIVERSAL = "universal"  # Gateway's abstraction


@dataclass
class SystemConnection:
    """Connection to a backend system."""
    system_type: SystemType
    config: DatabaseConfig
    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    healthy: bool = True
    last_health_check: float = 0.0


class UnifiedGatewayMCPServer:
    """
    Unified Gateway: Single MCP server that routes to multiple backends.
    
    Architecture:
    
    ┌─────────────────────────────────────────────────────┐
    │                    MCP Client                        │
    │                  (single connection)                 │
    └─────────────────────────┬───────────────────────────┘
                              │
    ┌─────────────────────────▼───────────────────────────┐
    │               UNIFIED GATEWAY MCP                    │
    │  ┌─────────┐  ┌─────────┐  ┌─────────────────────┐  │
    │  │ Router  │  │ Cache   │  │ Query Translator    │  │
    │  └────┬────┘  └─────────┘  └─────────────────────┘  │
    │       │                                              │
    │  ┌────▼─────────────────────────────────────────┐   │
    │  │           Connection Pool                     │   │
    │  │  ┌────────┐  ┌────────┐  ┌────────────────┐  │   │
    │  │  │ Oracle │  │  SAP   │  │  Salesforce    │  │   │
    │  │  └────────┘  └────────┘  └────────────────┘  │   │
    │  └──────────────────────────────────────────────┘   │
    └─────────────────────────────────────────────────────┘
    
    Key Features:
    - Single endpoint for all operations
    - Automatic routing based on entity type
    - Cross-system query support
    - Unified error handling
    """
    
    # Entity-to-system routing table
    ENTITY_ROUTING = {
        # Oracle entities
        "customers": SystemType.ORACLE,
        "orders": SystemType.ORACLE,
        "products": SystemType.ORACLE,
        "inventory": SystemType.ORACLE,
        
        # SAP entities
        "sales_documents": SystemType.SAP,
        "purchase_orders": SystemType.SAP,
        "materials": SystemType.SAP,
        "vendors": SystemType.SAP,
        
        # Salesforce entities
        "accounts": SystemType.SALESFORCE,
        "contacts": SystemType.SALESFORCE,
        "opportunities": SystemType.SALESFORCE,
        "leads": SystemType.SALESFORCE,
        "cases": SystemType.SALESFORCE,
    }
    
    # Cross-system entity relationships
    ENTITY_RELATIONSHIPS = {
        "customers": ["accounts", "contacts"],  # Oracle customers link to SF accounts
        "orders": ["opportunities", "sales_documents"],
        "products": ["materials"],
    }
    
    def __init__(self):
        self._systems: Dict[SystemType, SystemConnection] = {}
        self._cache = SimpleCache(ttl_seconds=60)
        self._query_count = 0
        
    def connect_systems(self, configs: Dict[SystemType, DatabaseConfig]) -> None:
        """Connect to all backend systems."""
        print("🔌 Connecting to backend systems...")
        
        for system_type, config in configs.items():
            self._systems[system_type] = SystemConnection(
                system_type=system_type,
                config=config,
            )
            print(f"   ✅ Connected to {system_type.value}")
        
        print(f"📊 Gateway connected to {len(self._systems)} systems")
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """
        Return unified tools that abstract the underlying systems.
        
        Note: Tools are designed to be system-agnostic.
        The gateway handles routing internally.
        """
        entities = list(self.ENTITY_ROUTING.keys())
        
        return [
            {
                "name": "list_entities",
                "description": (
                    "List all available data entities across all connected systems. "
                    f"Available entities: {', '.join(entities)}"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "system": {
                            "type": "string",
                            "description": "Optional: Filter by system (oracle, sap, salesforce)",
                            "enum": ["oracle", "sap", "salesforce"],
                        },
                    },
                },
            },
            {
                "name": "query_entity",
                "description": (
                    "Query any entity using a unified syntax. "
                    "The gateway automatically routes to the correct system. "
                    f"Entities: {', '.join(entities)}"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity": {
                            "type": "string",
                            "description": "Entity to query (e.g., customers, orders, accounts)",
                            "enum": entities,
                        },
                        "fields": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Fields to retrieve",
                        },
                        "filters": {
                            "type": "object",
                            "description": "Filter conditions as key-value pairs",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 100,
                        },
                    },
                    "required": ["entity"],
                },
            },
            {
                "name": "cross_system_query",
                "description": (
                    "Query data that spans multiple systems. "
                    "For example: 'Find all Salesforce opportunities for Oracle customers'. "
                    "The gateway handles the joins automatically."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "primary_entity": {
                            "type": "string",
                            "description": "Main entity to query",
                        },
                        "join_entity": {
                            "type": "string",
                            "description": "Entity to join with",
                        },
                        "join_key": {
                            "type": "string",
                            "description": "Field to join on (e.g., customer_id)",
                        },
                        "filters": {
                            "type": "object",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 100,
                        },
                    },
                    "required": ["primary_entity", "join_entity", "join_key"],
                },
            },
            {
                "name": "get_entity_schema",
                "description": "Get the schema (fields, types) for an entity.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity": {
                            "type": "string",
                            "enum": entities,
                        },
                    },
                    "required": ["entity"],
                },
            },
            {
                "name": "find_related_entities",
                "description": (
                    "Find entities that are related to a given entity, "
                    "including cross-system relationships."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity": {
                            "type": "string",
                            "enum": entities,
                        },
                    },
                    "required": ["entity"],
                },
            },
            {
                "name": "system_health",
                "description": "Check the health status of all connected backend systems.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
        ]
    
    def _route_entity(self, entity: str) -> Optional[SystemType]:
        """Determine which system handles an entity."""
        return self.ENTITY_ROUTING.get(entity.lower())
    
    async def _execute_on_system(
        self,
        system: SystemType,
        operation: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute an operation on a specific system with circuit breaker."""
        conn = self._systems.get(system)
        if not conn:
            return {"error": f"System {system.value} not connected"}
        
        if not conn.circuit_breaker.can_execute():
            return {"error": f"System {system.value} is temporarily unavailable"}
        
        try:
            # Simulate system call (in production: actual DB/API call)
            await asyncio.sleep(0.01)  # Simulate latency
            conn.circuit_breaker.record_success()
            
            return {
                "status": "success",
                "system": system.value,
                "operation": operation,
                "data": [],
            }
        except Exception as e:
            conn.circuit_breaker.record_failure()
            return {"error": str(e)}
    
    async def list_entities(
        self,
        system: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List all available entities."""
        entities = []
        
        for entity, sys_type in self.ENTITY_ROUTING.items():
            if system and sys_type.value != system:
                continue
            
            entities.append({
                "name": entity,
                "system": sys_type.value,
                "related_entities": self.ENTITY_RELATIONSHIPS.get(entity, []),
            })
        
        return {
            "total_entities": len(entities),
            "entities": entities,
        }
    
    async def query_entity(
        self,
        entity: str,
        fields: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Query an entity - gateway handles routing."""
        self._query_count += 1
        
        # Check cache
        cache_key = f"query:{entity}:{fields}:{filters}:{limit}"
        cached = self._cache.get(cache_key)
        if cached:
            return {**cached, "cached": True}
        
        # Route to correct system
        system = self._route_entity(entity)
        if not system:
            return {"error": f"Unknown entity: {entity}"}
        
        # Execute query
        result = await self._execute_on_system(
            system,
            "query",
            {"entity": entity, "fields": fields, "filters": filters, "limit": limit},
        )
        
        if result.get("status") == "success":
            result["entity"] = entity
            result["routed_to"] = system.value
            self._cache.set(cache_key, result)
        
        return result
    
    async def cross_system_query(
        self,
        primary_entity: str,
        join_entity: str,
        join_key: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """
        Execute a cross-system join.
        
        Strategy:
        1. Query primary entity to get join keys
        2. Use those keys to query join entity
        3. Merge results in gateway
        """
        self._query_count += 2  # Two queries
        
        primary_system = self._route_entity(primary_entity)
        join_system = self._route_entity(join_entity)
        
        if not primary_system:
            return {"error": f"Unknown primary entity: {primary_entity}"}
        if not join_system:
            return {"error": f"Unknown join entity: {join_entity}"}
        
        # Execute queries in parallel
        primary_result, join_result = await asyncio.gather(
            self._execute_on_system(primary_system, "query", {"entity": primary_entity}),
            self._execute_on_system(join_system, "query", {"entity": join_entity}),
        )
        
        return {
            "status": "success",
            "cross_system_join": True,
            "primary": {
                "entity": primary_entity,
                "system": primary_system.value,
                "result": primary_result,
            },
            "joined": {
                "entity": join_entity,
                "system": join_system.value,
                "result": join_result,
            },
            "join_key": join_key,
            "note": "Results merged by gateway",
        }
    
    async def get_entity_schema(self, entity: str) -> Dict[str, Any]:
        """Get schema for an entity."""
        system = self._route_entity(entity)
        if not system:
            return {"error": f"Unknown entity: {entity}"}
        
        # Mock schemas
        schemas = {
            "customers": {"fields": ["id", "name", "email", "created_at"]},
            "orders": {"fields": ["id", "customer_id", "total", "status", "created_at"]},
            "accounts": {"fields": ["Id", "Name", "Industry", "Website"]},
            "opportunities": {"fields": ["Id", "Name", "Amount", "StageName"]},
            "sales_documents": {"fields": ["VBELN", "ERDAT", "KUNNR", "NETWR"]},
        }
        
        return {
            "entity": entity,
            "system": system.value,
            "schema": schemas.get(entity, {"fields": ["id", "name"]}),
            "related": self.ENTITY_RELATIONSHIPS.get(entity, []),
        }
    
    async def find_related_entities(self, entity: str) -> Dict[str, Any]:
        """Find entities related to the given entity."""
        system = self._route_entity(entity)
        if not system:
            return {"error": f"Unknown entity: {entity}"}
        
        related = []
        
        # Same-system relationships
        for other_entity, other_system in self.ENTITY_ROUTING.items():
            if other_entity != entity and other_system == system:
                related.append({
                    "entity": other_entity,
                    "system": other_system.value,
                    "relationship": "same_system",
                })
        
        # Cross-system relationships
        for cross_entity in self.ENTITY_RELATIONSHIPS.get(entity, []):
            cross_system = self._route_entity(cross_entity)
            related.append({
                "entity": cross_entity,
                "system": cross_system.value if cross_system else "unknown",
                "relationship": "cross_system",
            })
        
        return {
            "entity": entity,
            "system": system.value,
            "related_entities": related,
        }
    
    async def system_health(self) -> Dict[str, Any]:
        """Check health of all systems."""
        health = []
        
        for system_type, conn in self._systems.items():
            health.append({
                "system": system_type.value,
                "healthy": conn.healthy,
                "circuit_breaker_state": conn.circuit_breaker.state,
                "failures": conn.circuit_breaker.failures,
            })
        
        all_healthy = all(h["healthy"] for h in health)
        
        return {
            "overall_status": "healthy" if all_healthy else "degraded",
            "systems": health,
            "total_queries_processed": self._query_count,
        }


async def demonstrate():
    """Demonstrate the unified gateway pattern."""
    print("=" * 70)
    print("DEMONSTRATION: Unified Gateway Pattern")
    print("=" * 70)
    
    # Initialize gateway
    gateway = UnifiedGatewayMCPServer()
    gateway.connect_systems(SYSTEM_CONFIGS)
    
    # Show tools
    tools = gateway.list_tools()
    print(f"\n📋 GATEWAY TOOLS ({len(tools)} tools):")
    for tool in tools:
        print(f"   - {tool['name']}: {tool['description'][:60]}...")
    
    # Show entity routing
    print("\n🗺️  ENTITY ROUTING:")
    entities = await gateway.list_entities()
    for e in entities["entities"][:5]:
        print(f"   {e['name']} → {e['system']}")
        if e['related_entities']:
            print(f"      ↳ related: {', '.join(e['related_entities'])}")
    
    # Demonstrate query
    print("\n🔍 SIMPLE QUERY (auto-routed):")
    result = await gateway.query_entity("customers", fields=["id", "name"], limit=10)
    print(f"   Entity: customers → Routed to: {result.get('routed_to', 'N/A')}")
    
    # Demonstrate cross-system query
    print("\n🔗 CROSS-SYSTEM QUERY:")
    cross_result = await gateway.cross_system_query(
        primary_entity="customers",
        join_entity="opportunities",
        join_key="customer_id",
    )
    print(f"   Primary: {cross_result['primary']['entity']} ({cross_result['primary']['system']})")
    print(f"   Joined: {cross_result['joined']['entity']} ({cross_result['joined']['system']})")
    
    # Show health
    print("\n💚 SYSTEM HEALTH:")
    health = await gateway.system_health()
    print(f"   Overall: {health['overall_status']}")
    for sys in health["systems"]:
        status = "✅" if sys["healthy"] else "❌"
        print(f"   {status} {sys['system']}: {sys['circuit_breaker_state']}")
    
    print("\n" + "=" * 70)
    print("VERDICT: ✅ GOOD - For unified access to 2-5 systems")
    print("=" * 70)


# ============================================================================
# 🚨 BAD COP FINAL REVIEW 🚨
# ============================================================================
#
# WHAT THIS CODE DOES RIGHT:
# ✅ Single MCP connection for client
# ✅ Unified query syntax
# ✅ Cross-system query support
# ✅ Circuit breaker for resilience
# ✅ Entity-based routing abstraction
# ✅ Health monitoring
#
# WHAT THIS CODE DOES WRONG:
# ⚠️ Single point of failure
# ⚠️ All traffic through one server
# ⚠️ Cross-system joins are expensive (N+1)
# ⚠️ Cache invalidation is complex
# ⚠️ System-specific features are hidden
#
# PRODUCTION REQUIREMENTS:
# 1. Gateway HA (multiple instances + load balancer)
# 2. Request tracing (distributed tracing)
# 3. Query optimization (smart join ordering)
# 4. Connection pooling per backend
# 5. Async query queue for large cross-system queries
# 6. Schema sync mechanism
#
# PERFORMANCE CONSIDERATIONS:
# - Cross-system queries: O(n) where n = number of systems
# - Caching helps but invalidation is tricky
# - Consider materialized views for common cross-system queries
#
# ============================================================================


if __name__ == "__main__":
    asyncio.run(demonstrate())
