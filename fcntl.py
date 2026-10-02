"""Cross-platform Windows compatibility shim for the Unix fcntl module.

On Unix/Linux/Docker platforms, Python provides a built-in C extension module
for fcntl. On Windows, fcntl does not exist in standard library. This shim
provides dummy no-op implementations of flock, fcntl, and ioctl along with the
standard flock operation constants so code runs cleanly cross-platform without
crashing on Windows.
"""

LOCK_SH = 1
LOCK_EX = 2
LOCK_NB = 4
LOCK_UN = 8


def flock(fd, operation):
    """File lock operation (no-op on Windows fallback)."""
    pass


def fcntl(fd, op, arg=0):
    """File control operation (no-op on Windows fallback)."""
    return 0


def ioctl(fd, op, arg=0, mutate_flag=True):
    """I/O control operation (no-op on Windows fallback)."""
    return 0
