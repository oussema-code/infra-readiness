from pathlib import Path
from unittest.mock import patch

import pytest

from infra_readiness.cli import main
from infra_readiness.config import ConfigError, load_config, parse_config


def configuration(**changes):
    value = {"checks": [{"name": "api", "type": "http", "url": "http://backend:8000/ready"}]}
    value.update(changes)
    return value


def test_example_configuration():
    config = load_config(Path(__file__).parents[1] / "examples/lab.yaml")
    assert len(config.checks) == 5
    assert config.checks[0].host == "db"
    assert config.checks[-1].expected_status == 200


@pytest.mark.parametrize("value", [None, [], {}, {"checks": []}, {"checks": "api"}])
def test_reject_invalid_document(value):
    with pytest.raises(ConfigError):
        parse_config(value)


@pytest.mark.parametrize("value", [True, 0, 33, "4", 1.5])
def test_invalid_concurrency(value):
    with pytest.raises(ConfigError, match="concurrency"):
        parse_config(configuration(concurrency=value))


@pytest.mark.parametrize("change", [
    {"timeout": True}, {"timeout": 0}, {"timeout": float("nan")},
    {"timeout": float("inf")}, {"timeout": 10**400}, {"timeout": 61},
    {"type": "ping"}, {"name": ""}, {"name": "line\nbreak"},
    {"port": 8000}, {"expected_status": True}, {"expected_status": 600},
    {"url": "file:///etc/passwd"}, {"url": "http://backend:99999"},
    {"url": "http://backend:0"}, {"url": "http://"},
    {"url": "http://user:password@backend/"},
    {"url": "http://backend/?token=secret"}, {"url": "http://backend/#fragment"},
    {"url": "http://back end/"}, {"url": 17},
])
def test_invalid_http_check(change):
    document = configuration()
    document["checks"][0].update(change)
    with pytest.raises(ConfigError):
        parse_config(document)


@pytest.mark.parametrize("entry", [
    {"name": "tcp", "type": "tcp", "host": "db"},
    {"name": "tcp", "type": "tcp", "host": "db", "port": True},
    {"name": "tcp", "type": "tcp", "host": "db", "port": 65536},
    {"name": "dns", "type": "dns", "host": "http://db"},
    {"name": "dns", "type": "dns", "host": "db:3306"},
    {"name": "dns", "type": "dns", "host": "db", "port": 3306},
])
def test_invalid_network_check(entry):
    with pytest.raises(ConfigError):
        parse_config({"checks": [entry]})


def test_duplicate_names_and_unknown_fields():
    document = configuration()
    document["checks"] *= 2
    with pytest.raises(ConfigError, match="unique"):
        parse_config(document)
    with pytest.raises(ConfigError, match="unsupported"):
        parse_config(configuration(concurency=2))


@pytest.mark.parametrize("contents", [
    "checks: [", "!!python/object:builtins.object {}", "concurrency: 1\nconcurrency: 2\nchecks: []",
    "? [a, b]\n: 1", "x" * 65537,
])
def test_invalid_yaml_file(tmp_path, contents):
    path = tmp_path / "invalid.yaml"
    path.write_text(contents)
    with pytest.raises(ConfigError):
        load_config(path)


def test_missing_file_and_invalid_encoding(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "missing.yaml")
    path = tmp_path / "invalid.yaml"
    path.write_bytes(b"\xff")
    with pytest.raises(ConfigError):
        load_config(path)


def test_validate_cli_never_probes_and_reports_invalid_config(tmp_path, capsys):
    path = tmp_path / "config.yaml"
    path.write_text("checks: [{name: api, type: http, url: 'http://backend/live'}]")
    with patch("socket.getaddrinfo", side_effect=AssertionError("network lookup")), patch(
        "socket.create_connection", side_effect=AssertionError("network connection")
    ):
        assert main(["validate", str(path)]) == 0
        path.write_text("checks: []")
        assert main(["validate", str(path)]) == 3
    assert "Configuration error" in capsys.readouterr().err
