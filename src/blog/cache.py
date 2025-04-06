from functools import wraps
from pathlib import Path

from blog.exceptions import Abort


CACHE_DIR: Path = Path.home() / ".local/share/blog"


def init_cache(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            CACHE_DIR.mkdir(exist_ok=True, parents=True)
            info_file = CACHE_DIR / "info.txt"
            info_file.write_text(
                """
                This directory is used by the.dusktreader blog for its cache.
                """
            )
        except Exception:
            raise Abort(
                """
                Cache directory {cache_dir} doesn't exist, is not writable,
                or could not be created.

                Please check your home directory permissions and try again.
                """,
                subject="Non-writable cache dir",
                log_message="Non-writable cache dir",
            )
        return func(*args, **kwargs)

    return wrapper
