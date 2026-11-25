"""
Split long documents into small overlapping pieces ("chunks").

Why? The search compares the QUESTION with each piece. Small pieces = precise matches,
and we only send the few relevant pieces to the LLM (cheaper, less distraction).
Why overlap? So a sentence cut at the border still appears whole in one of the chunks.

Ramen picture: you don't hand the chef the whole cookbook, you tear out the 3 pages they need.
"""

import re


def chunk_text(text, max_chars=800, overlap_chars=150):
    """
    Split on paragraphs first (keeps ideas together), then pack paragraphs into chunks of
    at most max_chars. Each new chunk starts with the last overlap_chars of the previous one.
    A single paragraph longer than max_chars is cut into pieces.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces = []
    for p in paragraphs:
        while len(p) > max_chars:
            pieces.append(p[:max_chars])
            p = p[max_chars - overlap_chars:]
        pieces.append(p)

    chunks, current = [], ""
    for piece in pieces:
        candidate = f"{current}\n\n{piece}" if current else piece
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            tail = current[-overlap_chars:] if overlap_chars else ""
            current = f"{tail}\n\n{piece}" if tail else piece
            if len(current) > max_chars:          # overlap pushed it over: drop the overlap
                current = piece
    if current:
        chunks.append(current)
    return chunks
