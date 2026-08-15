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


SCHEMA_VERSION = 4
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


def _read_text(path: Path, label: str) -> str:
    _require_nonempty_text(path, label)
    return path.read_text(encoding="utf-8")


def _require_reasoned_answer(path: Path) -> None:
    text = _read_text(path, "answer")
    nonempty_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(nonempty_lines) < 2:
        raise SessionError(
            "answer must include at least two non-empty lines: a conclusion and the reasoning behind it"
        )


def _copy_if_needed(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() != dst.resolve():
        shutil.copyfile(src, dst)


def _phase_locked_path(session: Path, phase: int) -> Path:
    return session / "state" / "locked" / "phase-artifacts" / f"phase{phase}.md"


def _phase_revealed_path(session: Path, phase: int) -> Path:
    return session / "coach" / "phase-artifacts" / f"phase{phase}.md"


def _question_round_answer_path(session: Path, question_id: str, round_no: int) -> Path:
    return session / "student" / "answers" / f"{question_id}.round{round_no}.md"


def _question_locked_feedback_path(session: Path, question_id: str, round_no: int) -> Path:
    return session / "state" / "locked" / "feedback" / question_id / f"round{round_no}.md"


def _question_revealed_feedback_path(session: Path, question_id: str, round_no: int) -> Path:
    return session / "coach" / "feedback" / question_id / f"round{round_no}.md"


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


def _new_state(
    goal: str,
    budget: str,
    materials: Iterable[Path],
    student_persona: str,
    coach_persona: str,
    assessment_mode: str,
    workspace_root: str,
) -> Dict[str, Any]:
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
                "locked_file": None,
                "revealed_file": None,
                "revealed": False,
            },
        },
        "2": {"status": "pending", "questions": {}},
        "3": {
            "status": "pending",
            "barrier": {
                "student_file": None,
                "locked_file": None,
                "revealed_file": None,
                "revealed": False,
            },
        },
        "4": {
            "status": "pending",
            "barrier": {
                "student_file": None,
                "locked_file": None,
                "revealed_file": None,
                "revealed": False,
            },
        },
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "id": "rdm-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "created_at": utcnow(),
        "goal": goal.strip(),
        "time_budget": budget.strip(),
        "student_persona": student_persona.strip(),
        "coach_persona": coach_persona.strip(),
        "assessment_mode": assessment_mode,
        "workspace_root": workspace_root.strip(),
        "materials": manifest,
        "current_phase": 1,
        "phases": phases,
    }


def init_session(
    output: Path,
    goal: str,
    budget: str,
    materials: Iterable[Path],
    student_persona: str,
    coach_persona: str,
    assessment_mode: str,
    workspace_root: str,
) -> None:
    output = output.resolve()
    state_path = output / "state" / "session.json"
    if state_path.exists():
        raise SessionError(f"session already exists: {output}")

    materials = list(materials)
    if not materials:
        raise SessionError("at least one material path is required")
    if len(materials) == 1:
        print(
            "warning: only one material path was provided; add multiple perspectives when possible",
            file=sys.stderr,
        )

    for rel in (
        "student/attempts",
        "student/answers",
        "student/artifacts",
        "student/notes",
        "coach/phase-artifacts",
        "coach/feedback",
        "shared/questions",
        "shared/tasks",
        "shared/runtime-feedback",
        "state/locked/phase-artifacts",
        "state/locked/feedback",
        "state",
    ):
        (output / rel).mkdir(parents=True, exist_ok=True)

    state = _new_state(
        goal,
        budget,
        materials,
        student_persona,
        coach_persona,
        assessment_mode,
        workspace_root,
    )
    _write_json(state_path, state)
    print(f"initialized session: {output}")


