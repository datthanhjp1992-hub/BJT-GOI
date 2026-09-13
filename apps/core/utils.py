"""Small shared helpers used by multiple apps."""


def chunked(iterable, size):
    """Yield successive chunks of `size` items from iterable."""
    buf = []
    for item in iterable:
        buf.append(item)
        if len(buf) == size:
            yield buf
            buf = []
    if buf:
        yield buf
