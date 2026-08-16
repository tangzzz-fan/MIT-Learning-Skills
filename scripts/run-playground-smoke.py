#!/usr/bin/env python3
"""Unattended playground smoke: walk Phase 1–4 with fixtures and barrier checks."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYGROUND = REPO_ROOT / "playground"
SESSION = PLAYGROUND / ".rdm"
SKILL_SCRIPT = REPO_ROOT / "skills" / "rapid-domain-mastery" / "scripts" / "session.py"
SCAFFOLD = REPO_ROOT / "scripts" / "scaffold-playground.py"
EXPORT_DIR = PLAYGROUND / "exports" / "smoke-export"
PHASE2_QUESTION_COUNT = 10


class SmokeError(RuntimeError):
    pass


def run_session(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), *args],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
    )
    if check and result.returncode != 0:
        raise SmokeError(
            f"session.py {' '.join(args)} failed\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def expect_fail(*args: str) -> None:
    result = run_session(*args, check=False)
    if result.returncode == 0:
        raise SmokeError(f"expected failure for: session.py {' '.join(args)}")


def write_text(rel: str, content: str) -> Path:
    path = REPO_ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


def ensure_playground() -> None:
    subprocess.run(
        [sys.executable, str(SCAFFOLD), "--force", "--reset"],
        cwd=str(REPO_ROOT),
        check=True,
    )


def phase_barrier(phase: int, attempt: str, artifact: str) -> None:
    draft_rel = f"playground/.rdm/student/notes/phase{phase}-draft.md"

    expect_fail(
        "save-phase-artifact",
        "--session",
        "playground/.rdm",
        "--phase",
        str(phase),
        "--text",
        "should not save yet",
    )

    write_text(draft_rel, attempt)
    run_session(
        "record-attempt",
        "--session",
        "playground/.rdm",
        "--phase",
        str(phase),
        "--from-file",
        draft_rel,
    )
    run_session(
        "save-phase-artifact",
        "--session",
        "playground/.rdm",
        "--phase",
        str(phase),
        "--text",
        artifact,
    )
    expect_fail(
        "finish-phase",
        "--session",
        "playground/.rdm",
        "--phase",
        str(phase),
    )
    revealed = run_session(
        "reveal-phase",
        "--session",
        "playground/.rdm",
        "--phase",
        str(phase),
    )
    if artifact.strip().splitlines()[0] not in revealed.stdout:
        raise SmokeError(f"reveal-phase {phase} did not print coach artifact")
    run_session(
        "finish-phase",
        "--session",
        "playground/.rdm",
        "--phase",
        str(phase),
    )


def phase_two() -> None:
    # Barrier: cannot save feedback before submit.
    run_session(
        "start-question",
        "--session",
        "playground/.rdm",
        "--id",
        "q01",
        "--title",
        "生成 vs 被动",
        "--text",
        "# Q01\n生成式学习与被动阅读的核心差别是什么？",
    )
    expect_fail(
        "save-feedback",
        "--session",
        "playground/.rdm",
        "--id",
        "q01",
        "--text",
        "premature feedback",
    )

    for index in range(1, PHASE2_QUESTION_COUNT + 1):
        qid = f"q{index:02d}"
        draft_rel = f"playground/.rdm/student/notes/{qid}-draft.md"
        if index > 1:
            run_session(
                "start-question",
                "--session",
                "playground/.rdm",
                "--id",
                qid,
                "--title",
                f"区分题 {index}",
                "--text",
                f"# {qid.upper()}\n区分题 {index}：概念 A 与概念 B 在什么条件下会互相冲突？",
            )

        write_text(
            draft_rel,
            (
                f"结论：题目 {index} 的关键差别在于是否强制学习者先产出可检验表征。\n"
                f"推理：没有提交就看标准答案会短路检索练习，所以必须先写自己的框架。"
            ),
        )
        # Barrier: one-line answers should fail the reasoned-answer check.
        if index == 1:
            thin = f"playground/.rdm/student/notes/{qid}-thin.md"
            write_text(thin, "只有一句话没有推理。")
            expect_fail(
                "submit",
                "--session",
                "playground/.rdm",
                "--id",
                qid,
                "--from-file",
                thin,
            )

        run_session(
            "submit",
            "--session",
            "playground/.rdm",
            "--id",
            qid,
            "--from-file",
            draft_rel,
        )
        run_session(
            "save-feedback",
            "--session",
            "playground/.rdm",
            "--id",
            qid,
            "--text",
            (
                f"【判断】部分正确\n"
                f"【逻辑漏洞】对题目 {index} 的边界条件说明不够。\n"
                f"【追问】若产出只是抄写，还算生成吗？"
            ),
        )
        run_session("reveal-feedback", "--session", "playground/.rdm", "--id", qid)

    run_session("finish-phase", "--session", "playground/.rdm", "--phase", "2")


def export_and_verify() -> None:
    if EXPORT_DIR.exists():
        shutil.rmtree(EXPORT_DIR)
    run_session(
        "export",
        "--session",
        "playground/.rdm",
        "--output",
        str(EXPORT_DIR),
    )
    required = [
        EXPORT_DIR / "student" / "attempts" / "phase1.md",
        EXPORT_DIR / "student" / "attempts" / "phase3.md",
        EXPORT_DIR / "student" / "attempts" / "phase4.md",
        EXPORT_DIR / "coach" / "phase-artifacts" / "phase1.md",
        EXPORT_DIR / "coach" / "feedback" / "q01" / "round1.md",
        EXPORT_DIR / "shared" / "questions" / "q01.md",
        EXPORT_DIR / "state" / "session.json",
    ]
    missing = [str(p.relative_to(REPO_ROOT)) for p in required if not p.is_file()]
    if missing:
        raise SmokeError("export missing files:\n" + "\n".join(missing))

    locked_leak = EXPORT_DIR / "state" / "locked"
    if locked_leak.exists() and any(locked_leak.rglob("*")):
        raise SmokeError("export must not include state/locked coach content")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep-session",
        action="store_true",
        help="do not reset playground/.rdm before running (default resets via scaffold)",
    )
    args = parser.parse_args()

    if args.keep_session:
        if not (SESSION / "state" / "session.json").exists():
            ensure_playground()
    else:
        ensure_playground()

    phase_barrier(
        1,
        attempt=(
            "## 我的初稿骨架\n"
            "1. 生成比阅读重要\n"
            "2. 好像还要有反馈，但不确定怎么接\n"
            "3. 三层：概念 / 方法 / 例子（很粗糙）"
        ),
        artifact=(
            "# Coach Phase 1\n"
            "## 心智模型\n"
            "- 产出驱动理解\n"
            "- 延迟答案防假学习\n"
            "## 争议\n"
            "- 生成频率 vs 认知负荷\n"
            "## 骨架\n"
            "范式 → 方法 → 探针"
        ),
    )
    phase_two()
    phase_barrier(
        3,
        attempt=(
            "## 边界探索\n"
            "若把生成式学习迁到开会：会后每人用三句话复述决策因果。"
        ),
        artifact=(
            "# Coach Phase 3\n"
            "迁移可行，但需加上可检验标准（别人能否按你的复述执行）。"
        ),
    )
    phase_barrier(
        4,
        attempt=(
            "## 个人资产\n"
            "- 概念图：生成 / 负荷 / 延迟反馈\n"
            "- 错题：把笔记抄写当成生成\n"
            "- 速查：先交再看"
        ),
        artifact=(
            "# Coach Phase 4\n"
            "补漏：程序性领域需要可运行反馈，不能只靠概念图。"
        ),
    )
    run_session("check", "--session", "playground/.rdm")
    export_and_verify()
    print("playground smoke passed")


if __name__ == "__main__":
    try:
        main()
    except (SmokeError, subprocess.CalledProcessError) as exc:
        print(f"playground smoke failed: {exc}", file=sys.stderr)
        sys.exit(1)
