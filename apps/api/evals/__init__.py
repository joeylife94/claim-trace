"""Offline retrieval evaluation for ClaimTrace claim search.

Lives inside the API application rather than at the repository root because it
runs the real thing: the same indexing service, the same retrievers, the same
fusion, and the same PostgreSQL. It needs the application's dependencies and its
container, and there is no second, simplified retrieval path for it to use.
"""
