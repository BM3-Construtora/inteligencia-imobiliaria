"""Pytest fixtures + offline isolation.

Sets dummy env vars BEFORE src.* is imported so src.config doesn't crash.
Mocks src.db.get_client so no real Supabase call ever happens.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure project root is on sys.path so `import src.*` works.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Set required env vars BEFORE any src import triggers src.config
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")

# Stub heavy/external modules so we never touch real Supabase/Postgrest/dotenv.
# Must be installed in sys.modules BEFORE src.* imports them.
import types as _types  # noqa: E402

if "dotenv" not in sys.modules:
    _dotenv = _types.ModuleType("dotenv")
    _dotenv.load_dotenv = lambda *a, **kw: None  # type: ignore[attr-defined]
    sys.modules["dotenv"] = _dotenv

if "supabase" not in sys.modules:
    _supabase = _types.ModuleType("supabase")
    _supabase.create_client = lambda *a, **kw: MagicMock()  # type: ignore[attr-defined]
    _supabase.Client = MagicMock  # type: ignore[attr-defined]
    sys.modules["supabase"] = _supabase

if "postgrest" not in sys.modules:
    _postgrest = _types.ModuleType("postgrest")
    _postgrest_exc = _types.ModuleType("postgrest.exceptions")

    class _APIError(Exception):
        def __init__(self, *a, **kw):
            super().__init__(*a)
            self.code = kw.get("code", "")

    _postgrest_exc.APIError = _APIError  # type: ignore[attr-defined]
    _postgrest.exceptions = _postgrest_exc  # type: ignore[attr-defined]
    sys.modules["postgrest"] = _postgrest
    sys.modules["postgrest.exceptions"] = _postgrest_exc


def _make_chain_mock() -> MagicMock:
    """Build a MagicMock that mimics the supabase query-builder chain.

    Every chained method (.table().select().eq().in_().limit().execute() ...)
    returns the same mock, so callers can chain freely without errors.
    The terminal .execute() returns an object with .data = [] by default.
    """
    chain = MagicMock(name="supabase_chain")

    # All chain methods return the same chain mock
    for method in (
        "table", "select", "insert", "update", "upsert", "delete",
        "eq", "neq", "gt", "gte", "lt", "lte", "in_", "is_", "not_",
        "or_", "and_", "filter", "match", "limit", "range", "order",
        "single", "maybe_single", "on_conflict",
    ):
        getattr(chain, method).return_value = chain

    # .not_ is also an attribute that chains
    chain.not_.is_ = MagicMock(return_value=chain)

    execute_result = MagicMock()
    execute_result.data = []
    execute_result.count = 0
    chain.execute.return_value = execute_result

    return chain


@pytest.fixture
def mock_db() -> MagicMock:
    """A MagicMock simulating a Supabase client. Chainable + safe."""
    return _make_chain_mock()


@pytest.fixture(autouse=True)
def _patch_get_client(monkeypatch, mock_db):
    """Auto-patch src.db.get_client to return the mock_db.

    Applies to every test so no test can accidentally hit Supabase.
    """
    import src.db
    monkeypatch.setattr(src.db, "get_client", lambda: mock_db)
    # Also patch where it's already imported in other modules
    for mod_name in (
        "src.normalizer", "src.classifier", "src.deduplicator",
        "src.viability", "src.hunter",
    ):
        if mod_name in sys.modules:
            mod = sys.modules[mod_name]
            if hasattr(mod, "get_client"):
                monkeypatch.setattr(mod, "get_client", lambda: mock_db)
    yield


# ============================================================
# Sample raw payloads — match the shape each normalizer expects
# ============================================================

@pytest.fixture
def sample_raw_uniao() -> dict:
    return {
        "id": "uniao-123",
        "type": "house",
        "title": "Casa nova MCMV",
        "address": "Rua das Flores, 123",
        "street": "Rua das Flores",
        "number": "123",
        "neighborhood": "Jardim Maria Izabel",
        "city": "Marília",
        "state": "SP",
        "zipCode": "17500-000",
        "latitude": -22.213,
        "longitude": -49.946,
        "salePrice": 220000,
        "rentPrice": None,
        "condominiumFee": None,
        "iptu": 500,
        "totalArea": 250,
        "builtArea": 55,
        "bedrooms": 2,
        "bathrooms": 1,
        "parkingSpaces": 1,
        "description": "Casa térrea",
        "features": ["garagem", "quintal"],
        "isFeatured": False,
        "isActive": True,
        "mainImage": {"url": "http://img/1.jpg"},
        "images": [{"url": "http://img/1.jpg"}, {"url": "http://img/2.jpg"}],
    }


@pytest.fixture
def sample_raw_toca() -> dict:
    return {
        "id": 4567,
        "tipo_imovel": "Casa",
        "titulo": "Casa 3 dorms",
        "endereco": "Avenida Brasil, 1000",
        "bairro_nome": "Centro",
        "cidade": "Marília",
        "lati": -22.21,
        "longi": -49.95,
        "valor": 350000,
        "valor_aluguel": None,
        "a_terreno": 200,
        "a_construida": 90,
        "dormitorios": 3,
        "banheiros": 2,
        "suites": 1,
        "garagem": 2,
        "descricao": "Casa térrea ampla",
        "caracteristicas": ["churrasqueira"],
        "flag_mostra_site_ven": 1,
        "flag_mostra_site_loc": 0,
        "destaque": "0",
        "destaque_venda": "0",
        "foto_thumb": "http://toca/thumb.jpg",
        "imovel_fotos": [
            {"foto_OK": "http://toca/1.jpg"},
            {"foto_OK": "http://toca/2.jpg"},
        ],
    }


@pytest.fixture
def sample_raw_vivareal() -> dict:
    return {
        "id": "vr-001",
        "url": "https://vivareal.com.br/imovel/vr-001",
        "name": "Terreno 300m²",
        "title": "Terreno",
        "type": "land",
        "price": 180000,
        "area": 300,
        "bedrooms": None,
        "bathrooms": None,
        "parking": None,
        "neighborhood": "Jardim Califórnia",
        "city": "Marília",
        "state": "SP",
        "street": "Rua A",
        "image_url": "http://vr/img.jpg",
        "images": ["http://vr/img.jpg"],
        "description": "Terreno plano",
    }


@pytest.fixture
def sample_raw_chavesnamao() -> dict:
    return {
        "id": "cnm-002",
        "url": "https://chavesnamao.com.br/imovel/cnm-002",
        "name": "Casa próxima ao centro",
        "type": "house",
        "price": 280000,
        "area": 180,
        "bedrooms": 3,
        "bathrooms": 2,
        "parking": 2,
        "neighborhood": "Centro",
        "city": "Marília",
        "state": "SP",
        "street": "Rua B, 50",
        "image_url": "http://cnm/img.jpg",
        "images": [],
    }


@pytest.fixture
def sample_raw_zap() -> dict:
    return {
        "id": "zap-999",
        "url": "https://zapimoveis.com.br/imovel/zap-999",
        "name": "Apartamento 2 dorms",
        "type": "apartment",
        "price": 320000,
        "area": 65,
        "bedrooms": 2,
        "bathrooms": 1,
        "parking": 1,
        "neighborhood": "Fragata",
        "city": "Marília",
        "state": "SP",
        "image_url": "http://zap/img.jpg",
        "images": ["http://zap/img.jpg"],
    }
