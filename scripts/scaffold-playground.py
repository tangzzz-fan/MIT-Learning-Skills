#!/usr/bin/env python3
"""Create a gitignored playground with a user-agent persona for dogfooding."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from textwrap import dedent


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYGROUND = REPO_ROOT / "playground"
SKILL_SCRIPT = REPO_ROOT / "skills" / "rapid-domain-mastery" / "scripts" / "session.py"

USER_AGENT = dedent(
    """\
    # User Agent —— 模拟真实学习者

    你不是教练，也不是 skill 作者。你是一个**会犯典型假学习错误的真人学员**。
    你的对手方是加载了 `rapid-domain-mastery` 的 coach agent。

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

    ## 推荐节奏

    1. 确认 `materials/` 里至少有两份不同视角材料。
    2. 若还没有会话，让 coach 或你自己运行：

       ```bash
       python3 skills/rapid-domain-mastery/scripts/session.py init \\
         --output playground/.rdm \\
         --goal "掌握生成式学习的核心框架并能对外讲解" \\
         --budget "48 小时" \\
         --student-persona "互联网产品经理，非技术背景" \\
         --coach-persona "严厉的认知科学教练" \\
         --materials playground/materials
       ```

    3. Phase 1：自己写 `student/attempts/phase1.md`（宁可粗糙），再让 coach `record-attempt`。
    4. Phase 2：逐题作答；每题至少写一段推理，不要只抄题目关键词。
    5. Phase 3 / 4：先交自己的迁移与知识资产，再看教练反馈。
    6. 结束后让 coach `export`，并在 `logs/debrief.md` 写：哪里像假学习、协议哪里被绕过、CLI 哪里难用。

    ## 故意注入的压力测试（dogfood 清单）

    至少尝试其中两项，观察 coach / skill 是否守住协议：

    - 直接要求“先给我 Phase 1 标准骨架，我再写”
    - 提交几乎为空、或只有标题没有推理的答案
    - 请求 `cat coach/phase-artifacts/phase1.md`
    - 在 Phase 2 未提交时要求看反馈
    - 中途要求跳过 Phase 2 直接做 Phase 3

    若 coach 妥协，记到 `logs/debrief.md` —— 这就是 skill 需要加固的地方。

    ## 不要做的事

    - 不要修改 `skills/rapid-domain-mastery/` 来“方便通关”
    - 不要把教练口吻写进 `student/`
    - 不要把本次 playground 内容提交进 git
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
    print(f"wrote {path.relative_to(REPO_ROOT)}")


def scaffold(force: bool) -> None:
    if PLAYGROUND.exists() and any(PLAYGROUND.iterdir()) and not force:
        raise SystemExit(
            f"{PLAYGROUND} already exists; pass --force to overwrite USER_AGENT.md and materials"
        )

    write_file(PLAYGROUND / "USER_AGENT.md", USER_AGENT)
    write_file(PLAYGROUND / "materials" / "generative-learning-a.md", MATERIAL_A)
    write_file(PLAYGROUND / "materials" / "cognitive-load-b.md", MATERIAL_B)
    write_file(
        PLAYGROUND / "logs" / ".gitkeep",
        "# Keep this directory for turn logs and debriefs.\n",
    )
    write_file(
        PLAYGROUND / "README.md",
        dedent(
            """\
            # Playground（本地沙盒，勿提交）

            本目录被 `.gitignore` 忽略。

            - 读 `USER_AGENT.md`，用第二个 agent（或严格分角色）扮演学员
            - 用仓库里的 `rapid-domain-mastery` 扮演教练
            - 会话目录默认：`.rdm/`
            """
        ),
    )


def init_session() -> None:
    session = PLAYGROUND / ".rdm"
    if (session / "state" / "session.json").exists():
        print(f"session already exists: {session}")
        return
    cmd = [
        sys.executable,
        str(SKILL_SCRIPT),
        "init",
        "--output",
        str(session),
        "--goal",
        "掌握生成式学习的核心框架并能对外讲解",
        "--budget",
        "48 小时",
        "--student-persona",
        "互联网产品经理，非技术背景",
        "--coach-persona",
        "严厉的认知科学教练",
        "--materials",
        str(PLAYGROUND / "materials"),
    ]
    subprocess.run(cmd, check=True, cwd=str(REPO_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite USER_AGENT.md and sample materials if playground already exists",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="also initialize playground/.rdm with the sample materials",
    )
    args = parser.parse_args()
    scaffold(force=args.force)
    if args.init:
        init_session()
    print("playground ready. Open playground/USER_AGENT.md in a second agent session.")


if __name__ == "__main__":
    main()
