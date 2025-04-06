from datetime import datetime
from dataclasses import dataclass, field

from blog.config import Settings


@dataclass
class CliContext:
    settings: Settings | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
