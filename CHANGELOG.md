# Changelog

## [0.6.0] - 2026-04-13

### Enhancements
- **Consolidated Schema**: Introduced a unified crumbs and users table architecture to replace the legacy dynamic per-project table model.
- **REST API**: Added standalone REST endpoints at /api in addition to the existing /graphql interface.
- **Geolocation Overhaul**: Transitioned to a "Bring Your Own Database" (BYODB) model using MaxMind maxminddb, removing runtime network dependencies.
- **Rate Limiting**: Implemented a standalone rate-limiting extension for both GraphQL and REST public routes.
- **New Dashboard**: Refreshed the visualization homepage using ApexCharts for more performant and interactive telemetry reporting.
- **Project Monitoring**: Added the ability to selectively monitor specific projects via a consolidated tracking system.

### Bug Fixes
- Fixed inconsistent status enum handling by qualifying the type within the migas schema.
- Resolved database session leaks by unifying all database operations under an explicit gen_session context manager.
- Fixed race conditions in project registration during concurrent server initialization.
- Stabilized integration tests by implementing robust mocking for external network traffic.

### Maintenance & Infrastructure
- **uv Integration**: Fully migrated dependency management from pip-tools to uv for lightning-fast builds and synchronizations.
- **Python 3.13**: Updated base images and CI pipelines to use Python 3.13.
- **Ruff & djlint**: Adopted ruff and djlint for repository-wide styling and linting consistency.
- **CI/CD Hardening**: Updated GitHub Actions to use latest immutable releases (v6+, v2+) and added automated GeoDB caching.

### Refactoring
- Unified all database boot logic into a factory-based application creation pattern.
- Extracted GraphQL parsing and validation logic into a dedicated module for better maintainability.
- Consolidated MIGAS_DEBUG and MIGAS_TESTING into a more robust MIGAS_DEV environment flag.

---
*For a full list of changes, see the [commit history](https://github.com/nipreps/migas-server/compare/0.5.0...HEAD).*
