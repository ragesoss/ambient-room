import shutil
import subprocess
import time

import pytest

from ambient.engine import Engine

pytest.importorskip("ctcsound")


def null_device() -> bool:
    """ALSA's null device: the real engine, with no sound."""
    if not shutil.which("aplay"):
        return False
    r = subprocess.run(["aplay", "-D", "null", "-f", "S16_LE", "-r", "48000", "-c", "2", "-t", "raw", "-d", "1",
                        "/dev/zero"], capture_output=True)
    return r.returncode == 0


@pytest.mark.skipif(not null_device(), reason="no aplay or ALSA null device")
def test_a_restart_starts_the_clock_at_zero():
    # The conductor resets its grid from time() just after start(). A time
    # kept from the last run held the grid back as long as that run was.
    e = Engine("null", 100, 0.0)
    e.start()
    try:
        t0 = time.monotonic()
        while e.time() < 1.0 and time.monotonic() - t0 < 5:
            time.sleep(0.05)
        assert e.time() >= 1.0
    finally:
        e.stop()
    e.start()
    try:
        assert e.time() < 0.5
    finally:
        e.stop()


def alsa_null() -> bool:
    from ambient.output import AlsaOutput
    try:
        out = AlsaOutput("null", 48000, 128, 3)
        out.open()
        out.close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not alsa_null(), reason="no alsa-lib or ALSA null device")
def test_the_engine_plays_in_short_blocks_straight_to_alsa():
    # the band's profile: Csound's block and the output from the config, no aplay and no pipe
    e = Engine("null", 8, 0.0, block=128, output="alsa", period_ms=2.0)
    assert e.latency() == pytest.approx(0.008 + 128 / 48000, abs=0.001)
    e.start()
    try:
        t0 = time.monotonic()
        while e.time() < 0.5 and time.monotonic() - t0 < 5:
            time.sleep(0.05)
        assert e.time() >= 0.5 and e.error is None
        assert e.out.granted()["period"] > 0
    finally:
        e.stop()