def _migrate_state(state: Dict[str, Any]) -> Dict[str, Any]:
    version = state.get("schema_version")
    if version not in {1, 2, 3, 4}:
        raise SessionError(
            f"unsupported session schema: {version}; expected one of [1, 2, 3, 4]"
        )

    if version in {1, 2, 3}:
        for phase in PHASE_BARRIER_PHASES:
            barrier = state["phases"][str(phase)]["barrier"]
            if version == 1:
                revealed = barrier.get("unlocked")
                if revealed is None:
                    revealed = bool(barrier.get("coach_file"))
            else:
                revealed = barrier.get("revealed", False)
            coach_file = barrier.get("coach_file")
            if coach_file:
                barrier["locked_file"] = coach_file.replace("coach/phase-artifacts/", "state/locked/phase-artifacts/")
                barrier["revealed_file"] = coach_file if revealed else None
            else:
                barrier["locked_file"] = None
                barrier["revealed_file"] = None
            barrier["revealed"] = bool(revealed)
            barrier.pop("unlocked", None)
            barrier.pop("coach_file", None)

        for question in state["phases"][str(QUESTION_PHASE)]["questions"].values():
            feedback_file = question.get("feedback_file")
            revealed = question.get("revealed")
            if revealed is None:
                revealed = bool(feedback_file and question.get("status") == "reviewed")
            question.setdefault("round", 1)
            question.setdefault("completed_round", 0)
            question.setdefault("rounds", [])
            answer_file = question.get("answer_file")
            if answer_file and not question["rounds"]:
                round_entry = {
                    "round": 1,
                    "answer_file": answer_file,
                    "locked_feedback_file": feedback_file.replace("coach/feedback/", "state/locked/feedback/") if feedback_file else None,
                    "revealed_feedback_file": feedback_file if revealed else None,
                    "revealed": bool(revealed),
                    "submitted_at": question.get("submitted_at"),
                    "reviewed_at": question.get("reviewed_at"),
                }
                question["rounds"].append(round_entry)
                question["completed_round"] = 1 if feedback_file else 0
            question.pop("answer_file", None)
            question.pop("feedback_file", None)
            question.pop("submitted_at", None)
            question.pop("reviewed_at", None)
            question["revealed"] = bool(revealed)

        state["schema_version"] = 4

    state.setdefault("student_persona", "")
    state.setdefault("coach_persona", "")
    state.setdefault("assessment_mode", "conceptual")
    state.setdefault("workspace_root", "")

    for phase in PHASE_BARRIER_PHASES:
        barrier = state["phases"][str(phase)]["barrier"]
        barrier.setdefault("student_file", None)
        barrier.setdefault("locked_file", None)
        barrier.setdefault("revealed_file", None)
        barrier.setdefault("revealed", False)

    for question in state["phases"][str(QUESTION_PHASE)]["questions"].values():
        question.setdefault("round", 1)
        question.setdefault("completed_round", 0)
        question.setdefault("rounds", [])
        question.setdefault("revealed", False)

    return state


def load_state(session: Path) -> Dict[str, Any]:
    state_path = session / "state" / "session.json"
    if not state_path.exists():
        raise SessionError(f"not a session (missing {state_path}): {session}")
    original = _load_json(state_path)
    state = _migrate_state(original)
    if state != original:
        _write_json(state_path, state)
    return state


def save_state(session: Path, state: Dict[str, Any]) -> None:
    _write_json(session / "state" / "session.json", state)


def _phase_state(state: Dict[str, Any], phase: int) -> Dict[str, Any]:
    return state["phases"][str(phase)]


def _check_phase(phase: int) -> None:
    if phase not in PHASES:
        raise SessionError(f"phase must be one of {sorted(PHASES)}")


def _require_current_phase(state: Dict[str, Any], phase: int, action: str) -> None:
    current_phase = state.get("current_phase")
    if current_phase != phase:
        raise SessionError(
            f"{action} requires current phase {phase}; current phase is {current_phase}"
        )


def _valid_id(value: str) -> None:
    if not value or not all(ch.isalnum() or ch in "-_" for ch in value):
        raise SessionError("id may only contain letters, digits, hyphens, and underscores")


