"""
Scenario 8: Federated Pattern - Distributed MCP with Central Orchestration

A hybrid architecture combining the best of separate servers and unified gateway:
- Each system has its own MCP server (isolation)
- A federated coordinator handles routing and cross-system queries
- Service mesh for discovery and communication

=============================================================================
✅ GOOD COP REVIEW - BENEFITS
=============================================================================
+ No single point of failure: Systems remain accessible if coordinator fails
+ Scalable: Add new systems without changing existing ones
+ Flexible routing: Smart load balancing and failover
+ Cross-system support: Coordinator handles complex queries
+ Technology diversity: Each system optimized independently
+ Gradual adoption: Start with one system, add more over time
=============================================================================

=============================================================================
🚨 BAD COP REVIEW - REMAINING ISSUES
=============================================================================
⚠️ ISSUE 1: OPERATIONAL COMPLEXITY
- More services to deploy and monitor
- Distributed system debugging is hard
- Network partitions cause issues

⚠️ ISSUE 2: CONSISTENCY CHALLENGES
- Schema changes need coordination
- Cache coherence across systems
- Eventual consistency for cross-system data

⚠️ ISSUE 3: LATENCY
- Multiple network hops for cross-system queries
- Service discovery overhead
- Coordinator adds latency

⚠️ ISSUE 4: COST
- More infrastructure (VMs, networking)
- Monitoring stack for each component
- Higher operational overhead

VERDICT: ✅ EXCELLENT - Best for large-scale enterprise (5+ systems, 1000+ tables)
=============================================================================
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import time
import random
from config import SystemType, DatabaseConfig, SYSTEM_CONFIGS
from utils import CircuitBreaker, SimpleCache


class ServiceStatus(Enum):
    """Service health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ServiceInfo:
    """Information about a registered service."""
    service_id: str
    system_type: SystemType
    host: str
    port: int
    status: ServiceStatus = ServiceStatus.HEALTHY
    last_heartbeat: float = field(default_factory=time.time)
    capabilities: Set[str] = field(default_factory=set)
    weight: int = 100  # For load balancing


class ServiceRegistry:
    """
    Service Registry: Keeps track of all MCP servers in the federation.
    
    In production, use:
    - Consul
    - etcd
    - Kubernetes service discovery
    - AWS Cloud Map
    """
    
    def __init__(self):
        self._services: Dict[str, ServiceInfo] = {}
        self._by_system: Dict[SystemType, List[str]] = {}
    
    def register(self, service: ServiceInfo) -> None:
        """Register a service."""
        self._services[service.service_id] = service
        
        if service.system_type not in self._by_system:
            self._by_system[service.system_type] = []
        self._by_system[service.system_type].append(service.service_id)
        
        print(f"   📝 Registered: {service.service_id} ({service.system_type.value})")
    
    def deregister(self, service_id: str) -> None:
        """Deregister a service."""
        if service_id in self._services:
            service = self._services[service_id]
            self._by_system[service.system_type].remove(service_id)
            del self._services[service_id]
    
    def get_service(self, service_id: str) -> Optional[ServiceInfo]:
        """Get a service by ID."""
        return self._services.get(service_id)
    
    def get_services_for_system(self, system_type: SystemType) -> List[ServiceInfo]:
        """Get all healthy services for a system type."""
        service_ids = self._by_system.get(system_type, [])
        return [
            self._services[sid] 
            for sid in service_ids 
            if self._services[sid].status == ServiceStatus.HEALTHY
        ]
    
    def select_service(self, system_type: SystemType) -> Optional[ServiceInfo]:
        """Select a service using weighted round-robin."""
        services = self.get_services_for_system(system_type)
        if not services:
            return None
        
        # Weighted random selection
        total_weight = sum(s.weight for s in services)
        r = random.randint(1, total_weight)
        cumulative = 0
        for service in services:
            cumulative += service.weight
            if r <= cumulative:
                return service
        
        return services[0]
    
    def update_heartbeat(self, service_id: str) -> None:
        """Update service heartbeat."""
        if service_id in self._services:
            self._services[service_id].last_heartbeat = time.time()
    
    def check_health(self, timeout_seconds: float = 30.0) -> Dict[str, ServiceStatus]:
        """Check health of all services."""
        now = time.time()
        statuses = {}
        
        for service_id, service in self._services.items():
            age = now - service.last_heartbeat
            if age > timeout_seconds:
                service.status = ServiceStatus.UNHEALTHY
            elif age > timeout_seconds / 2:
                service.status = ServiceStatus.DEGRADED
            else:
                service.status = ServiceStatus.HEALTHY
            statuses[service_id] = service.status
        
        return statuses


