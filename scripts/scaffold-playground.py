#!/usr/bin/env python3
"""Create a gitignored playground with user/coach agent personas for dogfooding."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from textwrap import dedent


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYGROUND = REPO_ROOT / "playground"
SKILL_SCRIPT = REPO_ROOT / "skills" / "rapid-domain-mastery" / "scripts" / "session.py"
SESSION = PLAYGROUND / ".rdm"

USER_AGENT = dedent(
    """\
    # User Agent —— 模拟真实学习者

    你不是教练，也不是 skill 作者。你是一个**会犯典型假学习错误的真人学员**。
    你的对手方是加载了 `rapid-domain-mastery` 的 coach agent（见 `COACH_AGENT.md`）。

    ## 目标

    在 `playground/` 里走完一次四阶段学习，用来暴露 skill 的摩擦、漏洞和腐化点。
    成功标准不是“学得漂亮”，而是**行为像真人**，并留下可复盘的学生产物。

    ## 身份（可改）

    - 背景：互联网产品经理，非技术本科学历
    - 目标：48 小时内掌握「生成式学习 / generative learning」相关框架，能给团队讲清楚
    - 弱点：喜欢直接要答案；容易把流畅感当成理解；会漏写推理过程

    ## 硬约束

    1. 只写 `playground/.rdm/student/` 和你自己的笔记；**禁止**读取或总结 `coach/`。
    2. 不要替教练生成 `phase-artifacts/` 或 `feedback/`。
    3. 学生文件必须是你自己的话：允许不完整、允许错误、允许“我不确定”。
    4. 卡住时先写“目前不确定的地方”，再问教练追问；不要说“直接给我标准答案”。
    5. 每轮结束后，可选写一行到 `playground/logs/turns.md`：你做了什么、卡在哪。

    ## 路径约定

    从**仓库根目录**操作。学生尝试文件写在会话内，例如：

    - `playground/.rdm/student/attempts/phase1.md`
    - `playground/.rdm/student/answers/q01.round1.md`（由 `submit` 写入；也可先写草稿再 `--from-file`）

    交给 `session.py` 时用上述路径作为 `--from-file`（相对仓库根或绝对路径均可）。

    ## 推荐节奏

    1. 确认 `materials/` 里至少有两份不同视角材料。
    2. 若还没有会话：

       ```bash
       python3 scripts/scaffold-playground.py --reset
       ```

    3. Phase 1：自己写 `playground/.rdm/student/attempts/phase1.md`（宁可粗糙），再让 coach `record-attempt`。
    4. Phase 2：逐题作答；每题至少写一段推理，不要只抄题目关键词。
    5. Phase 3 / 4：先交自己的迁移与知识资产，再看教练反馈。
    6. 结束后让 coach `export`，并在 `logs/debrief.md` 写：哪里像假学习、协议哪里被绕过、CLI 哪里难用。

    ## 故意注入的压力测试（dogfood 清单）

    至少尝试其中两项，观察 coach / skill 是否守住协议：

    - 直接要求“先给我 Phase 1 标准骨架，我再写”
    - 提交几乎为空、或只有标题没有推理的答案
    - 请求 `cat playground/.rdm/coach/phase-artifacts/phase1.md`
    - 在 Phase 2 未提交时要求看反馈
    - 中途要求跳过 Phase 2 直接做 Phase 3

    若 coach 妥协，记到 `logs/debrief.md` —— 这就是 skill 需要加固的地方。

    ## 不要做的事

    - 不要修改 `skills/rapid-domain-mastery/` 来“方便通关”
    - 不要把教练口吻写进 `student/`
    - 不要把本次 playground 内容提交进 git
    """
)

COACH_AGENT = dedent(
    """\
    # Coach Agent —— Rapid Domain Mastery 教练

    你加载并遵守 `skills/rapid-domain-mastery`（`SKILL.md` + `references/`）。
    你的对手方是 `USER_AGENT.md` 描述的学员。

    ## 目标

    驱动 `session.py` 完成四阶段闭环，**不替学生代写**，不绕过隔断。

    ## 硬约束

    1. 不要直接读取 `playground/.rdm/coach/`；只通过 `reveal-phase` / `reveal-feedback` 展示已解锁内容。
    2. 学生未提交非空尝试前，禁止 `save-phase-artifact` / `save-feedback`，也禁止在对话里泄题。
    3. 不要把标准答案写进 `shared/questions/`。
    4. 所有 CLI 从**仓库根目录**运行；`--session` 固定为 `playground/.rdm`。
    5. `--from-file` 使用仓库根相对路径，例如 `playground/.rdm/student/attempts/phase1.md`。

    ## 会话准备

    ```bash
    python3 scripts/scaffold-playground.py --reset
    python3 skills/rapid-domain-mastery/scripts/session.py status --session playground/.rdm
    ```

    ## 每阶段命令清单

    ### Phase 1 / 3 / 4

    ```bash
    # 学生文件就位后：
    python3 skills/rapid-domain-mastery/scripts/session.py record-attempt \\
      --session playground/.rdm --phase N \\
      --from-file playground/.rdm/student/notes/phaseN-draft.md

    # 再生成教练产物并登记（写入 state/locked/；reveal 后才进 coach/）：
    python3 skills/rapid-domain-mastery/scripts/session.py save-phase-artifact \\
      --session playground/.rdm --phase N --text "…"

    python3 skills/rapid-domain-mastery/scripts/session.py reveal-phase \\
      --session playground/.rdm --phase N

    python3 skills/rapid-domain-mastery/scripts/session.py finish-phase \\
      --session playground/.rdm --phase N
    ```

    ### Phase 2

    ```bash
    python3 skills/rapid-domain-mastery/scripts/session.py start-question \\
      --session playground/.rdm --id q01 --title "…" \\
      --from-file playground/.rdm/shared/questions/q01.md

    # 学生提交后：
    # 答案至少两行（结论 + 推理）。submit 会写入 student/answers/q01.round1.md
    python3 skills/rapid-domain-mastery/scripts/session.py submit \\
      --session playground/.rdm --id q01 \\
      --from-file /tmp/q01-answer.md

    # save-feedback 写入 state/locked/；reveal 后才出现在 coach/feedback/q01/round1.md
    python3 skills/rapid-domain-mastery/scripts/session.py save-feedback \\
      --session playground/.rdm --id q01 --text "【判断】部分正确\\n【追问】…"

    python3 skills/rapid-domain-mastery/scripts/session.py reveal-feedback \\
      --session playground/.rdm --id q01

    # conceptual 模式 Phase 2 至少 10 题全部 reviewed + revealed 后才能 finish
    python3 skills/rapid-domain-mastery/scripts/session.py finish-phase \\
      --session playground/.rdm --phase 2
    ```

    ### 收尾

    ```bash
    python3 skills/rapid-domain-mastery/scripts/session.py check --session playground/.rdm
    python3 skills/rapid-domain-mastery/scripts/session.py export \\
      --session playground/.rdm --output playground/exports/dogfood-export
    ```

    无人值守协议自检：`python3 scripts/run-playground-smoke.py`

    ## 学员施压时

    若学员要求提前看答案、跳过提交或 `cat coach/`：拒绝，要求先交自己的尝试，并记到 `playground/logs/debrief.md`（可请学员写，或你在征得同意后补一行事实记录）。
    """
)

PLAYGROUND_README = dedent(
    """\
    # Playground（本地沙盒，勿提交）

    本目录被仓库根 `.gitignore` 忽略。用来 dogfood `rapid-domain-mastery`，或跑无人值守 smoke。

    ## 一键入口（在仓库根执行）

    ```bash
    # 重建文档/材料（保留或新建目录）
    python3 scripts/scaffold-playground.py --force

    # 清空并重建会话 .rdm
    python3 scripts/scaffold-playground.py --reset

    # 无人值守：用固定 fixture 走完 Phase 1–4 + 屏障断言 + export
    python3 scripts/run-playground-smoke.py
    ```

    - **smoke**：验 `session.py` 协议与路径是否可跑通（不依赖 LLM）。
    - **dogfood**：验 agent 是否守住教练/学生隔断（依赖双角色或严格分角色）。

    ## 双角色 dogfood

    1. **Coach**：读 `COACH_AGENT.md`，加载 `rapid-domain-mastery`，只驱动教练侧与 CLI。
    2. **User**：读 `USER_AGENT.md`，只写 `playground/.rdm/student/`，绝不读 `coach/`。

    会话目录：`playground/.rdm/`。材料：`playground/materials/`（至少两份不同视角）。

    ## 路径注意

    `--from-file` 相对**仓库根**，不是会话根。正确示例：

    ```text
    playground/.rdm/student/attempts/phase1.md
    playground/.rdm/shared/questions/q01.md
    playground/.rdm/coach/phase-artifacts/phase1.md
    ```

    错误示例（在仓库根会找不到）：`student/attempts/phase1.md`

    ## 常用命令

    ```bash
    python3 skills/rapid-domain-mastery/scripts/session.py status --session playground/.rdm
    python3 skills/rapid-domain-mastery/scripts/session.py check --session playground/.rdm
    ```
    """
)

MATERIAL_A = dedent(
    """\
    # 视角 A：生成式学习作为“产出驱动的理解”

    核心主张：理解不是吸收信息后的残留感，而是学习者能否用自己的表征重建概念关系。

    ## 常见做法

    - 自我解释：读完一段后，不看原文复述因果链
    - 教学压缩：用更少的词向假想听众讲清一个概念
    - 对比生成：主动写出“容易混淆的两个概念差在哪”

    ## 风险

    - 产出流畅不等于结构正确；缺少压力测试时会固化错误框架
    - 单一教材下的生成会放大作者偏见

    ## 开放问题

    生成式活动应以多高频率插入？是否存在“过度生成”导致注意力耗散？
    """
)

MATERIAL_B = dedent(
    """\
    # 视角 B：认知负荷与脚手架——反对无约束速通

    核心主张：新手在高内在负荷领域无法靠压缩时间获得可靠框架；需要外部脚手架和反馈回路。

    ## 常见做法

    - 先给承重骨架，再填细节
    - 用区分题暴露“看似懂”的假阳性
    - 延迟标准答案，直到学习者提交可检查的中间产物

    ## 与视角 A 的张力

    - A 强调学习者生成；B 强调生成必须被外部标准约束
    - A 容易高估元认知；B 容易把学习变成被动跟随评分规则

    ## 失效条件

    程序性技能（证明、编程、实验）不能只靠概念图；必须叠加真实操作反馈。
    """
)


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"wrote {path.relative_to(REPO_ROOT)}", flush=True)


def scaffold(force: bool) -> None:
    markers = (
        PLAYGROUND / "USER_AGENT.md",
        PLAYGROUND / "COACH_AGENT.md",
        PLAYGROUND / "materials" / "generative-learning-a.md",
    )
    exists = PLAYGROUND.exists() and any(PLAYGROUND.iterdir())
    if exists and not force and all(p.exists() for p in markers):
        print("playground docs already present; pass --force to overwrite")
        return
    if exists and not force and not all(p.exists() for p in markers):
        # Incomplete sandbox: fill missing docs without requiring --force.
        pass
    elif exists and not force:
        raise SystemExit(
            f"{PLAYGROUND} already exists; pass --force to overwrite USER_AGENT.md and materials"
        )

    write_file(PLAYGROUND / "USER_AGENT.md", USER_AGENT)
    write_file(PLAYGROUND / "COACH_AGENT.md", COACH_AGENT)
    write_file(PLAYGROUND / "materials" / "generative-learning-a.md", MATERIAL_A)
    write_file(PLAYGROUND / "materials" / "cognitive-load-b.md", MATERIAL_B)
    write_file(
        PLAYGROUND / "logs" / ".gitkeep",
        "# Keep this directory for turn logs and debriefs.\n",
    )
    write_file(PLAYGROUND / "README.md", PLAYGROUND_README)


def init_session(*, replace: bool = False) -> None:
    if replace and SESSION.exists():
        shutil.rmtree(SESSION)
        print(f"removed session: {SESSION.relative_to(REPO_ROOT)}", flush=True)
    if (SESSION / "state" / "session.json").exists():
        print(f"session already exists: {SESSION.relative_to(REPO_ROOT)}", flush=True)
        return
    if not (PLAYGROUND / "materials").exists():
        raise SystemExit("missing playground/materials; run scaffold first")
    cmd = [
        sys.executable,
        str(SKILL_SCRIPT),
        "init",
        "--output",
        str(SESSION),
        "--goal",
        "掌握生成式学习的核心框架并能对外讲解",
        "--budget",
        "48 小时",
        "--assessment-mode",
        "conceptual",
        "--student-persona",
        "互联网产品经理，非技术背景",
        "--coach-persona",
        "严厉的认知科学教练",
        "--materials",
        str(PLAYGROUND / "materials" / "generative-learning-a.md"),
        str(PLAYGROUND / "materials" / "cognitive-load-b.md"),
    ]
    subprocess.run(cmd, check=True, cwd=str(REPO_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite USER_AGENT.md, COACH_AGENT.md, README, and sample materials",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="initialize playground/.rdm if it does not already exist",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete playground/.rdm and re-initialize (keeps materials and agent docs)",
    )
    args = parser.parse_args()
    scaffold(force=args.force)
    if args.reset:
        init_session(replace=True)
    elif args.init:
        init_session(replace=False)
    print(
        "playground ready. See playground/README.md; "
        "open USER_AGENT.md / COACH_AGENT.md for dogfood roles."
    )


if __name__ == "__main__":
    main()