def record_attempt(session: Path, phase: int, text: Optional[str], source: Optional[Path]) -> None:
    _check_phase(phase)
    if phase not in PHASE_BARRIER_PHASES:
        raise SessionError(f"phase {phase} does not use a phase-level attempt barrier")

    state = load_state(session)
    _require_current_phase(state, phase, "record-attempt")
    phase_data = _phase_state(state, phase)
    dest = session / "student" / "attempts" / f"phase{phase}.md"
    _write_or_copy(dest, text=text, source=source, label="attempt")
    phase_data["barrier"]["student_file"] = str(dest.relative_to(session))
    phase_data["barrier"]["revealed"] = False
    phase_data["barrier"]["revealed_file"] = None
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
    _require_current_phase(state, phase, "save-phase-artifact")
    phase_data = _phase_state(state, phase)
    barrier = phase_data["barrier"]
    student_file = barrier.get("student_file")
    if not student_file:
        raise SessionError(f"phase {phase} has no student attempt; record one first")
    _require_nonempty_text(session / student_file, "student attempt")

    dest = _phase_locked_path(session, phase)
    _write_or_copy(dest, text=text, source=source, label="phase artifact")
    barrier["locked_file"] = str(dest.relative_to(session))
    barrier["revealed_file"] = None
    barrier["revealed"] = False
    phase_data["status"] = "reviewed"
    save_state(session, state)
    print(f"saved locked coach artifact: {dest.relative_to(session)}")


def reveal_phase(session: Path, phase: int) -> None:
    _check_phase(phase)
    state = load_state(session)
    _require_current_phase(state, phase, "reveal-phase")
    phase_data = _phase_state(state, phase)
    barrier = phase_data["barrier"]
    if not barrier.get("locked_file"):
        raise SessionError(
            f"phase {phase} is still locked; submit and review the student attempt before revealing coach content"
        )
    locked_file = session / barrier["locked_file"]
    _require_nonempty_text(locked_file, "coach artifact")
    revealed_file = _phase_revealed_path(session, phase)
    _copy_if_needed(locked_file, revealed_file)
    barrier["revealed"] = True
    barrier["revealed_file"] = str(revealed_file.relative_to(session))
    save_state(session, state)
    print(revealed_file.read_text(encoding="utf-8"), end="")


def start_question(
    session: Path,
    question_id: str,
    title: str,
    text: Optional[str],
    source: Optional[Path],
) -> None:
    _valid_id(question_id)
    state = load_state(session)
    _require_current_phase(state, QUESTION_PHASE, "start-question")
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
        "round": 1,
        "completed_round": 0,
        "rounds": [],
        "revealed": False,
    }
    _phase_state(state, QUESTION_PHASE)["status"] = "in_progress"
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
    _require_current_phase(state, QUESTION_PHASE, "submit")
    question = _question(state, question_id)
    if question["status"] != "open":
        raise SessionError(f"question {question_id} is already {question['status']}")

    round_no = int(question["round"])
    dest = _question_round_answer_path(session, question_id, round_no)
    _write_or_copy(dest, text=text, source=source, label="answer")
    _require_reasoned_answer(dest)
    question["status"] = "submitted"
    submitted_at = utcnow()
    rounds = question["rounds"]
    round_entry = None
    for existing in rounds:
        if existing["round"] == round_no:
            round_entry = existing
            break
    if round_entry is None:
        round_entry = {"round": round_no}
        rounds.append(round_entry)
    round_entry["answer_file"] = str(dest.relative_to(session))
    round_entry["submitted_at"] = submitted_at
    round_entry.setdefault("locked_feedback_file", None)
    round_entry.setdefault("revealed_feedback_file", None)
    round_entry["revealed"] = False
    save_state(session, state)
    print(f"submitted answer for question: {question_id} round {round_no}")


def save_feedback(
    session: Path,
    question_id: str,
    text: Optional[str],
    source: Optional[Path],
) -> None:
    state = load_state(session)
    _require_current_phase(state, QUESTION_PHASE, "save-feedback")
    question = _question(state, question_id)
    if question["status"] != "submitted":
        raise SessionError(
            f"question {question_id} is {question['status']}; submit an answer before saving feedback"
        )

    round_no = int(question["round"])
    round_entry = None
    for existing in question["rounds"]:
        if existing["round"] == round_no:
            round_entry = existing
            break
    if round_entry is None or not round_entry.get("answer_file"):
        raise SessionError(f"question {question_id} round {round_no} has no recorded answer")

    dest = _question_locked_feedback_path(session, question_id, round_no)
    _write_or_copy(dest, text=text, source=source, label="feedback")
    question["status"] = "reviewed"
    reviewed_at = utcnow()
    round_entry["locked_feedback_file"] = str(dest.relative_to(session))
    round_entry["revealed_feedback_file"] = None
    round_entry["reviewed_at"] = reviewed_at
    round_entry["revealed"] = False
    question["revealed"] = False
    save_state(session, state)
    print(f"saved locked feedback for question: {question_id} round {round_no}")


