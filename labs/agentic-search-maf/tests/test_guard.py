import pytest

from agentic_search_maf.errors import BlockedUrlError
from agentic_search_maf.fetch.guard import ensure_public_host, validate_url


def test_allows_public_https_urls():
    validate_url("https://example.com/page")
    validate_url("http://93.184.216.34/")


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "ftp://example.com/"],
)
def test_rejects_non_http_schemes(url):
    with pytest.raises(BlockedUrlError):
        validate_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://10.0.0.5/admin",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "http://169.254.169.254/latest/meta-data",
        "http://100.64.0.1/",
        "http://[::1]/",
        "http://[fd00::1]/",
        "http://[::ffff:127.0.0.1]/",
    ],
)
def test_rejects_loopback_and_private_addresses(url):
    with pytest.raises(BlockedUrlError):
        validate_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://localhost:8080/",
        "http://intranet/",
        "http://printer.local/",
        "http://db.internal/",
    ],
)
def test_rejects_internal_hostnames(url):
    with pytest.raises(BlockedUrlError):
        validate_url(url)


def test_rejects_credentials_in_url():
    with pytest.raises(BlockedUrlError):
        validate_url("https://user:pass@example.com/")


async def test_dns_check_rejects_loopback_resolution():
    # localtest.me resolves to 127.0.0.1; offline the lookup fails, which is
    # also a rejection. Either way the fetch must be blocked.
    with pytest.raises(BlockedUrlError):
        await ensure_public_host("http://localtest.me/")