class SystemMCPNode(ABC):
    """
    Base class for system-specific MCP nodes in the federation.
    
    Each node:
    - Handles one system type
    - Registers with the service registry
    - Reports health via heartbeats
    - Implements system-specific tools
    """
    
    def __init__(
        self,
        service_id: str,
        system_type: SystemType,
        registry: ServiceRegistry,
        config: DatabaseConfig,
    ):
        self.service_id = service_id
        self.system_type = system_type
        self.registry = registry
        self.config = config
        self.circuit_breaker = CircuitBreaker()
        self._cache = SimpleCache(ttl_seconds=60)
    
    def start(self) -> None:
        """Start the node and register with the federation."""
        service_info = ServiceInfo(
            service_id=self.service_id,
            system_type=self.system_type,
            host="localhost",
            port=8080 + hash(self.service_id) % 1000,
            capabilities=self.get_capabilities(),
        )
        self.registry.register(service_info)
    
    def stop(self) -> None:
        """Stop the node and deregister."""
        self.registry.deregister(self.service_id)
    
    def heartbeat(self) -> None:
        """Send heartbeat to registry."""
        self.registry.update_heartbeat(self.service_id)
    
    @abstractmethod
    def get_capabilities(self) -> Set[str]:
        """Return capabilities this node supports."""
        pass
    
    @abstractmethod
    def list_tools(self) -> List[Dict[str, Any]]:
        """List tools this node provides."""
        pass
    
    @abstractmethod
    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool."""
        pass


class OracleNode(SystemMCPNode):
    """Oracle-specific MCP node."""
    
    def get_capabilities(self) -> Set[str]:
        return {"sql", "plsql", "procedures", "materialized_views"}
    
    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "oracle_query",
                "description": "Execute SQL query on Oracle",
                "system": "oracle",
            },
            {
                "name": "oracle_execute_plsql",
                "description": "Execute PL/SQL block",
                "system": "oracle",
            },
        ]
    
    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if not self.circuit_breaker.can_execute():
            return {"error": "Service temporarily unavailable"}
        
        try:
            await asyncio.sleep(0.01)  # Simulate work
            self.circuit_breaker.record_success()
            return {"status": "success", "node": self.service_id, "data": []}
        except Exception as e:
            self.circuit_breaker.record_failure()
            return {"error": str(e)}


class SAPNode(SystemMCPNode):
    """SAP-specific MCP node."""
    
    def get_capabilities(self) -> Set[str]:
        return {"bapi", "rfc", "idoc", "odata"}
    
    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "sap_query",
                "description": "Query SAP tables",
                "system": "sap",
            },
            {
                "name": "sap_call_bapi",
                "description": "Call SAP BAPI",
                "system": "sap",
            },
        ]
    
    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if not self.circuit_breaker.can_execute():
            return {"error": "Service temporarily unavailable"}
        
        try:
            await asyncio.sleep(0.01)
            self.circuit_breaker.record_success()
            return {"status": "success", "node": self.service_id, "data": []}
        except Exception as e:
            self.circuit_breaker.record_failure()
            return {"error": str(e)}


class SalesforceNode(SystemMCPNode):
    """Salesforce-specific MCP node."""
    
    def get_capabilities(self) -> Set[str]:
        return {"soql", "rest_api", "bulk_api", "metadata_api"}
    
    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "sf_soql_query",
                "description": "Execute SOQL query",
                "system": "salesforce",
            },
            {
                "name": "sf_crud",
                "description": "Create/Read/Update/Delete records",
                "system": "salesforce",
            },
        ]
    
    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if not self.circuit_breaker.can_execute():
            return {"error": "Service temporarily unavailable"}
        
        try:
            await asyncio.sleep(0.01)
            self.circuit_breaker.record_success()
            return {"status": "success", "node": self.service_id, "data": []}
        except Exception as e:
            self.circuit_breaker.record_failure()
            return {"error": str(e)}


class FederatedCoordinator:
    """
    Federated Coordinator: Orchestrates the MCP federation.
    
    Architecture:
    
    ┌─────────────────────────────────────────────────────────────────┐
    │                       MCP Client                                 │
    └─────────────────────────────┬───────────────────────────────────┘
                                  │
    ┌─────────────────────────────▼───────────────────────────────────┐
    │                  FEDERATED COORDINATOR                           │
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
    │  │   Router     │  │    Query     │  │   Cross-System       │   │
    │  │              │  │   Planner    │  │   Join Engine        │   │
    │  └──────┬───────┘  └──────────────┘  └──────────────────────┘   │
    │         │                                                        │
    │  ┌──────▼──────────────────────────────────────────────────┐    │
    │  │                  SERVICE REGISTRY                        │    │
    │  │  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐         │    │
    │  │  │Oracle-1│  │Oracle-2│  │ SAP-1  │  │  SF-1  │  ...    │    │
    │  │  └────────┘  └────────┘  └────────┘  └────────┘         │    │
    │  └─────────────────────────────────────────────────────────┘    │
    └─────────────────────────────────────────────────────────────────┘
                                  │
            ┌─────────────────────┼─────────────────────┐
            ▼                     ▼                     ▼
    ┌───────────────┐    ┌───────────────┐    ┌───────────────┐
    │  Oracle Node  │    │   SAP Node    │    │   SF Node     │
    │  (Primary)    │    │               │    │               │
    └───────────────┘    └───────────────┘    └───────────────┘
    ┌───────────────┐
    │  Oracle Node  │
    │  (Replica)    │
    └───────────────┘
    
    Key Features:
    - Service discovery via registry
    - Load balancing across replicas
    - Automatic failover
    - Cross-system query coordination
    - Centralized tool aggregation
    """
    
    def __init__(self):
        self.registry = ServiceRegistry()
        self._nodes: Dict[str, SystemMCPNode] = {}
        self._cache = SimpleCache(ttl_seconds=30)
    
    def register_node(self, node: SystemMCPNode) -> None:
        """Register a node with the federation."""
        self._nodes[node.service_id] = node
        node.start()
    
    def deregister_node(self, service_id: str) -> None:
        """Deregister a node."""
        if service_id in self._nodes:
            self._nodes[service_id].stop()
            del self._nodes[service_id]
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """
        Aggregate tools from all nodes plus coordinator tools.
        
        Returns:
        - Per-system tools (namespaced)
        - Coordinator tools (cross-system operations)
        """
        tools = []
        
        # Add coordinator tools
        tools.extend([
            {
                "name": "federated_query",
                "description": (
                    "Execute a query that may span multiple systems. "
                    "The coordinator automatically routes to the appropriate nodes."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "system": {
                            "type": "string",
                            "description": "Target system (oracle, sap, salesforce) or 'auto' for automatic routing",
                            "enum": ["oracle", "sap", "salesforce", "auto"],
                        },
                        "query": {
                            "type": "string",
                            "description": "Query in system-native syntax",
                        },
                        "prefer_replica": {
                            "type": "boolean",
                            "description": "Prefer replica nodes for read queries",
                            "default": True,
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "federated_cross_system",
                "description": (
                    "Execute a cross-system operation. "
                    "Supports joining data from Oracle, SAP, and Salesforce."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "operations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "system": {"type": "string"},
                                    "query": {"type": "string"},
                                    "alias": {"type": "string"},
                                },
                            },
                            "description": "List of queries to execute and join",
                        },
                        "join_config": {
                            "type": "object",
                            "description": "How to join the results",
                        },
                    },
                    "required": ["operations"],
                },
            },
            {
                "name": "federated_discover",
                "description": "Discover available systems, nodes, and capabilities in the federation.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "system": {
                            "type": "string",
                            "description": "Optional: Filter by system type",
                        },
                    },
                },
            },
            {
                "name": "federated_health",
                "description": "Get health status of all nodes in the federation.",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ])
        
        # Aggregate tools from all node types (deduplicated)
        seen_tools = set()
        for node in self._nodes.values():
            for tool in node.list_tools():
                tool_key = f"{tool['system']}_{tool['name']}"
                if tool_key not in seen_tools:
                    tools.append({
                        **tool,
                        "name": f"{tool['system']}_{tool['name']}",  # Namespace tools
                        "federated": True,
                    })
                    seen_tools.add(tool_key)
        
        return tools
    
    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool, routing to appropriate nodes."""
        
        # Coordinator tools
        if tool_name == "federated_query":
            return await self._federated_query(arguments)
        if tool_name == "federated_cross_system":
            return await self._federated_cross_system(arguments)
        if tool_name == "federated_discover":
            return await self._federated_discover(arguments)
        if tool_name == "federated_health":
            return await self._federated_health()
        
        # Route to system-specific node
        for system_prefix in ["oracle", "sap", "salesforce"]:
            if tool_name.startswith(f"{system_prefix}_"):
                return await self._route_to_system(
                    SystemType(system_prefix),
                    tool_name.replace(f"{system_prefix}_", ""),
                    arguments,
                )
        
        return {"error": f"Unknown tool: {tool_name}"}
    
    async def _route_to_system(
        self,
        system_type: SystemType,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Any:
        """Route a request to a specific system."""
        service = self.registry.select_service(system_type)
        if not service:
            return {"error": f"No healthy {system_type.value} nodes available"}
        
        node = self._nodes.get(service.service_id)
        if not node:
            return {"error": f"Node {service.service_id} not found"}
        
        result = await node.execute(tool_name, arguments)
        return {
            **result,
            "routed_to": service.service_id,
            "system": system_type.value,
        }
    
    async def _federated_query(self, arguments: Dict[str, Any]) -> Any:
        """Execute a federated query."""
        system = arguments.get("system", "auto")
        query = arguments.get("query", "")
        
        if system == "auto":
            # Simple auto-detection based on query syntax
            if "SELECT" in query.upper() and "FROM" in query.upper():
                system = "oracle"  # Default to Oracle for SQL
            elif query.upper().startswith("SELECT"):
                system = "salesforce"  # SOQL
            else:
                system = "oracle"
        
        system_type = SystemType(system)
        return await self._route_to_system(system_type, "query", {"query": query})
    
    async def _federated_cross_system(self, arguments: Dict[str, Any]) -> Any:
        """Execute cross-system operations in parallel."""
        operations = arguments.get("operations", [])
        
        # Execute all operations in parallel
        tasks = []
        for op in operations:
            system_type = SystemType(op["system"])
            tasks.append(self._route_to_system(
                system_type,
                "query",
                {"query": op["query"]},
            ))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            "status": "success",
            "operations_count": len(operations),
            "results": [
                {
                    "alias": op.get("alias", f"result_{i}"),
                    "system": op["system"],
                    "result": r if not isinstance(r, Exception) else {"error": str(r)},
                }
                for i, (op, r) in enumerate(zip(operations, results))
            ],
            "note": "Results can be joined in application layer",
        }
    
    async def _federated_discover(self, arguments: Dict[str, Any]) -> Any:
        """Discover federation topology."""
        system_filter = arguments.get("system")
        
        discovery = {
            "systems": [],
            "total_nodes": 0,
            "healthy_nodes": 0,
        }
        
        for system_type in SystemType:
            if system_filter and system_type.value != system_filter:
                continue
            
            services = self.registry.get_services_for_system(system_type)
            all_services = self.registry._by_system.get(system_type, [])
            
            system_info = {
                "system": system_type.value,
                "total_nodes": len(all_services),
                "healthy_nodes": len(services),
                "capabilities": set(),
                "nodes": [],
            }
            
            for service_id in all_services:
                service = self.registry.get_service(service_id)
                if service:
                    system_info["capabilities"].update(service.capabilities)
                    system_info["nodes"].append({
                        "id": service_id,
                        "status": service.status.value,
                        "weight": service.weight,
                    })
            
            system_info["capabilities"] = list(system_info["capabilities"])
            discovery["systems"].append(system_info)
            discovery["total_nodes"] += len(all_services)
            discovery["healthy_nodes"] += len(services)
        
        return discovery
    
    async def _federated_health(self) -> Any:
        """Get federation health."""
        statuses = self.registry.check_health()
        
        healthy = sum(1 for s in statuses.values() if s == ServiceStatus.HEALTHY)
        degraded = sum(1 for s in statuses.values() if s == ServiceStatus.DEGRADED)
        unhealthy = sum(1 for s in statuses.values() if s == ServiceStatus.UNHEALTHY)
        
        if unhealthy > 0:
            overall = "critical"
        elif degraded > 0:
            overall = "degraded"
        else:
            overall = "healthy"
        
        return {
            "overall_status": overall,
            "summary": {
                "healthy": healthy,
                "degraded": degraded,
                "unhealthy": unhealthy,
                "total": len(statuses),
            },
            "nodes": {
                service_id: status.value
                for service_id, status in statuses.items()
            },
        }


