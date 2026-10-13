"""Global quiet-mode toggle."""
QUIET = False

def set_quiet(on: bool):
    global QUIET
    QUIET = on

def is_quiet() -> bool:
    return QUIET

def say(*a, **k):
    """Print unless quiet."""
    if not QUIET:
        print(*a, **k)
