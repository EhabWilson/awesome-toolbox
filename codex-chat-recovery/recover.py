#!/usr/bin/env python3
"""Recover readable chat transcripts from Codex JSONL session files.

The tool is intentionally read-only with respect to Codex data. It can scan,
display, and export transcripts, but never edits the source session files.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional, Sequence


@dataclass
class ChatMessage:
    role: str
    text: str
    timestamp: Optional[str] = None
    phase: Optional[str] = None


@dataclass
class RecoveredSession:
    source: str
    session_id: Optional[str] = None
    timestamp: Optional[str] = None
    cwd: Optional[str] = None
    messages: list[ChatMessage] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        for message in self.messages:
            if message.role != "user":
                continue
            for line in message.text.splitlines():
                line = line.strip()
                if line and not line.startswith("<environment_context"):
                    return _shorten(line, 72)
        return Path(self.source).stem


def default_sessions_dir() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    root = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return root / "sessions"


def discover_session_files(source: Path) -> list[Path]:
    source = source.expanduser()
    if source.is_file():
        return [source]
    if not source.exists():
        raise FileNotFoundError(f"Source does not exist: {source}")
    if not source.is_dir():
        raise ValueError(f"Source is neither a file nor directory: {source}")
    return sorted(source.rglob("*.jsonl"), key=_mtime, reverse=True)


def recover_session(path: Path, include_commentary: bool = False) -> RecoveredSession:
    session = RecoveredSession(source=str(path.resolve()))
    response_messages: list[ChatMessage] = []
    fallback_messages: list[ChatMessage] = []

    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                session.parse_errors.append(f"line {line_number}: {exc.msg}")
                continue
            if not isinstance(record, dict):
                session.parse_errors.append(f"line {line_number}: expected a JSON object")
                continue

            record_type = record.get("type")
            payload = record.get("payload")
            if not isinstance(payload, dict):
                continue

            if record_type == "session_meta":
                session.session_id = _string(payload.get("id") or payload.get("session_id"))
                session.timestamp = _string(payload.get("timestamp") or record.get("timestamp"))
                session.cwd = _string(payload.get("cwd"))
                continue

            if record_type == "response_item" and payload.get("type") == "message":
                message = _response_message(payload, _string(record.get("timestamp")))
                if message and _should_include(message, include_commentary):
                    response_messages.append(message)
                continue

            if record_type == "event_msg":
                message = _event_message(payload, _string(record.get("timestamp")))
                if message and _should_include(message, include_commentary):
                    fallback_messages.append(message)

    # event_msg user_message/agent_message entries duplicate response_item messages
    # in common Codex files, so they are only used for older/event-only logs.
    session.messages = response_messages if response_messages else fallback_messages
    if not session.timestamp:
        session.timestamp = _timestamp_from_filename(path.name)
    return session


def _response_message(payload: dict[str, Any], timestamp: Optional[str]) -> Optional[ChatMessage]:
    role = payload.get("role")
    if role not in {"user", "assistant"}:
        return None
    text = _content_text(payload.get("content"))
    if not text.strip():
        return None
    if role == "user" and _is_context_only_user_message(text):
        return None
    return ChatMessage(
        role=role,
        text=text,
        timestamp=timestamp,
        phase=_string(payload.get("phase")),
    )


def _event_message(payload: dict[str, Any], timestamp: Optional[str]) -> Optional[ChatMessage]:
    event_type = payload.get("type")
    if event_type == "user_message":
        role = "user"
    elif event_type == "agent_message":
        role = "assistant"
    else:
        return None
    text = payload.get("message")
    if not isinstance(text, str) or not text.strip():
        return None
    return ChatMessage(
        role=role,
        text=text,
        timestamp=timestamp,
        phase=_string(payload.get("phase")),
    )


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    chunks: list[str] = []
    for part in content:
        if isinstance(part, str):
            chunks.append(part)
            continue
        if not isinstance(part, dict):
            continue
        for key in ("text", "input_text", "output_text"):
            value = part.get(key)
            if isinstance(value, str):
                chunks.append(value)
                break
    return "\n".join(chunks)


def _should_include(message: ChatMessage, include_commentary: bool) -> bool:
    return include_commentary or not (
        message.role == "assistant" and message.phase == "commentary"
    )


def _is_context_only_user_message(text: str) -> bool:
    """Ignore app-injected context records that are not user-authored chat turns."""
    remainder = text.strip()
    block = re.compile(
        r"^<(environment_context|recommended_plugins)>.*?</\1>\s*",
        flags=re.DOTALL,
    )
    while remainder:
        match = block.match(remainder)
        if not match:
            return False
        remainder = remainder[match.end() :].strip()
    return True


def session_to_markdown(session: RecoveredSession) -> str:
    lines = [
        f"# {session.title}",
        "",
        f"- Session ID: `{session.session_id or 'unknown'}`",
        f"- Started: `{session.timestamp or 'unknown'}`",
        f"- Working directory: `{session.cwd or 'unknown'}`",
        f"- Source: `{session.source}`",
        f"- Parse warnings: `{len(session.parse_errors)}`",
        "",
    ]
    if not session.messages:
        lines.extend(["_No user or assistant messages were recovered._", ""])
    for message in session.messages:
        label = "User" if message.role == "user" else "Assistant"
        if message.phase:
            label += f" · {message.phase}"
        lines.extend([f"## {label}", "", message.text.rstrip(), ""])
    if session.parse_errors:
        lines.extend(["## Recovery warnings", ""])
        lines.extend(f"- {warning}" for warning in session.parse_errors)
        lines.append("")
    return "\n".join(lines)


def session_to_json(session: RecoveredSession) -> str:
    return json.dumps(asdict(session), ensure_ascii=False, indent=2) + "\n"


def scan_sessions(
    files: Iterable[Path],
    include_commentary: bool = False,
    query: Optional[str] = None,
) -> Iterator[RecoveredSession]:
    needle = query.casefold() if query else None
    for path in files:
        session = recover_session(path, include_commentary=include_commentary)
        if needle:
            haystack = "\n".join(
                [session.title, session.cwd or ""] + [message.text for message in session.messages]
            ).casefold()
            if needle not in haystack:
                continue
        yield session


def export_sessions(
    sessions: Iterable[RecoveredSession], output_dir: Path, export_format: str
) -> tuple[int, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    warnings = 0
    extension = ".md" if export_format == "markdown" else ".json"
    for index, session in enumerate(sessions, start=1):
        timestamp = _filename_timestamp(session.timestamp) or f"session-{index:04d}"
        identity = session.session_id or Path(session.source).stem
        filename = f"{timestamp}-{_safe_filename(identity)}{extension}"
        destination = _unique_path(output_dir / filename)
        body = (
            session_to_markdown(session)
            if export_format == "markdown"
            else session_to_json(session)
        )
        destination.write_text(body, encoding="utf-8")
        written += 1
        warnings += len(session.parse_errors)
    return written, warnings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Recover readable transcripts from Codex JSONL session files."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="List recoverable sessions")
    _add_source_argument(scan)
    scan.add_argument("--limit", type=_positive_int, default=30)
    scan.add_argument("--query", help="Only show sessions containing this text")
    scan.add_argument("--include-commentary", action="store_true")

    show = subparsers.add_parser("show", help="Print one recovered chat as Markdown")
    show.add_argument("file", type=Path, help="A Codex rollout .jsonl file")
    show.add_argument("--include-commentary", action="store_true")

    export = subparsers.add_parser("export", help="Export recovered chats")
    _add_source_argument(export)
    export.add_argument("--output", "-o", type=Path, required=True)
    export.add_argument("--format", choices=("markdown", "json"), default="markdown")
    export.add_argument("--query", help="Only export sessions containing this text")
    export.add_argument("--include-commentary", action="store_true")
    return parser


def _add_source_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=default_sessions_dir(),
        help="Codex sessions directory or one .jsonl file (default: ~/.codex/sessions)",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "show":
            session = recover_session(args.file, include_commentary=args.include_commentary)
            sys.stdout.write(session_to_markdown(session))
            return 0 if session.messages else 2

        files = discover_session_files(args.source)
        sessions = scan_sessions(
            files,
            include_commentary=args.include_commentary,
            query=getattr(args, "query", None),
        )
        if args.command == "scan":
            print("STARTED\tMESSAGES\tWARNINGS\tTITLE\tFILE")
            count = 0
            for session in sessions:
                if count >= args.limit:
                    break
                print(
                    "\t".join(
                        [
                            session.timestamp or "unknown",
                            str(len(session.messages)),
                            str(len(session.parse_errors)),
                            session.title.replace("\t", " "),
                            session.source,
                        ]
                    )
                )
                count += 1
            return 0

        written, warnings = export_sessions(sessions, args.output, args.format)
        print(f"Recovered {written} session(s) into {args.output} ({warnings} warning(s)).")
        return 0 if written else 2
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError, PermissionError, ValueError) as exc:
        parser.error(str(exc))
    return 2


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _string(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value else None


def _shorten(text: str, width: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact if len(compact) <= width else compact[: width - 1].rstrip() + "…"


def _timestamp_from_filename(filename: str) -> Optional[str]:
    match = re.search(r"rollout-(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})", filename)
    return match.group(1).replace("T", "T", 1) if match else None


def _filename_timestamp(timestamp: Optional[str]) -> Optional[str]:
    if not timestamp:
        return None
    normalized = timestamp.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).strftime("%Y%m%d-%H%M%S")
    except ValueError:
        match = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}[-:]\d{2}[-:]\d{2}", timestamp)
        return re.sub(r"[-:T]", "", match.group(0)) if match else None


def _safe_filename(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    return (clean or "recovered")[:80]


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 10_000):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise ValueError(f"Could not create a unique export path for: {path}")


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
