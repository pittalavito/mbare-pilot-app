"""Persistence by aggregate: one store per aggregate (runs, catalog, agents,
projects, ...), each over its own repositories and mappers. A service receives
only the stores it uses, so its constructor says what it reads and writes."""
