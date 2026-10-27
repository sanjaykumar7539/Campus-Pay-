"""CampusPay business modules (ADR-0002, ADR-0003, ADR-0004..0008).

Each module folder contains:
  models.py   persistence entities owned by the module (private to the module)
  service.py  the module's PUBLISHED interface (application services + DTOs);
              the only file other modules may import
  router.py   presentation layer (HTTP); no business rules

tests/test_architecture_boundaries.py enforces the dependency matrix.
"""
