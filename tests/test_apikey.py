from app.api.apikey import extract_api_key


def test_extracts_present_key():
    assert extract_api_key({"X-API-Key": "abc123"}) == "abc123"


def test_case_insensitive_header_name():
    assert extract_api_key({"x-api-key": "abc123"}) == "abc123"
    assert extract_api_key({"X-Api-Key": "abc123"}) == "abc123"


def test_absent_header_returns_none():
    assert extract_api_key({}) is None
    assert extract_api_key({"X-Client-Id": "unrelated"}) is None


def test_blank_header_treated_as_absent():
    assert extract_api_key({"X-API-Key": ""}) is None
    assert extract_api_key({"X-API-Key": "   "}) is None


def test_surrounding_whitespace_is_stripped():
    assert extract_api_key({"X-API-Key": "  abc123  "}) == "abc123"


def test_works_against_a_starlette_headers_object():
    """Real requests hand this a Starlette Headers object, not a plain
    dict -- confirm the case-insensitive lookup logic doesn't assume dict
    semantics that Headers happens not to break."""
    from starlette.datastructures import Headers

    headers = Headers({"x-api-key": "abc123"})
    assert extract_api_key(headers) == "abc123"
