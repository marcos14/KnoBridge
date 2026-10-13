"""How ``model`` names a product and a level, and the combinations a key lists (unit, no
database)."""

from __future__ import annotations

import uuid

import pytest

from knobridge.apikeys.auth import ApiKeyIdentity
from knobridge.apikeys.products import key_models, split_model
from knobridge.levels.level import ResponseLevel
from knobridge.products.models import Product


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("ERP", ("ERP", None)),
        ("ERP:support", ("ERP", ResponseLevel.SUPPORT)),
        ("ERP:end_user", ("ERP", ResponseLevel.END_USER)),
        ("Caixa: fechamento:product_dev", ("Caixa: fechamento", ResponseLevel.PRODUCT_DEV)),
        ("Caixa: fechamento", ("Caixa: fechamento", None)),
        ("ERP:Support", ("ERP:Support", None)),
        ("ERP:", ("ERP:", None)),
    ],
)
def test_split_model_reads_a_trailing_level(
    model: str, expected: tuple[str, ResponseLevel | None]
) -> None:
    assert split_model(model) == expected


def test_key_models_list_each_product_alone_then_its_levels() -> None:
    identity = ApiKeyIdentity(
        api_key_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        key_prefix="abcd1234",
        product_ids=None,
        max_level=ResponseLevel.SUPPORT,
    )
    erp, caixa = Product(name="ERP"), Product(name="Caixa")

    models = key_models(identity, [caixa, erp])

    assert [(m.product.name, m.level, m.level_explicit) for m in models] == [
        ("Caixa", ResponseLevel.SUPPORT, False),
        ("Caixa", ResponseLevel.END_USER, True),
        ("Caixa", ResponseLevel.SUPPORT, True),
        ("ERP", ResponseLevel.SUPPORT, False),
        ("ERP", ResponseLevel.END_USER, True),
        ("ERP", ResponseLevel.SUPPORT, True),
    ]
