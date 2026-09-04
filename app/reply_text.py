"""One rule, one place: model *thought* parts never become visible text.

Gemini native thinking (issue #76, ADR-0010) arrives as
``Part(text=..., thought=True)`` *inside the same event content as the
reply*. Every place that turns a voice agent's event parts into text she
sees — the live reply builder (``app.chat``) and the re-opened-transcript
replay (``app.history``) — routes through here, so a future edit cannot
fix one path and miss the other. This is the safety guarantee ADR-0010
calls out; ``include_thoughts=False`` on the planner is configuration on
top of it.

Not used for *user* content (``app.guard`` reads that directly): her own
message never carries a thought part.
"""

from __future__ import annotations

from typing import Iterable


def visible_texts(parts: Iterable) -> list[str]:
    """The ``.text`` of every part that is real reply text — i.e. has text
    and is not a model thought part."""
    return [
        part.text
        for part in (parts or [])
        if part.text and not getattr(part, "thought", None)
    ]