def reveal_feedback(session: Path, question_id: str) -> None:
    state = load_state(session)
    _require_current_phase(state, QUESTION_PHASE, "reveal-feedback")
    question = _question(state, question_id)
    if question["status"] != "reviewed":
        raise SessionError(
            f"question {question_id} is {question['status']}; feedback is not available yet"
        )
    round_no = int(question["round"])
    round_entry = None
    for existing in question["rounds"]:
        if existing["round"] == round_no:
            round_entry = existing
            break
    if round_entry is None or not round_entry.get("locked_feedback_file"):
        raise SessionError(f"question {question_id} round {round_no} has no locked feedback")

    locked_feedback_file = session / round_entry["locked_feedback_file"]
    _require_nonempty_text(locked_feedback_file, "feedback")
    revealed_feedback_file = _question_revealed_feedback_path(session, question_id, round_no)
    _copy_if_needed(locked_feedback_file, revealed_feedback_file)
    round_entry["revealed_feedback_file"] = str(revealed_feedback_file.relative_to(session))
    round_entry["revealed"] = True
    question["revealed"] = True
    question["completed_round"] = max(int(question.get("completed_round", 0)), round_no)
    save_state(session, state)
    print(revealed_feedback_file.read_text(encoding="utf-8"), end="")


def request_followup(session: Path, question_id: str) -> None:
    state = load_state(session)
    _require_current_phase(state, QUESTION_PHASE, "request-followup")
    question = _question(state, question_id)
    if question["status"] != "reviewed":
        raise SessionError(
            f"question {question_id} is {question['status']}; reveal the current feedback before opening a follow-up round"
        )
    current_round = int(question["round"])
    round_entry = None
    for existing in question["rounds"]:
        if existing["round"] == current_round:
            round_entry = existing
            break
    if round_entry is None or not round_entry.get("revealed"):
        raise SessionError(
            f"question {question_id} round {current_round} feedback must be revealed before opening a follow-up round"
        )
    question["round"] = current_round + 1
    question["status"] = "open"
    question["revealed"] = False
    save_state(session, state)
    print(f"opened follow-up round {question['round']} for question: {question_id}")


def finish_phase(session: Path, phase: int) -> None:
    _check_phase(phase)
    state = load_state(session)
    _require_current_phase(state, phase, "finish-phase")
    phase_data = _phase_state(state, phase)

    if phase in PHASE_BARRIER_PHASES:
        if not phase_data["barrier"].get("revealed"):
            raise SessionError(
                f"phase {phase} is not complete; reveal the reviewed coach artifact first"
            )
    elif phase == QUESTION_PHASE:
        questions = phase_data["questions"]
        if len(questions) < 10:
            raise SessionError("phase 2 requires at least 10 questions before completion")
        for question in questions.values():
            if int(question.get("round", 1)) != int(question.get("completed_round", 0)):
                raise SessionError(
                    f"question {question['id']} has an open follow-up round; close it before finishing phase 2"
                )
        for question in questions.values():
            if question["status"] != "reviewed":
                raise SessionError(
                    f"question {question['id']} is {question['status']}; all questions must be reviewed"
                )
            if not question.get("revealed"):
                raise SessionError(
                    f"question {question['id']} feedback has not been revealed yet"
                )

    phase_data["status"] = "completed"
    if phase < 4:
        state["current_phase"] = phase + 1
        next_phase = _phase_state(state, phase + 1)
        if next_phase["status"] == "pending":
            next_phase["status"] = "in_progress"
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
            if barrier.get("revealed") and barrier.get("revealed_file"):
                coach_src = session / barrier["revealed_file"]
                _require_nonempty_text(coach_src, "coach artifact")
                coach_dst = output / barrier["revealed_file"]
                coach_dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(coach_src, coach_dst)
        elif phase == str(QUESTION_PHASE):
            for question in phase_data["questions"].values():
                for round_entry in question.get("rounds", []):
                    if round_entry.get("revealed") and round_entry.get("revealed_feedback_file"):
                        feedback_src = session / round_entry["revealed_feedback_file"]
                        _require_nonempty_text(feedback_src, "feedback")
                        feedback_dst = output / round_entry["revealed_feedback_file"]
                        feedback_dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(feedback_src, feedback_dst)

    _write_json(output / "state" / "session.json", state)
    print(f"exported unlocked session content to: {output}")