async def demonstrate():
    """Demonstrate the federated pattern."""
    print("=" * 70)
    print("DEMONSTRATION: Federated MCP Pattern (RECOMMENDED FOR ENTERPRISE)")
    print("=" * 70)
    
    # Create coordinator
    coordinator = FederatedCoordinator()
    
    # Create and register nodes
    print("\n🏗️  SETTING UP FEDERATION:")
    
    # Oracle nodes (primary + replica)
    oracle_primary = OracleNode(
        "oracle-primary",
        SystemType.ORACLE,
        coordinator.registry,
        SYSTEM_CONFIGS[SystemType.ORACLE],
    )
    oracle_replica = OracleNode(
        "oracle-replica",
        SystemType.ORACLE,
        coordinator.registry,
        SYSTEM_CONFIGS[SystemType.ORACLE],
    )
    
    # SAP node
    sap_node = SAPNode(
        "sap-primary",
        SystemType.SAP,
        coordinator.registry,
        SYSTEM_CONFIGS[SystemType.SAP],
    )
    
    # Salesforce node
    sf_node = SalesforceNode(
        "sf-primary",
        SystemType.SALESFORCE,
        coordinator.registry,
        SYSTEM_CONFIGS[SystemType.SALESFORCE],
    )
    
    # Register all nodes
    for node in [oracle_primary, oracle_replica, sap_node, sf_node]:
        coordinator.register_node(node)
    
    # Show federation topology
    print("\n🌐 FEDERATION TOPOLOGY:")
    discovery = await coordinator._federated_discover({})
    for sys in discovery["systems"]:
        print(f"   {sys['system'].upper()}: {sys['healthy_nodes']}/{sys['total_nodes']} nodes")
        for node in sys["nodes"]:
            status = "✅" if node["status"] == "healthy" else "⚠️"
            print(f"      {status} {node['id']} (weight: {node['weight']})")
    
    # Show tools
    tools = coordinator.list_tools()
    print(f"\n📋 FEDERATED TOOLS ({len(tools)} tools):")
    coordinator_tools = [t for t in tools if t["name"].startswith("federated_")]
    system_tools = [t for t in tools if not t["name"].startswith("federated_")]
    
    print("   Coordinator tools:")
    for tool in coordinator_tools:
        print(f"      - {tool['name']}")
    
    print("   System tools (namespaced):")
    for tool in system_tools[:6]:
        print(f"      - {tool['name']} ({tool.get('system', 'N/A')})")
    
    # Demonstrate routing
    print("\n🔀 LOAD BALANCING DEMONSTRATION:")
    routes = {}
    for _ in range(10):
        result = await coordinator.execute_tool("oracle_query", {"query": "SELECT 1"})
        node = result.get("routed_to", "unknown")
        routes[node] = routes.get(node, 0) + 1
    
    for node, count in routes.items():
        print(f"   {node}: {count} requests")
    
    # Demonstrate cross-system query
    print("\n🔗 CROSS-SYSTEM QUERY:")
    cross_result = await coordinator.execute_tool("federated_cross_system", {
        "operations": [
            {"system": "oracle", "query": "SELECT * FROM customers", "alias": "customers"},
            {"system": "salesforce", "query": "SELECT Id, Name FROM Account", "alias": "accounts"},
        ],
    })
    print(f"   Operations executed: {cross_result['operations_count']}")
    for r in cross_result["results"]:
        print(f"   - {r['alias']} ({r['system']}): {r['result'].get('status', 'error')}")
    
    # Health check
    print("\n💚 FEDERATION HEALTH:")
    health = await coordinator._federated_health()
    print(f"   Overall: {health['overall_status']}")
    print(f"   Healthy: {health['summary']['healthy']}/{health['summary']['total']}")
    
    print("\n" + "=" * 70)
    print("VERDICT: ✅ EXCELLENT - Best for large-scale enterprise deployments")
    print("=" * 70)


