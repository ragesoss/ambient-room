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