def check_session(session: Path) -> None:
    state = load_state(session)
    errors = []

    for material in state["materials"]:
        material_path = Path(material["path"])
        if not material_path.exists():
            errors.append(f"material is missing: {material_path}")
            continue
        if material["type"] == "file":
            current_hash = _sha256_file(material_path)
            if current_hash != material.get("sha256"):
                errors.append(f"material changed since init: {material_path}")

    if state.get("workspace_root"):
        workspace_root = Path(state["workspace_root"])
        if not workspace_root.exists():
            errors.append(f"workspace_root is missing: {workspace_root}")

    for phase in PHASES:
        phase_data = _phase_state(state, phase)
        if phase in PHASE_BARRIER_PHASES:
            barrier = phase_data["barrier"]
            student_file = barrier.get("student_file")
            locked_file = barrier.get("locked_file")
            revealed_file = barrier.get("revealed_file")
            if barrier.get("revealed") and (not student_file or not locked_file or not revealed_file):
                errors.append(f"phase {phase} is revealed but missing a barrier path")
            if student_file and not (session / student_file).exists():
                errors.append(f"phase {phase} student attempt is missing on disk")
            if locked_file and not (session / locked_file).exists():
                errors.append(f"phase {phase} locked coach artifact is missing on disk")
            if revealed_file and not (session / revealed_file).exists():
                errors.append(f"phase {phase} revealed coach artifact is missing on disk")
        elif phase == QUESTION_PHASE:
            for question in phase_data["questions"].values():
                for round_entry in question.get("rounds", []):
                    answer_file = round_entry.get("answer_file")
                    locked_feedback_file = round_entry.get("locked_feedback_file")
                    revealed_feedback_file = round_entry.get("revealed_feedback_file")
                    if locked_feedback_file and not answer_file:
                        errors.append(f"question {question['id']} round {round_entry['round']} has feedback without an answer")
                    if answer_file and not (session / answer_file).exists():
                        errors.append(f"question {question['id']} round {round_entry['round']} answer is missing on disk")
                    if locked_feedback_file and not (session / locked_feedback_file).exists():
                        errors.append(f"question {question['id']} round {round_entry['round']} locked feedback is missing on disk")
                    if round_entry.get("revealed") and not revealed_feedback_file:
                        errors.append(f"question {question['id']} round {round_entry['round']} is revealed without a revealed feedback path")
                    if revealed_feedback_file and not (session / revealed_feedback_file).exists():
                        errors.append(f"question {question['id']} round {round_entry['round']} revealed feedback is missing on disk")
                if question["status"] == "reviewed" and not question.get("rounds"):
                    errors.append(f"question {question['id']} is reviewed without an answer")
                if question.get("revealed") and question["status"] != "reviewed":
                    errors.append(f"question {question['id']} is revealed without reviewed feedback")

    expected_phase_artifacts = {
        phase_data["barrier"]["revealed_file"]
        for phase in PHASE_BARRIER_PHASES
        for phase_data in [_phase_state(state, phase)]
        if phase_data["barrier"].get("revealed_file")
    }
    actual_phase_artifacts = {
        str(path.relative_to(session))
        for path in (session / "coach" / "phase-artifacts").rglob("*.md")
    }
    for unexpected in sorted(actual_phase_artifacts - expected_phase_artifacts):
        errors.append(f"untracked coach artifact on disk: {unexpected}")

    expected_feedback = {
        round_entry["revealed_feedback_file"]
        for question in _phase_state(state, QUESTION_PHASE)["questions"].values()
        for round_entry in question.get("rounds", [])
        if round_entry.get("revealed_feedback_file")
    }
    actual_feedback = {
        str(path.relative_to(session))
        for path in (session / "coach" / "feedback").rglob("*.md")
    }
    for unexpected in sorted(actual_feedback - expected_feedback):
        errors.append(f"untracked coach feedback on disk: {unexpected}")

    locked_phase_artifacts = {
        phase_data["barrier"]["locked_file"]
        for phase in PHASE_BARRIER_PHASES
        for phase_data in [_phase_state(state, phase)]
        if phase_data["barrier"].get("locked_file")
    }
    actual_locked_phase_artifacts = {
        str(path.relative_to(session))
        for path in (session / "state" / "locked" / "phase-artifacts").rglob("*.md")
    }
    for unexpected in sorted(actual_locked_phase_artifacts - locked_phase_artifacts):
        errors.append(f"untracked locked phase artifact on disk: {unexpected}")

    locked_feedback = {
        round_entry["locked_feedback_file"]
        for question in _phase_state(state, QUESTION_PHASE)["questions"].values()
        for round_entry in question.get("rounds", [])
        if round_entry.get("locked_feedback_file")
    }
    actual_locked_feedback = {
        str(path.relative_to(session))
        for path in (session / "state" / "locked" / "feedback").rglob("*.md")
    }
    for unexpected in sorted(actual_locked_feedback - locked_feedback):
        errors.append(f"untracked locked feedback on disk: {unexpected}")

    if errors:
        raise SessionError("; ".join(errors))
    print("session integrity check passed")


