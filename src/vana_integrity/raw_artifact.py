"""Raw artifact integrity — content-addressed SHA-256 digests."""

from __future__ import annotations

import hashlib
from typing import Any


def compute_content_digest(content: bytes | str) -> str:
    """Return SHA-256 hex digest of raw artifact content."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def format_input_ref(content: bytes | str, ref: str) -> str:
    """Format processing_run.input_ref as ``sha256:<hex>|ref:<uri-or-path>``."""
    digest = compute_content_digest(content)
    return f"sha256:{digest}|ref:{ref}"


def parse_input_ref(input_ref: str) -> dict[str, str]:
    """Parse an input_ref string into digest and ref components."""
    parts = dict(part.split(":", 1) for part in input_ref.split("|") if ":" in part)
    return {"sha256": parts.get("sha256", ""), "ref": parts.get("ref", "")}


def extract_raw_artifact(payload: dict[str, Any]) -> tuple[str, str]:
    """Return (content, ref) from payload raw_artifact block."""
    raw = payload.get("raw_artifact") or {}
    content = raw.get("content")
    ref = raw.get("ref")
    if content is None:
        raise ValueError("raw_artifact.content is required")
    if not ref:
        raise ValueError("raw_artifact.ref is required")
    return str(content), str(ref)