# ============================================================================
# 🚨 BAD COP FINAL REVIEW 🚨
# ============================================================================
#
# WHAT THIS CODE DOES RIGHT:
# ✅ No single point of failure (nodes can fail independently)
# ✅ Horizontal scaling (add more nodes per system)
# ✅ Load balancing across replicas
# ✅ Service discovery and health monitoring
# ✅ Namespaced tools prevent conflicts
# ✅ Cross-system query support
# ✅ Gradual adoption path
#
# WHAT THIS CODE DOES WRONG:
# ⚠️ Mock implementations (no real DB connections)
# ⚠️ No persistent registry (Consul/etcd needed)
# ⚠️ No distributed tracing
# ⚠️ No metrics collection
# ⚠️ Simple load balancing (needs smarter algorithms)
# ⚠️ No authentication between nodes
#
# PRODUCTION REQUIREMENTS:
# 1. Service mesh (Istio, Linkerd) for secure communication
# 2. Distributed registry (Consul, etcd, ZooKeeper)
# 3. Distributed tracing (Jaeger, Zipkin)
# 4. Metrics (Prometheus) and logging (ELK)
# 5. mTLS between all components
# 6. Rate limiting per node
# 7. Circuit breaker configuration per system
# 8. Graceful degradation strategies
#
# OPERATIONAL COMPLEXITY:
# - Deploy: 1 coordinator + N system nodes + registry + monitoring
# - Monitor: Health, latency, error rates per node
# - Scale: Add nodes to registry, coordinator auto-discovers
# - Upgrade: Rolling updates per system type
#
# COST ESTIMATE (hypothetical):
# - 4 nodes × $200/month = $800/month
# - Registry (Consul Cloud) = $50/month
# - Monitoring (Datadog) = $100/month
# - Total: ~$1000/month vs $50/month for single gateway
#
# WHEN TO USE THIS PATTERN:
# - 5+ systems
# - High availability requirements
# - Multiple teams managing different systems
# - Need independent scaling per system
# - Cross-system queries are common
#
# ============================================================================


if __name__ == "__main__":
    asyncio.run(demonstrate())
