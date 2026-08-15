#!/usr/bin/env python3
"""Deterministic session manager for Rapid Domain Mastery.

The manager keeps a physical separation between learner-owned and
coach-owned artifacts:

* ``student/`` holds the learner's attempts and answers.
* ``coach/`` holds model answers, rubrics, and feedback.
* ``shared/questions/`` holds questions that both sides are allowed to see.

The commands in this module enforce the "student first, coach second"
barrier. Coach artifacts for a phase cannot be written or revealed until the
corresponding learner artifact is non-empty, and question feedback cannot be
written or revealed until the learner answer has been submitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


SCHEMA_VERSION = 1
PHASES = {1, 2, 3, 4}
PHASE_BARRIER_PHASES = {1, 3, 4}
QUESTION_PHASE = 2


class SessionError(Exception):
    """Raised when a requested operation violates the session contract."""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
    temp.replace(path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_nonempty_text(path: Path, label: str) -> None:
    if not path.exists():
        raise SessionError(f"{label} does not exist: {path}")
    if not path.is_file():
        raise SessionError(f"{label} is not a file: {path}")
    if not path.read_text(encoding="utf-8").strip():
        raise SessionError(f"{label} is empty: {path}")


def _write_or_copy(
    dest: Path,
    *,
    text: Optional[str],
    source: Optional[Path],
    label: str,
) -> None:
    if text is not None and source is not None:
        raise SessionError("pass either --text or --from-file, not both")

    dest.parent.mkdir(parents=True, exist_ok=True)
    if source is not None:
        _require_nonempty_text(source, label)
        shutil.copyfile(source, dest)
    elif text is not None:
        if not text.strip():
            raise SessionError(f"{label} must not be empty")
        dest.write_text(text.strip() + "\n", encoding="utf-8")
    else:
        _require_nonempty_text(dest, label)


def _new_state(goal: str, budget: str, materials: Iterable[Path]) -> Dict[str, Any]:
    manifest = []
    for material in materials:
        resolved = material.resolve()
        if not resolved.exists():
            raise SessionError(f"material does not exist: {resolved}")
        entry: Dict[str, Any] = {
            "path": str(resolved),
            "name": resolved.name,
            "type": "file" if resolved.is_file() else "directory",
        }
        if resolved.is_file():
            entry["sha256"] = _sha256_file(resolved)
        manifest.append(entry)

    phases: Dict[str, Any] = {
        "1": {
            "status": "in_progress",
            "barrier": {
                "student_file": None,
                "coach_file": None,
                "unlocked": False,
            },
        },
        "2": {"status": "pending", "questions": {}},
        "3": {
            "status": "pending",
            "barrier": {
                "student_file": None,
                "coach_file": None,
                "unlocked": False,
            },
        },
        "4": {
            "status": "pending",
            "barrier": {
                "student_file": None,
                "coach_file": None,
                "unlocked": False,
            },
        },
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "id": "rdm-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "created_at": utcnow(),
        "goal": goal.strip(),
        "time_budget": budget.strip(),
        "materials": manifest,
        "current_phase": 1,
        "phases": phases,
    }


def init_session(output: Path, goal: str, budget: str, materials: Iterable[Path]) -> None:
    output = output.resolve()
    state_path = output / "state" / "session.json"
    if state_path.exists():
        raise SessionError(f"session already exists: {output}")

    for rel in (
        "student/attempts",
        "student/answers",
        "student/notes",
        "coach/phase-artifacts",
        "coach/feedback",
        "shared/questions",
        "state",
    ):
        (output / rel).mkdir(parents=True, exist_ok=True)

    state = _new_state(goal, budget, materials)
    _write_json(state_path, state)
    print(f"initialized session: {output}")


def load_state(session: Path) -> Dict[str, Any]:
    state_path = session / "state" / "session.json"
    if not state_path.exists():
        raise SessionError(f"not a session (missing {state_path}): {session}")
    state = _load_json(state_path)
    if state.get("schema_version") != SCHEMA_VERSION:
        raise SessionError(
            f"unsupported session schema: {state.get('schema_version')}; expected {SCHEMA_VERSION}"
        )
    return state


def save_state(session: Path, state: Dict[str, Any]) -> None:
    _write_json(session / "state" / "session.json", state)


def _phase_state(state: Dict[str, Any], phase: int) -> Dict[str, Any]:
    return state["phases"][str(phase)]


def _check_phase(phase: int) -> None:
    if phase not in PHASES:
        raise SessionError(f"phase must be one of {sorted(PHASES)}")


def _valid_id(value: str) -> None:
    if not value or not all(ch.isalnum() or ch in "-_" for ch in value):
        raise SessionError("id may only contain letters, digits, hyphens, and underscores")


def record_attempt(session: Path, phase: int, text: Optional[str], source: Optional[Path]) -> None:
    _check_phase(phase)
    if phase not in PHASE_BARRIER_PHASES:
        raise SessionError(f"phase {phase} does not use a phase-level attempt barrier")

    state = load_state(session)
    phase_data = _phase_state(state, phase)
    dest = session / "student" / "attempts" / f"phase{phase}.md"
    _write_or_copy(dest, text=text, source=source, label="attempt")
    phase_data["barrier"]["student_file"] = str(dest.relative_to(session))
    phase_data["barrier"]["unlocked"] = False
    save_state(session, state)
    print(f"recorded student attempt: {dest.relative_to(session)}")


def save_phase_artifact(
    session: Path,
    phase: int,
    text: Optional[str],
    source: Optional[Path],
) -> None:
    _check_phase(phase)
    if phase not in PHASE_BARRIER_PHASES:
        raise SessionError(f"phase {phase} does not use a phase-level artifact barrier")

    state = load_state(session)
    phase_data = _phase_state(state, phase)
    barrier = phase_data["barrier"]
    student_file = barrier.get("student_file")
    if not student_file:
        raise SessionError(f"phase {phase} has no student attempt; record one first")
    _require_nonempty_text(session / student_file, "student attempt")

    dest = session / "coach" / "phase-artifacts" / f"phase{phase}.md"
    _write_or_copy(dest, text=text, source=source, label="phase artifact")
    barrier["coach_file"] = str(dest.relative_to(session))
    barrier["unlocked"] = True
    phase_data["status"] = "reviewed"
    save_state(session, state)
    print(f"saved coach artifact: {dest.relative_to(session)}")


def reveal_phase(session: Path, phase: int) -> None:
    _check_phase(phase)
    state = load_state(session)
    phase_data = _phase_state(state, phase)
    barrier = phase_data["barrier"]
    if not barrier.get("unlocked") or not barrier.get("coach_file"):
        raise SessionError(
            f"phase {phase} is still locked; submit and review the student attempt before revealing coach content"
        )
    coach_file = session / barrier["coach_file"]
    _require_nonempty_text(coach_file, "coach artifact")
    print(coach_file.read_text(encoding="utf-8"), end="")


def start_question(
    session: Path,
    question_id: str,
    title: str,
    text: Optional[str],
    source: Optional[Path],
) -> None:
    _valid_id(question_id)
    state = load_state(session)
    questions = _phase_state(state, QUESTION_PHASE)["questions"]
    if question_id in questions:
        raise SessionError(f"question already exists: {question_id}")

    dest = session / "shared" / "questions" / f"{question_id}.md"
    _write_or_copy(dest, text=text, source=source, label="question")
    questions[question_id] = {
        "id": question_id,
        "phase": QUESTION_PHASE,
        "title": title.strip(),
        "question_file": str(dest.relative_to(session)),
        "status": "open",
        "answer_file": None,
        "feedback_file": None,
        "submitted_at": None,
        "reviewed_at": None,
    }
    save_state(session, state)
    print(f"started question: {question_id}")


def _question(state: Dict[str, Any], question_id: str) -> Dict[str, Any]:
    questions = _phase_state(state, QUESTION_PHASE)["questions"]
    if question_id not in questions:
        raise SessionError(f"unknown question: {question_id}")
    return questions[question_id]


def submit_answer(
    session: Path,
    question_id: str,
    text: Optional[str],
    source: Optional[Path],
) -> None:
    state = load_state(session)
    question = _question(state, question_id)
    if question["status"] != "open":
        raise SessionError(f"question {question_id} is already {question['status']}")

    dest = session / "student" / "answers" / f"{question_id}.md"
    _write_or_copy(dest, text=text, source=source, label="answer")
    question["status"] = "submitted"
    question["answer_file"] = str(dest.relative_to(session))
    question["submitted_at"] = utcnow()
    save_state(session, state)
    print(f"submitted answer for question: {question_id}")


def save_feedback(
    session: Path,
    question_id: str,
    text: Optional[str],
    source: Optional[Path],
) -> None:
    state = load_state(session)
    question = _question(state, question_id)
    if question["status"] != "submitted":
        raise SessionError(
            f"question {question_id} is {question['status']}; submit an answer before saving feedback"
        )

    dest = session / "coach" / "feedback" / f"{question_id}.md"
    _write_or_copy(dest, text=text, source=source, label="feedback")
    question["status"] = "reviewed"
    question["feedback_file"] = str(dest.relative_to(session))
    question["reviewed_at"] = utcnow()
    save_state(session, state)
    print(f"saved feedback for question: {question_id}")


def reveal_feedback(session: Path, question_id: str) -> None:
    state = load_state(session)
    question = _question(state, question_id)
    if question["status"] != "reviewed":
        raise SessionError(
            f"question {question_id} is {question['status']}; feedback is not available yet"
        )
    feedback_file = session / question["feedback_file"]
    _require_nonempty_text(feedback_file, "feedback")
    print(feedback_file.read_text(encoding="utf-8"), end="")


def finish_phase(session: Path, phase: int) -> None:
    _check_phase(phase)
    state = load_state(session)
    phase_data = _phase_state(state, phase)

    if phase in PHASE_BARRIER_PHASES:
        if not phase_data["barrier"].get("unlocked"):
            raise SessionError(
                f"phase {phase} is not complete; the student attempt must be reviewed first"
            )
    elif phase == QUESTION_PHASE:
        questions = phase_data["questions"]
        if not questions:
            raise SessionError("phase 2 has no questions")
        for question in questions.values():
            if question["status"] != "reviewed":
                raise SessionError(
                    f"question {question['id']} is {question['status']}; all questions must be reviewed"
                )

    phase_data["status"] = "completed"
    if phase < 4:
        state["current_phase"] = phase + 1
    else:
        state["current_phase"] = None
    save_state(session, state)
    print(f"completed phase {phase}")


def _copy_tree(src: Path, dst: Path) -> None:
    if src.exists():
        shutil.copytree(src, dst, dirs_exist_ok=True)


def export_session(session: Path, output: Path) -> None:
    state = load_state(session)
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SessionError(f"export directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    _copy_tree(session / "student", output / "student")
    _copy_tree(session / "shared", output / "shared")

    for phase, phase_data in state["phases"].items():
        if phase in {str(p) for p in PHASE_BARRIER_PHASES}:
            barrier = phase_data["barrier"]
            if barrier.get("unlocked") and barrier.get("coach_file"):
                coach_src = session / barrier["coach_file"]
                _require_nonempty_text(coach_src, "coach artifact")
                coach_dst = output / barrier["coach_file"]
                coach_dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(coach_src, coach_dst)
        elif phase == str(QUESTION_PHASE):
            for question in phase_data["questions"].values():
                if question["status"] == "reviewed" and question.get("feedback_file"):
                    feedback_src = session / question["feedback_file"]
                    _require_nonempty_text(feedback_src, "feedback")
                    feedback_dst = output / question["feedback_file"]
                    feedback_dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(feedback_src, feedback_dst)

    _write_json(output / "state" / "session.json", state)
    print(f"exported unlocked session content to: {output}")


def check_session(session: Path) -> None:
    state = load_state(session)
    errors = []

    for phase in PHASES:
        phase_data = _phase_state(state, phase)
        if phase in PHASE_BARRIER_PHASES:
            barrier = phase_data["barrier"]
            student_file = barrier.get("student_file")
            coach_file = barrier.get("coach_file")
            if barrier.get("unlocked") and (not student_file or not coach_file):
                errors.append(f"phase {phase} is unlocked but missing a barrier path")
            if coach_file and not barrier.get("unlocked"):
                errors.append(f"phase {phase} has coach content while still locked")
        elif phase == QUESTION_PHASE:
            for question in phase_data["questions"].values():
                if question["status"] == "reviewed" and not question.get("answer_file"):
                    errors.append(f"question {question['id']} is reviewed without an answer")
                if question.get("feedback_file") and question["status"] != "reviewed":
                    errors.append(f"question {question['id']} has feedback but is not reviewed")

    if errors:
        raise SessionError("; ".join(errors))
    print("session integrity check passed")


def _status_dict(state: Dict[str, Any], session: Path) -> Dict[str, Any]:
    summary = {
        "id": state["id"],
        "goal": state["goal"],
        "time_budget": state["time_budget"],
        "current_phase": state["current_phase"],
        "phases": {},
    }
    for phase in PHASES:
        phase_data = _phase_state(state, phase)
        if phase == QUESTION_PHASE:
            questions = phase_data["questions"]
            summary["phases"][str(phase)] = {
                "status": phase_data["status"],
                "question_count": len(questions),
                "questions": {
                    qid: q["status"] for qid, q in questions.items()
                },
            }
        else:
            barrier = phase_data["barrier"]
            summary["phases"][str(phase)] = {
                "status": phase_data["status"],
                "barrier": {
                    "unlocked": barrier.get("unlocked", False),
                    "student_file": barrier.get("student_file"),
                    "coach_file": barrier.get("coach_file"),
                },
            }
    return summary


def status_session(session: Path) -> None:
    state = load_state(session)
    print(json.dumps(_status_dict(state, session), indent=2, sort_keys=True))


def _add_session_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--session", default=".rdm", help="session directory (default: .rdm)")


def _add_text_or_file(parser: argparse.ArgumentParser, label: str) -> None:
    parser.add_argument("--text", help=f"{label} content as a string")
    parser.add_argument(
        "--from-file",
        type=Path,
        dest="source",
        help=f"path to a file containing the {label}",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="session.py",
        description="Manage a Rapid Domain Mastery session with a coach/student barrier.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create a new session")
    init.add_argument("--output", default=".rdm", help="session directory (default: .rdm)")
    init.add_argument("--goal", required=True, help="learning goal")
    init.add_argument("--budget", default="", help="time budget")
    init.add_argument("--materials", nargs="*", default=[], help="material files or directories")

    status = sub.add_parser("status", help="show session status")
    _add_session_arg(status)

    check = sub.add_parser("check", help="check session integrity")
    _add_session_arg(check)

    record = sub.add_parser("record-attempt", help="record a phase-level student attempt")
    _add_session_arg(record)
    record.add_argument("--phase", type=int, required=True)
    _add_text_or_file(record, "attempt")

    phase_artifact = sub.add_parser("save-phase-artifact", help="save coach phase artifact after student attempt")
    _add_session_arg(phase_artifact)
    phase_artifact.add_argument("--phase", type=int, required=True)
    _add_text_or_file(phase_artifact, "phase artifact")

    reveal_phase_cmd = sub.add_parser("reveal-phase", help="reveal an unlocked coach phase artifact")
    _add_session_arg(reveal_phase_cmd)
    reveal_phase_cmd.add_argument("--phase", type=int, required=True)

    start = sub.add_parser("start-question", help="create a phase-2 question")
    _add_session_arg(start)
    start.add_argument("--id", dest="question_id", required=True)
    start.add_argument("--title", default="")
    _add_text_or_file(start, "question")

    submit = sub.add_parser("submit", help="submit a learner answer for a question")
    _add_session_arg(submit)
    submit.add_argument("--id", dest="question_id", required=True)
    _add_text_or_file(submit, "answer")

    feedback = sub.add_parser("save-feedback", help="save coach feedback after learner submission")
    _add_session_arg(feedback)
    feedback.add_argument("--id", dest="question_id", required=True)
    _add_text_or_file(feedback, "feedback")

    reveal_feedback_cmd = sub.add_parser("reveal-feedback", help="reveal reviewed question feedback")
    _add_session_arg(reveal_feedback_cmd)
    reveal_feedback_cmd.add_argument("--id", dest="question_id", required=True)

    finish = sub.add_parser("finish-phase", help="mark a phase complete")
    _add_session_arg(finish)
    finish.add_argument("--phase", type=int, required=True)

    export = sub.add_parser("export", help="export student work and unlocked coach content")
    _add_session_arg(export)
    export.add_argument("--output", required=True, help="export directory")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command

    try:
        if command == "init":
            init_session(
                Path(args.output),
                args.goal,
                args.budget,
                [Path(m) for m in args.materials],
            )
        elif command == "status":
            status_session(Path(args.session))
        elif command == "check":
            check_session(Path(args.session))
        elif command == "record-attempt":
            record_attempt(Path(args.session), args.phase, args.text, args.source)
        elif command == "save-phase-artifact":
            save_phase_artifact(Path(args.session), args.phase, args.text, args.source)
        elif command == "reveal-phase":
            reveal_phase(Path(args.session), args.phase)
        elif command == "start-question":
            start_question(Path(args.session), args.question_id, args.title, args.text, args.source)
        elif command == "submit":
            submit_answer(Path(args.session), args.question_id, args.text, args.source)
        elif command == "save-feedback":
            save_feedback(Path(args.session), args.question_id, args.text, args.source)
        elif command == "reveal-feedback":
            reveal_feedback(Path(args.session), args.question_id)
        elif command == "finish-phase":
            finish_phase(Path(args.session), args.phase)
        elif command == "export":
            export_session(Path(args.session), Path(args.output))
        else:
            parser.error(f"unknown command: {command}")
    except SessionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
