"""
Shared configuration for MCP scenarios.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class SystemType(Enum):
    """Supported backend systems."""
    ORACLE = "oracle"
    SAP = "sap"
    SALESFORCE = "salesforce"
    POSTGRES = "postgres"
    MYSQL = "mysql"


@dataclass
class DatabaseConfig:
    """Database connection configuration."""
    host: str
    port: int
    database: str
    username: str
    password: str
    system_type: SystemType
    pool_size: int = 10
    timeout_seconds: int = 30


@dataclass
class TableMetadata:
    """Metadata for a database table."""
    name: str
    schema: str
    domain: str
    columns: List[Dict[str, str]]
    row_count: int
    description: str
    primary_key: List[str]
    foreign_keys: List[Dict[str, str]] = field(default_factory=list)
    indexes: List[str] = field(default_factory=list)
    last_updated: Optional[str] = None


@dataclass
class MCPServerConfig:
    """MCP server configuration."""
    name: str
    host: str = "localhost"
    port: int = 8080
    max_tools_per_response: int = 100
    enable_caching: bool = True
    cache_ttl_seconds: int = 300
    enable_search: bool = True
    log_level: str = "INFO"


# Sample domain mappings for 1000 tables scenario
DOMAIN_MAPPINGS = {
    "sales": ["orders", "customers", "products", "invoices", "quotes", "opportunities"],
    "hr": ["employees", "departments", "payroll", "benefits", "timesheets", "reviews"],
    "finance": ["accounts", "transactions", "budgets", "reports", "audits", "taxes"],
    "inventory": ["items", "warehouses", "shipments", "suppliers", "stock", "transfers"],
    "manufacturing": ["work_orders", "bom", "routing", "quality", "equipment", "maintenance"],
    "crm": ["contacts", "leads", "campaigns", "activities", "cases", "contracts"],
}


# Sample system configurations for multi-system scenario
SYSTEM_CONFIGS = {
    SystemType.ORACLE: DatabaseConfig(
        host="oracle-db.internal",
        port=1521,
        database="PRODDB",
        username="app_user",
        password="***",
        system_type=SystemType.ORACLE,
    ),
    SystemType.SAP: DatabaseConfig(
        host="sap-hana.internal",
        port=30015,
        database="SAPDB",
        username="sap_user",
        password="***",
        system_type=SystemType.SAP,
    ),
    SystemType.SALESFORCE: DatabaseConfig(
        host="salesforce-api.internal",
        port=443,
        database="SFDC",
        username="sf_user",
        password="***",
        system_type=SystemType.SALESFORCE,
    ),
}


def generate_sample_tables(count: int = 1000) -> List[TableMetadata]:
    """Generate sample table metadata for testing."""
    tables = []
    domains = list(DOMAIN_MAPPINGS.keys())
    
    for i in range(count):
        domain = domains[i % len(domains)]
        base_names = DOMAIN_MAPPINGS[domain]
        base_name = base_names[i % len(base_names)]
        
        tables.append(TableMetadata(
            name=f"{base_name}_{i:04d}",
            schema=f"SCHEMA_{domain.upper()}",
            domain=domain,
            columns=[
                {"name": "id", "type": "INTEGER", "nullable": False},
                {"name": "created_at", "type": "TIMESTAMP", "nullable": False},
                {"name": "updated_at", "type": "TIMESTAMP", "nullable": True},
                {"name": f"{base_name}_name", "type": "VARCHAR(255)", "nullable": False},
                {"name": "status", "type": "VARCHAR(50)", "nullable": True},
            ],
            row_count=(i + 1) * 1000,
            description=f"Table for {domain} - {base_name} data (partition {i})",
            primary_key=["id"],
        ))
    
    return tables
