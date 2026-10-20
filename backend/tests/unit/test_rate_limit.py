"""Sliding-window rate limiter (spec §9.14)."""

from app.services.rate_limit import SlidingWindowRateLimiter


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_allows_up_to_limit_then_rejects():
    limiter = SlidingWindowRateLimiter(3, 60, clock=Clock())
    assert [limiter.hit("ip").allowed for _ in range(4)] == [True, True, True, False]


def test_window_slides():
    clock = Clock()
    limiter = SlidingWindowRateLimiter(2, 60, clock=clock)
    limiter.hit("ip")
    clock.now = 30
    limiter.hit("ip")
    clock.now = 59.5
    result = limiter.hit("ip")
    assert not result.allowed and result.retry_after == 1  # ceil(0.5)
    clock.now = 60  # first hit (t=0) leaves the window
    assert limiter.hit("ip").allowed
    assert not limiter.hit("ip").allowed


def test_rejected_requests_do_not_extend_the_block():
    clock = Clock()
    limiter = SlidingWindowRateLimiter(1, 60, clock=clock)
    limiter.hit("ip")
    for t in range(1, 60):
        clock.now = t
        assert not limiter.hit("ip").allowed
    clock.now = 60
    assert limiter.hit("ip").allowed


def test_retry_after_is_whole_seconds():
    clock = Clock()
    limiter = SlidingWindowRateLimiter(1, 60, clock=clock)
    limiter.hit("ip")
    clock.now = 10.2
    assert limiter.hit("ip").retry_after == 50  # ceil(49.8)


def test_keys_are_independent():
    limiter = SlidingWindowRateLimiter(1, 60, clock=Clock())
    assert limiter.hit("a").allowed
    assert limiter.hit("b").allowed
    assert not limiter.hit("a").allowed


def test_idle_keys_are_pruned():
    clock = Clock()
    limiter = SlidingWindowRateLimiter(5, 60, clock=clock)
    for ip in ("a", "b", "c"):
        limiter.hit(ip)
    clock.now = 61
    limiter.hit("d")
    assert set(limiter._hits) == {"d"}
