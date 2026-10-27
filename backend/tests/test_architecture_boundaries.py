"""Enforces the modular-monolith rules (ARCHITECTURE.md §7.12, §8; ADR-0002..0008) by reading the source."""
import ast
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
MODULES = BACKEND / "modules"

# The declared module dependency matrix for P1 (ARCHITECTURE.md §8.3 as extended by ADR-0004 and ADR-0005).
ALLOWED = {
    "audit": set(),
    "institutions": {"audit"},
    "users": {"audit"},
    "ledger": set(),
    "wallets": {"users", "ledger", "audit"},
    "auth": {"users", "institutions", "audit"},
    "devices": {"audit"},
    "merchants": {"users", "devices", "audit"},
    "payments": {"wallets", "merchants", "auth", "users", "devices", "institutions", "audit"},
    "reports": {"audit", "devices", "institutions", "ledger", "merchants", "payments", "users", "wallets"},
}


def _imports(path: Path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            yield node.module, [a.name for a in node.names]
        elif isinstance(node, ast.Import):
            for a in node.names:
                yield a.name, []


def _module_files():
    for mod_dir in MODULES.iterdir():
        if mod_dir.is_dir() and mod_dir.name in ALLOWED:
            for f in mod_dir.glob("*.py"):
                yield mod_dir.name, f


def test_every_module_folder_is_declared():
    on_disk = {d.name for d in MODULES.iterdir() if d.is_dir() and any(d.glob("*.py"))}
    assert on_disk == set(ALLOWED), on_disk ^ set(ALLOWED)


def test_modules_only_import_published_service_of_declared_dependencies():
    violations = []
    for name, f in _module_files():
        for module, names in _imports(f):
            parts = module.split(".")
            if parts[0] != "modules" or len(parts) < 2 or parts[1] == name:
                continue
            other = parts[1]
            if other not in ALLOWED[name]:
                violations.append(f"{name}/{f.name} depends on undeclared module '{other}'")
            # `from modules.x import service` -> names == ['service'];  `from modules.x.service import y` -> parts[2]
            subs = [parts[2]] if len(parts) > 2 else names
            for sub in subs:
                if sub != "service":
                    violations.append(f"{name}/{f.name} imports modules.{other}.{sub}: only modules.<x>.service is published")
    assert not violations, "\n".join(violations)


def test_dependency_graph_is_acyclic():
    seen, stack = set(), set()

    def visit(n):
        assert n not in stack, f"cyclic dependency through {n}"
        if n in seen:
            return
        stack.add(n)
        for m in ALLOWED[n]:
            visit(m)
        stack.discard(n)
        seen.add(n)

    for n in ALLOWED:
        visit(n)


def test_core_and_shared_contain_no_business_module_imports():
    for pkg in ("core", "shared"):
        for f in (BACKEND / pkg).glob("*.py"):
            for module, _ in _imports(f):
                assert not module.startswith("modules"), f"{pkg}/{f.name} imports {module}"


def test_merchant_staff_path_cannot_reach_money():
    """Merchant (orders, fulfillment) never depends on wallets, ledger or payments: staff cannot alter financial state."""
    for f in (MODULES / "merchants").glob("*.py"):
        for module, _ in _imports(f):
            assert not re.match(r"modules\.(wallets|ledger|payments)", module), f"{f.name} imports {module}"


def test_only_the_wallet_service_assigns_available_value():
    pattern = re.compile(r"\.available_cu\s*=[^=]")
    offenders = []
    for path in list(MODULES.rglob("*.py")) + list((BACKEND / "app").glob("*.py")):
        if path.parts[-2:] == ("wallets", "service.py"):
            continue
        if pattern.search(path.read_text()):
            offenders.append(str(path.relative_to(BACKEND)))
    assert not offenders, offenders


def test_routers_contain_no_persistence_or_business_logic():
    forbidden = re.compile(r"\bselect\(|db\.query|db\.add\(|\.with_for_update|db\.execute")
    for name, f in _module_files():
        if f.name == "router.py":
            assert not forbidden.search(f.read_text()), f"{name}/router.py touches persistence directly"


def test_no_create_all_and_no_floating_point_money():
    for path in list(MODULES.rglob("*.py")) + list((BACKEND / "app").glob("*.py")) + list((BACKEND / "core").glob("*.py")):
        text = path.read_text()
        assert "metadata.create_all(" not in text, f"{path.name} uses create_all()"
        if "modules" in path.parts:
            assert not re.search(r"\bfloat\b|Float\(|Numeric\(", text), f"{path.name} uses non-integer money type"


def test_no_hard_coded_credentials_or_first_institution_shortcut():
    banned = ["admin123", "canteen123", "stationery123", "demo-secret-not-for-production"]
    for path in BACKEND.rglob("*.py"):
        if "tests" in path.parts or "site-packages" in path.parts:
            continue
        text = path.read_text()
        for word in banned:
            assert word not in text, f"{path} contains {word}"
        assert "Institution).first()" not in text, f"{path} selects an arbitrary institution"
