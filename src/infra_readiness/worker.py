"""One isolated probe; the parent enforces its end-to-end deadline."""

import http.client
import json
import socket
import ssl
import sys
from urllib.parse import urlsplit

from .config import Check


def probe(check: Check):
    if check.type == "dns":
        addresses = sorted({entry[4][0] for entry in socket.getaddrinfo(
            check.host, None, type=socket.SOCK_STREAM
        )})
        return "PASS", f"Resolved {len(addresses)} address(es): {', '.join(addresses[:16])}", None
    if check.type == "tcp":
        with socket.create_connection((check.host, check.port), timeout=check.timeout):
            return "PASS", "TCP connection established", None
    parsed = urlsplit(check.url)
    connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = connection_type(parsed.hostname, parsed.port, timeout=check.timeout)
    try:
        connection.request("GET", parsed.path or "/", headers={"Connection": "close"})
        with connection.getresponse() as response:
            status = response.status
        # Status checks deliberately do not consume bodies or follow redirects.
        matches = status == check.expected_status
        return ("PASS" if matches else "FAIL",
                f"Observed HTTP {status}; expected {check.expected_status}",
                None if matches else "http_status")
    finally:
        connection.close()


def execute(check: Check):
    try:
        return probe(check)
    except socket.gaierror as error:
        if error.errno == socket.EAI_NONAME:
            return "FAIL", "Name resolution returned no matching address", "dns_not_found"
        return "UNKNOWN", f"Name resolution failed (resolver code {error.errno})", "dns_error"
    except TimeoutError:
        return "UNKNOWN", "Network operation timed out; service state is undetermined", "timeout"
    except ConnectionRefusedError:
        return "FAIL", "Connection was refused", "connection_refused"
    except ssl.SSLCertVerificationError:
        return "FAIL", "TLS certificate verification failed", "tls_certificate"
    except ssl.SSLError:
        return "FAIL", "TLS handshake or protocol failed", "tls_protocol"
    except http.client.HTTPException:
        return "FAIL", "Invalid or incomplete HTTP response headers", "http_protocol"
    except OSError as error:
        return "UNKNOWN", f"Network operation failed (OS error {error.errno})", "network_error"


def main():
    check = Check(**json.load(sys.stdin))
    status, evidence, category = execute(check)
    print(json.dumps({"status": status, "evidence": evidence, "error_category": category}))


if __name__ == "__main__":
    main()
