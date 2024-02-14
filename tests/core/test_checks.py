from dockerflow import checks


def test_run_checks():
    check_fns = (
        ("returns_error", lambda: [checks.Error("my error message", id="my.error")]),
    )
    results = checks.run_checks(checks=check_fns)
    assert results.level == checks.ERROR
    assert results.statuses == {"returns_error": "error"}
    assert results.details == {
        "returns_error": {
            "level": checks.ERROR,
            "messages": {"my.error": "my error message"},
            "status": "error",
        }
    }


def test_run_multiple_checks():
    check_fns = (
        (
            "returns_error",
            lambda: [checks.Error("my error message", id="my.error")],
        ),
        (
            "returns_warning",
            lambda: [checks.Warning("my warning message", id="my.warning")],
        ),
    )
    results = checks.run_checks(checks=check_fns)
    assert results.level == checks.ERROR
    assert results.statuses == {"returns_error": "error", "returns_warning": "warning"}
    assert results.details == {
        "returns_error": {
            "level": checks.ERROR,
            "messages": {"my.error": "my error message"},
            "status": "error",
        },
        "returns_warning": {
            "level": 30,
            "messages": {"my.warning": "my warning message"},
            "status": "warning",
        },
    }


def test_silenced_checks():
    check_fns = (
        (
            "returns_error",
            lambda: [checks.Error("my error message", id="my.error")],
        ),
        (
            "returns_warning",
            lambda: [checks.Warning("my warning message", id="my.warning")],
        ),
    )
    results = checks.run_checks(checks=check_fns, silenced_check_ids=["my.error"])
    assert results.details == {
        "returns_warning": {
            "level": checks.WARNING,
            "messages": {
                "my.warning": "my warning message",
            },
            "status": "warning",
        }
    }


def test_checks_returns_multiple_messages():
    check_fns = (
        (
            "returns_messages",
            lambda: [
                checks.Error("my error message", id="my.error"),
                checks.Warning("my warning message", id="my.warning"),
            ],
        ),
        (
            "returns_more_messages",
            lambda: [
                checks.Warning("another warning message", id="another.warning"),
            ],
        ),
    )
    results = checks.run_checks(checks=check_fns)
    assert results.level == checks.ERROR
    assert results.statuses == {
        "returns_messages": "error",
        "returns_more_messages": "warning",
    }
    assert results.details == {
        "returns_messages": {
            "level": checks.ERROR,
            "messages": {
                "my.warning": "my warning message",
                "my.error": "my error message",
            },
            "status": "error",
        },
        "returns_more_messages": {
            "level": checks.WARNING,
            "messages": {
                "another.warning": "another warning message",
            },
            "status": "warning",
        },
    }
