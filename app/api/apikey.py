from collections.abc import Mapping

API_KEY_HEADER = "X-API-Key"


def extract_api_key(headers: Mapping[str, str]) -> str | None:
    """Pull the API key out of request headers, if present.

    Looks up the header name case-insensitively by hand rather than relying
    on the caller's mapping to normalize case for us -- this needs to behave
    the same whether `headers` is a plain dict (as in unit tests) or
    Starlette's own case-insensitive Headers object (as in real requests).
    A present-but-blank/whitespace-only header is treated as absent.
    """
    for key, value in headers.items():
        if key.lower() == API_KEY_HEADER.lower():
            value = value.strip()
            return value or None
    return None
