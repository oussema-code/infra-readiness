import json

import pytest

from infra_readiness.models import Result, Status, exit_code


def result(status):
    return Result("api", "http", "http://backend/live", status, 12.5, "Observed HTTP 200")


@pytest.mark.parametrize("statuses, expected", [
    ([Status.PASS], 0), ([Status.UNKNOWN], 2), ([Status.FAIL], 1),
    ([Status.PASS, Status.UNKNOWN], 2),
    ([Status.UNKNOWN, Status.FAIL, Status.PASS], 1),
])
def test_exit_precedence(statuses, expected):
    assert exit_code([result(status) for status in statuses]) == expected


def test_empty_report_is_not_success():
    with pytest.raises(ValueError):
        exit_code([])


def test_result_is_json_serializable():
    document = json.loads(json.dumps(result(Status.PASS).to_dict()))
    assert document["status"] == "PASS"
    assert document["duration_ms"] == 12.5
    assert document["error_category"] is None
