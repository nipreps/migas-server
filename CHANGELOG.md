# Changelog

## [0.6.3] - 2026-04-16

### Bug Fixes
- **Geolocation Stability**: Make requests more resilient to missing data in the MaxMind database.

---
*For a full list of changes, see the [commit history](https://github.com/nipreps/migas-server/compare/0.6.2...0.6.3).*

## [0.6.2] - 2026-04-16

A maintenance release focusing on dashboard improvements, logging refinements, and deployment optimizations.

### Enhancements
- **Restructured Dashboard**: Overhauled the visualization layout for better data density and interaction.

### Bug Fixes
- **Visualization Aggregation**: Corrected a bug in data aggregation and removed the redundant year bucket.
- **Database Consistency**: Ensured session uniqueness and consistent bucketing during data retrieval.

### Maintenance & Refactoring
- **Structured Logging**: Replaced standard prints with a more robust logging system and silenced noisy MaxMind reader outputs.

---
*For a full list of changes, see the [commit history](https://github.com/nipreps/migas-server/compare/0.6.1...0.6.2).*

## [0.6.1] - 2026-04-13

A bug-fix release to ensure client IPs are properly forwarded to the application.

---
*For a full list of changes, see the [commit history](https://github.com/nipreps/migas-server/compare/0.6.0...0.6.1).*

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
*For a full list of changes, see the [commit history](https://github.com/nipreps/migas-server/compare/0.5.0...0.6.0).*
