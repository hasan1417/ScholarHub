"""Library proxy links: prefix validation, URL building, and the link endpoint."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1 import users as users_api
from app.services.library_access import (
    InvalidProxyPrefix,
    build_proxied_url,
    normalize_doi,
    normalize_proxy_prefix,
)

KFUPM = "https://login.kfupm.idm.oclc.org/login?url="
OPENATHENS = "https://go.openathens.net/redirector/example.ac.uk?url="


class FakeDB:
    def commit(self) -> None:
        pass


@pytest.mark.parametrize("prefix", [KFUPM, OPENATHENS, "  https://ezproxy.example.edu/login?qurl=  "])
def test_valid_prefixes_are_accepted(prefix: str) -> None:
    assert normalize_proxy_prefix(prefix) == prefix.strip()


@pytest.mark.parametrize(
    "prefix",
    [
        "http://login.kfupm.idm.oclc.org/login?url=",
        "https://login.kfupm.idm.oclc.org/login",
        "javascript:alert(1)//url=",
        "https://" + "a" * 500 + "/login?url=",
    ],
)
def test_invalid_prefixes_are_rejected(prefix: str) -> None:
    with pytest.raises(InvalidProxyPrefix):
        normalize_proxy_prefix(prefix)


def test_ezproxy_target_is_appended_unencoded() -> None:
    assert build_proxied_url(KFUPM, "https://ieeexplore.ieee.org/document/726791/") == (
        "https://login.kfupm.idm.oclc.org/login?url=https://ieeexplore.ieee.org/document/726791/"
    )


@pytest.mark.parametrize("prefix", [OPENATHENS, "https://ezproxy.example.edu/login?qurl="])
def test_openathens_and_qurl_targets_are_encoded(prefix: str) -> None:
    assert build_proxied_url(prefix, "https://www.nature.com/articles/nature14539") == (
        prefix + "https%3A%2F%2Fwww.nature.com%2Farticles%2Fnature14539"
    )


@pytest.mark.parametrize(
    "raw", ["10.1038/nature14539", "https://doi.org/10.1038/nature14539", "doi:10.1038/nature14539"]
)
def test_doi_is_normalized(raw: str) -> None:
    assert normalize_doi(raw) == "10.1038/nature14539"


@pytest.mark.asyncio
async def test_set_library_access_validates_and_clears() -> None:
    user = SimpleNamespace(library_proxy_prefix=None)
    result = await users_api.set_library_access(
        users_api.LibraryAccessRequest(proxy_prefix=KFUPM), current_user=user, db=FakeDB()
    )
    assert result == {"proxy_prefix": KFUPM}

    with pytest.raises(HTTPException) as exc:
        await users_api.set_library_access(
            users_api.LibraryAccessRequest(proxy_prefix="https://bad.example"), current_user=user, db=FakeDB()
        )
    assert exc.value.status_code == 400
    assert user.library_proxy_prefix == KFUPM

    await users_api.set_library_access(
        users_api.LibraryAccessRequest(proxy_prefix=""), current_user=user, db=FakeDB()
    )
    assert user.library_proxy_prefix is None


@pytest.mark.asyncio
async def test_doi_is_resolved_to_publisher_url_before_proxying(monkeypatch) -> None:
    async def fake_resolve(doi: str) -> str:
        assert doi == "10.1109/5.726791"
        return "https://ieeexplore.ieee.org/document/726791/"

    monkeypatch.setattr(users_api, "resolve_doi", fake_resolve)
    resp = await users_api.get_library_link(
        doi="https://doi.org/10.1109/5.726791", url=None,
        current_user=SimpleNamespace(library_proxy_prefix=KFUPM),
    )
    assert resp["url"] == KFUPM + "https://ieeexplore.ieee.org/document/726791/"


@pytest.mark.asyncio
async def test_unresolvable_doi_falls_back_to_given_url(monkeypatch) -> None:
    async def fake_resolve(doi: str) -> None:
        return None

    monkeypatch.setattr(users_api, "resolve_doi", fake_resolve)
    resp = await users_api.get_library_link(
        doi="10.1/x", url="https://publisher.example/x",
        current_user=SimpleNamespace(library_proxy_prefix=KFUPM),
    )
    assert resp["url"] == KFUPM + "https://publisher.example/x"


@pytest.mark.asyncio
async def test_without_a_proxy_the_link_goes_straight_to_the_publisher() -> None:
    resp = await users_api.get_library_link(
        doi=None, url="https://publisher.example/x", current_user=SimpleNamespace(library_proxy_prefix=None),
    )
    assert resp["url"] == "https://publisher.example/x"


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [None, "javascript:alert(1)", "ftp://x"])
async def test_missing_or_non_http_target_is_rejected(url) -> None:
    with pytest.raises(HTTPException) as exc:
        await users_api.get_library_link(
            doi=None, url=url, current_user=SimpleNamespace(library_proxy_prefix=KFUPM),
        )
    assert exc.value.status_code == 400
