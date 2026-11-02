"""Load and validate the entire configuration without performing network I/O."""

from dataclasses import dataclass
import ipaddress
from pathlib import Path
from urllib.parse import urlsplit

import yaml


class ConfigError(ValueError):
    """Configuration cannot safely be executed."""


class UniqueKeyLoader(yaml.SafeLoader):
    """Reject duplicate mapping keys instead of silently replacing values."""


def _mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str):
            raise ConfigError("configuration keys must be strings")
        if key in result:
            raise ConfigError("duplicate configuration key")
        result[key] = loader.construct_object(value_node)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


@dataclass(frozen=True)
class Check:
    name: str
    type: str
    timeout: float
    host: str | None = None
    port: int | None = None
    url: str | None = None
    expected_status: int | None = None


@dataclass(frozen=True)
class Config:
    concurrency: int
    checks: tuple[Check, ...]


def _keys(value, allowed, context):
    if not isinstance(value, dict):
        raise ConfigError(f"{context} must be a mapping")
    if set(value) - allowed:
        raise ConfigError(f"{context} contains unsupported fields")


def _integer(value, minimum, maximum, context):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ConfigError(f"{context} must be an integer between {minimum} and {maximum}")
    return value


def parse_config(document):
    _keys(document, {"concurrency", "checks"}, "configuration")
    concurrency = _integer(document.get("concurrency", 4), 1, 32, "concurrency")
    entries = document.get("checks")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 100:
        raise ConfigError("checks must be a list containing 1 to 100 entries")
    checks = []
    names = set()
    for index, entry in enumerate(entries):
        context = f"check {index + 1}"
        _keys(entry, {"name", "type", "timeout", "host", "port", "url", "expected_status"}, context)
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 80 or not name.isprintable():
            raise ConfigError(f"{context}: name must be printable text of 1 to 80 characters")
        if name in names:
            raise ConfigError(f"{context}: check names must be unique")
        names.add(name)
        kind = entry.get("type")
        if kind not in ("dns", "tcp", "http"):
            raise ConfigError(f"{context}: type must be dns, tcp, or http")
        timeout = entry.get("timeout", 2)
        if type(timeout) not in (int, float) or not 0.1 <= timeout <= 60:
            raise ConfigError(f"{context}: timeout must be between 0.1 and 60 seconds")
        common = {"name", "type", "timeout"}
        if kind in ("dns", "tcp"):
            _keys(entry, common | ({"host", "port"} if kind == "tcp" else {"host"}), context)
            host = entry.get("host")
            if not isinstance(host, str) or not host or len(host) > 253 or any(
                not (character.isascii() and (character.isalnum() or character in ".-:_"))
                for character in host
            ):
                raise ConfigError(f"{context}: host must be a hostname or IP address without a scheme or port")
            if ":" in host:
                try:
                    ipaddress.IPv6Address(host)
                except ValueError:
                    raise ConfigError(f"{context}: host must not include a port") from None
            port = _integer(entry.get("port"), 1, 65535, f"{context}: port") if kind == "tcp" else None
            checks.append(Check(name, kind, float(timeout), host=host, port=port))
        else:
            _keys(entry, common | {"url", "expected_status"}, context)
            url = entry.get("url")
            try:
                if not isinstance(url, str) or not url.isascii() or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url):
                    raise ValueError
                parsed = urlsplit(url)
                if (parsed.scheme not in ("http", "https") or not parsed.hostname
                        or parsed.username is not None or parsed.password is not None
                        or parsed.query or parsed.fragment or parsed.port == 0):
                    raise ValueError
            except ValueError:
                raise ConfigError(f"{context}: url must be HTTP(S), with no credentials, query, or fragment") from None
            status = _integer(entry.get("expected_status", 200), 100, 599, f"{context}: expected_status")
            checks.append(Check(name, kind, float(timeout), url=url, expected_status=status))
    return Config(concurrency, tuple(checks))


def load_config(path: Path):
    try:
        with path.open("rb") as stream:
            contents = stream.read(65537)
        if len(contents) > 65536:
            raise ConfigError("configuration exceeds the 64 KiB limit")
        document = yaml.load(contents.decode("utf-8"), Loader=UniqueKeyLoader)
    except (OSError, UnicodeError) as error:
        raise ConfigError("cannot read configuration as a UTF-8 file") from error
    except ConfigError:
        raise
    except (yaml.YAMLError, RecursionError, ValueError) as error:
        raise ConfigError("invalid YAML configuration") from error
    return parse_config(document)
