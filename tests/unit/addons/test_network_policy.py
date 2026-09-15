from __future__ import annotations

import pytest

from boneio.addons.errors import AddonError
from boneio.addons.network import canonical_repository_url, is_public_address, resolve_same_origin


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fe80::1", "ff02::1"])
def test_non_public_addresses_are_blocked(address: str) -> None:
    assert not is_public_address(address)


def test_public_address_is_allowed() -> None:
    assert is_public_address("93.184.216.34")


@pytest.mark.parametrize(
    "url",
    ["http://example.com/index.json", "https://user:pass@example.com/index.json", "https://example.com/index.json#x"],
)
def test_repository_url_rejects_unsafe_forms(url: str) -> None:
    with pytest.raises(AddonError):
        canonical_repository_url(url)


def test_file_resolution_stays_on_origin() -> None:
    assert (
        resolve_same_origin("https://example.com/catalog/index.json", "packs/a.yaml")
        == "https://example.com/catalog/packs/a.yaml"
    )
    with pytest.raises(AddonError):
        resolve_same_origin("https://example.com/catalog/index.json", "https://cdn.example.com/a.yaml")
