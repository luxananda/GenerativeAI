"""
1000 Tables Scenarios

Demonstrates different patterns for exposing large numbers of database tables
through MCP without overwhelming the LLM's context window.

Patterns:
- 01_naive_all_tools.py: Anti-pattern showing what NOT to do
- 02_lazy_loading.py: Load tools on-demand
- 03_domain_grouping.py: Group tables by business domain
- 04_search_discovery.py: Semantic search for tables
- 05_hybrid_approach.py: Recommended combined approach
"""