def next_step(session: Path) -> None:
    state = load_state(session)
    current_phase = state.get("current_phase")
    if current_phase is None:
        print("session is complete; use export to capture unlocked artifacts")
        return

    if current_phase in PHASE_BARRIER_PHASES:
        barrier = _phase_state(state, current_phase)["barrier"]
        if not barrier.get("student_file"):
            print(
                f"next: record the student attempt for phase {current_phase}\n"
                f"command: python3 \"$SKILL_DIR/scripts/session.py\" record-attempt --session .rdm --phase {current_phase} --from-file student/attempts/phase{current_phase}.md"
            )
            return
        if not barrier.get("locked_file"):
            print(
                f"next: save the coach artifact for phase {current_phase}\n"
                f"command: python3 \"$SKILL_DIR/scripts/session.py\" save-phase-artifact --session .rdm --phase {current_phase} --from-file coach/phase-artifacts/phase{current_phase}.md"
            )
            return
        if not barrier.get("revealed"):
            print(
                f"next: reveal the coach artifact for phase {current_phase}\n"
                f"command: python3 \"$SKILL_DIR/scripts/session.py\" reveal-phase --session .rdm --phase {current_phase}"
            )
            return
        print(
            f"next: finish phase {current_phase}\n"
            f"command: python3 \"$SKILL_DIR/scripts/session.py\" finish-phase --session .rdm --phase {current_phase}"
        )
        return

    questions = _phase_state(state, QUESTION_PHASE)["questions"]
    if len(questions) < 10:
        next_id = f"q{len(questions) + 1:02d}"
        print(
            "next: create the remaining phase 2 questions until you have 10\n"
            f"command: python3 \"$SKILL_DIR/scripts/session.py\" start-question --session .rdm --id {next_id} --title \"Question {len(questions) + 1}\" --from-file shared/questions/{next_id}.md"
        )
        return

    submitted = [qid for qid, q in questions.items() if q["status"] == "submitted"]
    if submitted:
        qid = sorted(submitted)[0]
        print(
            f"next: save coach feedback for {qid}\n"
            f"command: python3 \"$SKILL_DIR/scripts/session.py\" save-feedback --session .rdm --id {qid} --from-file coach/feedback/{qid}.md"
        )
        return

    reviewed_hidden = [qid for qid, q in questions.items() if q["status"] == "reviewed" and not q.get("revealed")]
    if reviewed_hidden:
        qid = sorted(reviewed_hidden)[0]
        print(
            f"next: reveal coach feedback for {qid}\n"
            f"command: python3 \"$SKILL_DIR/scripts/session.py\" reveal-feedback --session .rdm --id {qid}"
        )
        return

    reviewed_followup_ready = [
        qid
        for qid, q in questions.items()
        if q["status"] == "reviewed" and q.get("revealed") and int(q.get("completed_round", 0)) == int(q.get("round", 1))
    ]
    if reviewed_followup_ready:
        qid = sorted(reviewed_followup_ready)[0]
        next_round = int(questions[qid]["round"]) + 1
        print(
            f"next: open follow-up round {next_round} for {qid} if the coach asked a追问\n"
            f"command: python3 \"$SKILL_DIR/scripts/session.py\" request-followup --session .rdm --id {qid}"
        )
        return

    open_questions = [qid for qid, q in questions.items() if q["status"] == "open"]
    if open_questions:
        qid = sorted(open_questions)[0]
        print(
            f"next: submit the learner answer for {qid}\n"
            f"command: python3 \"$SKILL_DIR/scripts/session.py\" submit --session .rdm --id {qid} --from-file student/answers/{qid}.md"
        )
        return

    print(
        "next: finish phase 2\n"
        "command: python3 \"$SKILL_DIR/scripts/session.py\" finish-phase --session .rdm --phase 2"
    )


