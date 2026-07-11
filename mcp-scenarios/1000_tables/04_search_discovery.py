"""
Scenario 4: Search/Discovery Pattern - Semantic Search for Tables

Use vector embeddings and semantic search to find relevant tables
without requiring exact keyword matches.

=============================================================================
✅ GOOD COP REVIEW - BENEFITS
=============================================================================
+ Semantic understanding: "revenue" finds "sales_totals" table
+ Typo tolerance: Fuzzy matching handles user errors
+ No domain knowledge required: User describes what they need
+ Scales to any number of tables: Vector search is O(log n)
+ Relationship discovery: Finds related tables automatically
=============================================================================

=============================================================================
🚨 BAD COP REVIEW - REMAINING ISSUES
=============================================================================
⚠️ ISSUE 1: EMBEDDING MODEL DEPENDENCY
- Requires embedding model (OpenAI, Cohere, local)
- Additional API costs per search
- Latency for embedding generation

⚠️ ISSUE 2: SEMANTIC MISMATCH
- Business jargon may not match technical schemas
- "ARR" might not find "annual_recurring_revenue"
- Requires good metadata/descriptions

⚠️ ISSUE 3: COLD START PROBLEM
- Need to embed all tables upfront
- Re-embed on schema changes
- Storage for embedding vectors

⚠️ ISSUE 4: OVER-RETRIEVAL
- May return too many "relevant" tables
- User still needs to filter results
- Confidence scoring is imperfect

VERDICT: ✅ EXCELLENT - Best for large-scale discovery (500+ tables)
=============================================================================
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import math
import hashlib
from config import generate_sample_tables, TableMetadata
from utils import MCPTool, SimpleCache


@dataclass
class TableEmbedding:
    """Embedded representation of a table."""
    table_name: str
    embedding: List[float]
    metadata: Dict[str, Any] = field(default_factory=dict)


class MockEmbeddingService:
    """
    Mock embedding service for demonstration.
    In production, use OpenAI, Cohere, or local models.
    """
    
    def __init__(self, dimension: int = 128):
        self.dimension = dimension
        self._cache: Dict[str, List[float]] = {}
    
    def embed(self, text: str) -> List[float]:
        """Generate a mock embedding (deterministic for same text)."""
        # In production: return openai.embeddings.create(...)
        if text in self._cache:
            return self._cache[text]
        
        # Create deterministic pseudo-embedding based on text
        seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
        embedding = []
        for i in range(self.dimension):
            embedding.append(math.sin(seed * (i + 1) * 0.1))
        
        # Normalize
        magnitude = math.sqrt(sum(x * x for x in embedding))
        embedding = [x / magnitude for x in embedding]
        
        self._cache[text] = embedding
        return embedding
    
    def similarity(self, a: List[float], b: List[float]) -> float:
        """Cosine similarity between two embeddings."""
        dot_product = sum(x * y for x, y in zip(a, b))
        return dot_product  # Already normalized


class SemanticSearchMCPServer:
    """
    Search/Discovery Pattern: Use semantic search to find tables.
    
    Architecture:
    1. Embed all table descriptions + column names at startup
    2. User query is embedded and compared to all tables
    3. Return top-k most similar tables
    4. User can then activate/query those tables
    
    This pattern is ideal for:
    - Large number of tables (500+)
    - Users who don't know exact table names
    - Natural language queries
    """
    
    def __init__(self, embedding_dim: int = 128, top_k: int = 10):
        self._embedding_service = MockEmbeddingService(dimension=embedding_dim)
        self._table_embeddings: Dict[str, TableEmbedding] = {}
        self._tables: Dict[str, TableMetadata] = {}
        self._top_k = top_k
        self._cache = SimpleCache(ttl_seconds=300)
    
    def _create_table_text(self, table: TableMetadata) -> str:
        """Create searchable text representation of a table."""
        column_text = ", ".join([
            f"{c['name']} ({c['type']})" 
            for c in table.columns
        ])
        
        return f"""
        Table: {table.name}
        Schema: {table.schema}
        Domain: {table.domain}
        Description: {table.description}
        Columns: {column_text}
        Related concepts: {table.domain} data, {table.name.replace('_', ' ')}
        """
    
    def initialize(self, tables: List[TableMetadata]) -> None:
        """Embed all tables for semantic search."""
        print(f"🔮 Creating embeddings for {len(tables)} tables...")
        
        for i, table in enumerate(tables):
            # Store table metadata
            self._tables[table.name] = table
            
            # Create searchable text
            text = self._create_table_text(table)
            
            # Generate embedding
            embedding = self._embedding_service.embed(text)
            
            self._table_embeddings[table.name] = TableEmbedding(
                table_name=table.name,
                embedding=embedding,
                metadata={
                    "schema": table.schema,
                    "domain": table.domain,
                    "row_count": table.row_count,
                },
            )
            
            if (i + 1) % 250 == 0:
                print(f"   Embedded {i + 1}/{len(tables)} tables...")
        
        print(f"✅ Embedded {len(self._table_embeddings)} tables")
    
    def _create_tools(self) -> List[MCPTool]:
        """Create search and query tools."""
        return [
            MCPTool(
                name="search_tables",
                description=(
                    "Search for database tables using natural language. "
                    "Describe what data you need, and this will find the most relevant tables. "
                    "Examples: 'customer purchase history', 'employee salaries', 'inventory levels'"
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language description of the data you need",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of tables to return",
                            "default": 10,
                        },
                        "min_similarity": {
                            "type": "number",
                            "description": "Minimum similarity score (0-1)",
                            "default": 0.3,
                        },
                    },
                    "required": ["query"],
                },
            ),
            MCPTool(
                name="get_table_schema",
                description="Get detailed schema information for a specific table.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "table_name": {
                            "type": "string",
                            "description": "Name of the table to get schema for",
                        },
                    },
                    "required": ["table_name"],
                },
            ),
            MCPTool(
                name="find_related_tables",
                description="Find tables that are related to a given table (by schema similarity).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "table_name": {
                            "type": "string",
                            "description": "Name of the reference table",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum related tables to return",
                            "default": 5,
                        },
                    },
                    "required": ["table_name"],
                },
            ),
            MCPTool(
                name="query_table",
                description="Execute a query on a table. Use search_tables first to find the right table.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "table_name": {
                            "type": "string",
                            "description": "Name of the table to query",
                        },
                        "columns": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Columns to select",
                        },
                        "filters": {
                            "type": "object",
                            "description": "Filter conditions",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 100,
                        },
                    },
                    "required": ["table_name"],
                },
            ),
        ]
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """Return search and query tools."""
        return [tool.to_dict() for tool in self._create_tools()]
    
    async def search_tables(
        self,
        query: str,
        limit: int = 10,
        min_similarity: float = 0.3,
    ) -> Dict[str, Any]:
        """Search for tables using semantic similarity."""
        # Check cache
        cache_key = f"search:{query}:{limit}:{min_similarity}"
        cached = self._cache.get(cache_key)
        if cached:
            return cached
        
        # Embed the query
        query_embedding = self._embedding_service.embed(query)
        
        # Calculate similarity with all tables
        similarities: List[Tuple[str, float]] = []
        for table_name, table_embed in self._table_embeddings.items():
            similarity = self._embedding_service.similarity(
                query_embedding,
                table_embed.embedding,
            )
            if similarity >= min_similarity:
                similarities.append((table_name, similarity))
        
        # Sort by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)
        top_results = similarities[:limit]
        
        # Build response
        results = []
        for table_name, similarity in top_results:
            table = self._tables[table_name]
            results.append({
                "table_name": table_name,
                "schema": table.schema,
                "domain": table.domain,
                "description": table.description,
                "columns": [c["name"] for c in table.columns],
                "row_count": table.row_count,
                "similarity_score": round(similarity, 3),
            })
        
        response = {
            "query": query,
            "results_count": len(results),
            "tables": results,
        }
        
        self._cache.set(cache_key, response)
        return response
    
    async def get_table_schema(self, table_name: str) -> Dict[str, Any]:
        """Get detailed schema for a table."""
        if table_name not in self._tables:
            return {"error": f"Table '{table_name}' not found"}
        
        table = self._tables[table_name]
        return {
            "table_name": table.name,
            "schema": table.schema,
            "domain": table.domain,
            "description": table.description,
            "columns": table.columns,
            "primary_key": table.primary_key,
            "foreign_keys": table.foreign_keys,
            "indexes": table.indexes,
            "row_count": table.row_count,
        }
    
    async def find_related_tables(
        self,
        table_name: str,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Find tables related to a given table."""
        if table_name not in self._table_embeddings:
            return {"error": f"Table '{table_name}' not found"}
        
        reference_embedding = self._table_embeddings[table_name].embedding
        
        # Calculate similarity with all other tables
        similarities: List[Tuple[str, float]] = []
        for other_name, table_embed in self._table_embeddings.items():
            if other_name == table_name:
                continue
            similarity = self._embedding_service.similarity(
                reference_embedding,
                table_embed.embedding,
            )
            similarities.append((other_name, similarity))
        
        # Sort by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)
        top_results = similarities[:limit]
        
        return {
            "reference_table": table_name,
            "related_tables": [
                {
                    "table_name": name,
                    "similarity_score": round(sim, 3),
                    "domain": self._tables[name].domain,
                }
                for name, sim in top_results
            ],
        }
    
    async def query_table(
        self,
        table_name: str,
        columns: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Query a table."""
        if table_name not in self._tables:
            return {"error": f"Table '{table_name}' not found"}
        
        table = self._tables[table_name]
        
        return {
            "success": True,
            "table": table_name,
            "columns_selected": columns or ["*"],
            "filters_applied": filters or {},
            "limit": limit,
            "data": [],  # Would contain actual results
            "row_count": table.row_count,
        }
    
    def calculate_token_overhead(self) -> Dict[str, int]:
        """Calculate token overhead."""
        import json
        
        tools = self.list_tools()
        tools_json = json.dumps(tools)
        estimated_tokens = len(tools_json) // 4
        
        return {
            "total_tables": len(self._tables),
            "total_tools": len(tools),
            "json_bytes": len(tools_json),
            "estimated_tokens": estimated_tokens,
            "embedding_dimension": self._embedding_service.dimension,
            "vs_naive_tokens": 300000,
            "savings_percent": round((1 - estimated_tokens / 300000) * 100, 1),
        }


async def demonstrate():
    """Demonstrate the semantic search pattern."""
    print("=" * 70)
    print("DEMONSTRATION: Semantic Search Pattern")
    print("=" * 70)
    
    # Generate 1000 tables
    tables = generate_sample_tables(1000)
    
    # Initialize server
    server = SemanticSearchMCPServer(embedding_dim=128, top_k=10)
    server.initialize(tables)
    
    # Show stats
    print("\n📊 STATISTICS:")
    stats = server.calculate_token_overhead()
    print(f"   Tables indexed: {stats['total_tables']}")
    print(f"   Tools exposed: {stats['total_tools']}")
    print(f"   Estimated tokens: {stats['estimated_tokens']:,}")
    print(f"   Savings vs naive: {stats['savings_percent']}%")
    
    # Demonstrate semantic search
    print("\n🔍 SEMANTIC SEARCH DEMONSTRATIONS:")
    
    queries = [
        "customer purchase history",
        "employee salary information",
        "warehouse stock levels",
    ]
    
    for query in queries:
        print(f"\n   Query: '{query}'")
        results = await server.search_tables(query, limit=3)
        for r in results["tables"]:
            print(f"   → {r['table_name']} (score: {r['similarity_score']}) - {r['domain']}")
    
    # Demonstrate related tables
    print("\n🔗 RELATED TABLE DISCOVERY:")
    if results["tables"]:
        first_table = results["tables"][0]["table_name"]
        related = await server.find_related_tables(first_table, limit=3)
        print(f"   Tables related to '{first_table}':")
        for r in related["related_tables"]:
            print(f"   → {r['table_name']} (similarity: {r['similarity_score']})")
    
    print("\n" + "=" * 70)
    print("VERDICT: ✅ EXCELLENT - Best for large-scale discovery scenarios")
    print("=" * 70)


# ============================================================================
# 🚨 BAD COP FINAL REVIEW 🚨
# ============================================================================
#
# WHAT THIS CODE DOES RIGHT:
# ✅ Semantic search (not just keywords)
# ✅ Related table discovery
# ✅ Minimal tool footprint (4 tools)
# ✅ Caching for performance
# ✅ Natural language queries
#
# WHAT THIS CODE DOES WRONG:
# ⚠️ Mock embeddings (need real embedding model)
# ⚠️ No incremental embedding updates
# ⚠️ No hybrid search (semantic + keyword)
# ⚠️ No query expansion for acronyms
# ⚠️ Linear similarity search (should use vector DB)
#
# PRODUCTION REQUIREMENTS:
# 1. Real embedding model (OpenAI, Cohere, local)
# 2. Vector database (Pinecone, Weaviate, pgvector)
# 3. Incremental embedding updates on schema changes
# 4. Hybrid search: semantic + keyword + filters
# 5. Query expansion for business acronyms
#
# WHEN TO USE THIS PATTERN:
# - 500+ tables
# - Users don't know exact table names
# - Natural language is preferred interface
# - Discovery is primary use case
#
# WHEN TO AVOID THIS PATTERN:
# - Users know exact table names (overhead)
# - Real-time requirements (embedding latency)
# - No embedding infrastructure available
#
# ============================================================================


if __name__ == "__main__":
    asyncio.run(demonstrate())
