"""Request-owned reply plans; generated content is never a delivered conversation."""
from dataclasses import dataclass, field
import uuid


@dataclass
class ReplyPlan:
    key: str
    target: object
    token: object
    bubbles: list
    stickers: list
    voice: bool = False
    text: str = ''
    others: list = field(default_factory=list)
    id: str = field(default_factory=lambda:uuid.uuid4().hex)
    started: bool = False
    finished: bool = False
    results: list = field(default_factory=list)
    sticker_only: bool = False
    sticker_limit: object = None


def owned(event,runtime):
    token=event.get_extra('_dsh_work')
    return token is not None and token.runtime is runtime and runtime.requests.get(token.key)==token.request and runtime.epochs.get(token.key,0)==token.epoch