def _status_dict(state: Dict[str, Any]) -> Dict[str, Any]:
    summary = {
        "id": state["id"],
        "goal": state["goal"],
        "time_budget": state["time_budget"],
        "student_persona": state.get("student_persona", ""),
        "coach_persona": state.get("coach_persona", ""),
        "assessment_mode": state.get("assessment_mode", "conceptual"),
        "workspace_root": state.get("workspace_root", ""),
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
                    qid: {
                        "status": q["status"],
                        "round": q.get("round", 1),
                        "completed_round": q.get("completed_round", 0),
                    }
                    for qid, q in questions.items()
                },
            }
        else:
            barrier = phase_data["barrier"]
            summary["phases"][str(phase)] = {
                "status": phase_data["status"],
                "barrier": {
                    "revealed": barrier.get("revealed", False),
                    "student_file": barrier.get("student_file"),
                    "locked_file": barrier.get("locked_file"),
                    "revealed_file": barrier.get("revealed_file"),
                },
            }
    return summary


def status_session(session: Path) -> None:
    state = load_state(session)
    print(json.dumps(_status_dict(state), indent=2, sort_keys=True))


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
    init.add_argument("--student-persona", default="", help="optional learner persona or scenario")
    init.add_argument("--coach-persona", default="", help="optional coach persona or scenario")
    init.add_argument(
        "--assessment-mode",
        choices=("conceptual", "executable"),
        default="conceptual",
        help="learning assessment mode (default: conceptual)",
    )
    init.add_argument(
        "--workspace-root",
        default="",
        help="optional project root for executable tasks",
    )
    init.add_argument("--materials", nargs="*", default=[], help="material files or directories")

    status = sub.add_parser("status", help="show session status")
    _add_session_arg(status)

    check = sub.add_parser("check", help="check session integrity")
    _add_session_arg(check)

    next_cmd = sub.add_parser("next", help="show the next recommended session command")
    _add_session_arg(next_cmd)

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

    request_followup_cmd = sub.add_parser("request-followup", help="open a new follow-up round after revealed feedback")
    _add_session_arg(request_followup_cmd)
    request_followup_cmd.add_argument("--id", dest="question_id", required=True)

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
                args.student_persona,
                args.coach_persona,
                args.assessment_mode,
                args.workspace_root,
            )
        elif command == "status":
            status_session(Path(args.session))
        elif command == "check":
            check_session(Path(args.session))
        elif command == "next":
            next_step(Path(args.session))
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
        elif command == "request-followup":
            request_followup(Path(args.session), args.question_id)
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
