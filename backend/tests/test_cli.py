from app.cli import wait_db


def test_wait_db_retries_then_succeeds() -> None:
    calls = iter([RuntimeError("down"), RuntimeError("down"), None])
    assert wait_db("x", max_total=30, attempt=lambda _: next(calls)) is True


def test_wait_db_gives_up() -> None:
    assert wait_db("x", max_total=0.0, attempt=lambda _: RuntimeError("down")) is False
