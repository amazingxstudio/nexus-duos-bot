import time


def now_ms() -> int:
    return int(time.time() * 1000)


def elapsed_ms(state: dict) -> int:
    return now_ms() - state["started_at"]
