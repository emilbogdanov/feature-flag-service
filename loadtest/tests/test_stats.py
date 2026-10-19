import pytest

from flagstaff_load.stats import Summary


def test_reports_percentiles_that_were_actually_measured() -> None:
    summary = Summary.of([float(n) for n in range(100, 0, -1)])

    assert summary == Summary(count=100, p50=50.0, p95=95.0, p99=99.0, max=100.0)


def test_a_single_sample_is_every_percentile() -> None:
    assert Summary.of([0.004]) == Summary(count=1, p50=0.004, p95=0.004, p99=0.004, max=0.004)


def test_needs_samples() -> None:
    with pytest.raises(ValueError, match="no samples"):
        Summary.of([])
