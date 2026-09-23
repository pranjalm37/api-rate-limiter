"""Tests that /api/metrics produces genuinely valid Prometheus exposition
text, not just correct numbers (that's test_metrics.py's job). Written
against a small hand-rolled structural parser rather than pulling in
prometheus_client, matching this project's decision not to depend on it
even for rendering -- adding it just for test-side parsing would be an
inconsistent way to honor that decision."""

import re

import pytest

METRIC_LINE_RE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+(\S+)$")
VALID_TYPES = {"counter", "gauge", "histogram", "summary", "untyped"}


def parse_prometheus_text(text: str) -> dict:
    """Minimal structural validator -- enough to catch real format bugs
    (missing HELP/TYPE, malformed lines, unparseable values), not a full
    reimplementation of the exposition format spec."""
    help_names = set()
    type_by_name: dict[str, str] = {}
    values_by_name: dict[str, list[tuple[str, float]]] = {}

    for line in text.split("\n"):
        if line == "":
            continue
        if line.startswith("# HELP "):
            rest = line[len("# HELP ") :]
            name, _, _help_text = rest.partition(" ")
            assert name, f"malformed HELP line: {line!r}"
            help_names.add(name)
            continue
        if line.startswith("# TYPE "):
            rest = line[len("# TYPE ") :]
            parts = rest.split(" ")
            assert len(parts) == 2, f"malformed TYPE line: {line!r}"
            name, type_ = parts
            assert type_ in VALID_TYPES, f"invalid TYPE {type_!r} in line: {line!r}"
            type_by_name[name] = type_
            continue
        if line.startswith("#"):
            continue

        match = METRIC_LINE_RE.match(line)
        assert match, f"malformed metric line: {line!r}"
        name, labels, value_str = match.groups()
        value = float(value_str)  # must be a parseable number, incl. +Inf/-Inf/scientific
        values_by_name.setdefault(name, []).append((labels or "", value))

    return {"help": help_names, "types": type_by_name, "values": values_by_name}


@pytest.fixture
async def metrics_text(client):
    await client.post(
        "/api/config",
        json={
            "algorithm": "fixed_window",
            "backend": "memory",
            "capacity": 10,
            "window_seconds": 5,
            "refill_rate": 1,
        },
    )
    await client.get("/api/demo/resource", headers={"X-Client-Id": "render-test-a"})
    await client.get("/api/demo/resource", headers={"X-Client-Id": "render-test-b"})
    res = await client.get("/api/metrics")
    return res.text


@pytest.mark.asyncio
async def test_output_is_structurally_valid_prometheus_text(metrics_text):
    # parse_prometheus_text() itself asserts on any malformed line -- if
    # this doesn't raise, the whole response parsed cleanly.
    parse_prometheus_text(metrics_text)


_HISTOGRAM_SUFFIXES = ("_bucket", "_sum", "_count")


def _declared_family_name(value_line_name: str, parsed: dict) -> str:
    """A histogram declares HELP/TYPE once under its base name (e.g.
    rate_limiter_check_latency_seconds) but emits value lines under
    suffixed variants (_bucket/_sum/_count) that are never separately
    declared -- that's correct per the exposition format spec, not
    missing metadata. Strip a known suffix only if the base name is
    actually declared as a histogram."""
    if value_line_name in parsed["types"]:
        return value_line_name
    for suffix in _HISTOGRAM_SUFFIXES:
        if value_line_name.endswith(suffix):
            base = value_line_name[: -len(suffix)]
            if parsed["types"].get(base) == "histogram":
                return base
    return value_line_name


@pytest.mark.asyncio
async def test_every_emitted_metric_has_help_and_type(metrics_text):
    parsed = parse_prometheus_text(metrics_text)
    for name in parsed["values"]:
        family = _declared_family_name(name, parsed)
        assert family in parsed["help"], f"{name} has values but no # HELP line"
        assert family in parsed["types"], f"{name} has values but no # TYPE line"


@pytest.mark.asyncio
async def test_histogram_bucket_counts_are_monotonic_and_end_at_inf(metrics_text):
    parsed = parse_prometheus_text(metrics_text)
    buckets = parsed["values"]["rate_limiter_check_latency_seconds_bucket"]

    counts = [value for _labels, value in buckets]
    assert counts == sorted(counts)

    last_labels, last_count = buckets[-1]
    assert 'le="+Inf"' in last_labels


@pytest.mark.asyncio
async def test_histogram_inf_bucket_matches_count_line(metrics_text):
    parsed = parse_prometheus_text(metrics_text)
    _labels, inf_count = parsed["values"]["rate_limiter_check_latency_seconds_bucket"][-1]
    (_, total_count) = parsed["values"]["rate_limiter_check_latency_seconds_count"][0]
    assert inf_count == total_count


@pytest.mark.asyncio
async def test_content_type_is_prometheus_exposition_format(client):
    res = await client.get("/api/metrics")
    assert res.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"
