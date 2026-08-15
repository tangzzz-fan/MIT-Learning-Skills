---
name: rapid-domain-mastery
description: Rapid Domain Mastery 把教材、论文、讲义等学习材料变成可验证的个人知识框架，并执行四阶段学习：骨架提取、认知压力测试、边界探索迁移、知识资产固化。使用时机：用户想快速学习/速通一门陌生课程、准备考试或项目、把大量阅读材料转化为深层理解、执行“MIT 48 小时 NotebookLM”式学习法，或要求“先搭骨架、再压力测试、最后迁移验证”。该 skill 强制教练/学生隔断，只有在学生先提交自己的回答或框架后，才允许生成和读取教练的模型答案、推理与反馈。
---

# Rapid Domain Mastery

把学习材料压缩成可测试的心智模型，并用“先学生、后教练”的隔断避免假学习。默认适合陈述性知识，也可以渐进扩展到编程这类程序性技能。

## 快速开始

1. 确认学习材料是多个视角的文件或目录；单本教材会产生偏见。
2. 创建会话：

```bash
python3 "$SKILL_DIR/scripts/session.py" init \
  --output .rdm \
  --goal "你的学习目标" \
  --budget "48 小时" \
  --assessment-mode conceptual \
  --student-persona "某行业新人" \
  --coach-persona "麦肯锡资深分析家" \
  --materials 教材目录 论文目录 讲义目录
```

3. 查看状态：

```bash
python3 "$SKILL_DIR/scripts/session.py" status --session .rdm
```

4. 依次执行 Phase 1 到 Phase 4。CLI 会强制阶段顺序；先写学生自己的尝试，再保存并解锁教练内容。

## 会话目录

```
.rdm/
  student/
    attempts/   # 学生先写的框架、边界推理、个人知识资产
    answers/    # 学生对每个区分题的作答
    artifacts/  # executable 模式下的补丁、源码或最小可执行产物
    notes/      # 学生笔记
  coach/
    phase-artifacts/  # 仅存放已经 reveal 给学生的阶段产物
    feedback/         # 仅存放已经 reveal 给学生的逐轮反馈
  shared/
    questions/  # 学生和教练都能看到的题目
    tasks/      # executable 模式下的任务说明
    migration-tasks/  # executable 模式下的 Phase 3 迁移任务
    regression-cases/  # executable 模式下的 Phase 4 回归用例
    runtime-feedback/  # executable 模式下即时可见的环境反馈
  state/
    session.json
    locked/      # 未 reveal 的教练内容，export 不会带出
```

学生拥有 `student/`；教练拥有 `coach/`。`shared/` 只放双方都可读的输入，不放置模型答案。

## 身份与情景

`init` 支持两个可选身份字段，并持久化到 `state/session.json`：

- `--student-persona`：学生的初始身份或情景，例如“非技术背景的产品新人”。
- `--coach-persona`：教练的角色，例如“麦肯锡资深分析家”。
- `--assessment-mode`：学习模式，`conceptual` 用于概念压力测试，`executable` 为程序性技能扩展预留。
- `--workspace-root`：可选的项目根目录，供 executable 模式下运行检查使用。

如果为空，教练使用 `references/phase-prompts.md` 中的默认角色；学生不额外代入身份。身份只影响语气、视角和难度，不改变先学生、后教练的隔断顺序。

## 教练/学生隔断（必须遵守）

“假学习”来自学生过早看到标准答案。以下规则不可跳过：

- 不要直接 `cat`、读取或总结 `coach/` 下的任何文件。只使用 `session.py` 的 `reveal-phase` 或 `reveal-feedback` 命令。
- Phase 1：先让学生写 `student/attempts/phase1.md` 的朴素框架，再生成 `coach/phase-artifacts/phase1.md`。
- Phase 2：先把题目写入 `shared/questions/`，等学生提交 `student/answers/<id>.md`，再生成 `coach/feedback/<id>.md`。
- Phase 3 和 Phase 4 同样遵循“学生尝试 -> 教练评价 -> 解锁”。
- 如果学生没有提交自己的内容，立即停止并提示学生先完成；不要给答案、暗示或“我先给你看看正确版本”。
- `save-phase-artifact` / `save-feedback` 只把教练内容写入 `state/locked/`；只有执行 `reveal-*` 后，内容才会复制到 `coach/`，并进入导出。

完整规则见 [references/separation-protocol.md](references/separation-protocol.md)。
若要把 RDM 扩展到编程教学，参考 [references/executable-mode.md](references/executable-mode.md)。

## 四阶段工作流

每个阶段的完整 prompt 模板在 [references/phase-prompts.md](references/phase-prompts.md)。执行时按以下顺序操作，并只加载当前阶段的模板。

### Phase 1：骨架提取

目标是在 30 分钟内建立高层认知地图。先让学生用自己的话写出已知框架，再让教练从材料中抽取：

- 3-5 个核心心智模型，每个都能一句话定义并说明适用问题。
- 2-3 个根本争议，标明共识区、活跃争议和开放问题。
- 不超过三层的知识骨架，并标注每个节点的“承重”程度。

用命令记录和解锁：

```bash
python3 "$SKILL_DIR/scripts/session.py" record-attempt --session .rdm --phase 1 --from-file student/attempts/phase1.md
python3 "$SKILL_DIR/scripts/session.py" save-phase-artifact --session .rdm --phase 1 --from-file coach/phase-artifacts/phase1.md
python3 "$SKILL_DIR/scripts/session.py" reveal-phase --session .rdm --phase 1
```

### Phase 2：认知压力测试

生成至少 10 道“区分题”，覆盖概念辨析、场景应用、方法论比较和开放设计。题目放在 `shared/questions/`，答案和标准推理绝不能在学生提交前写入 `coach/`。学生答案至少要包含两行非空内容：自己的结论，以及支撑该结论的推理。若教练在反馈中提出追问，必须先 `reveal-feedback`，再用 `request-followup` 开启下一轮作答。

```bash
python3 "$SKILL_DIR/scripts/session.py" start-question --session .rdm --id q01 --title "第一题" --from-file shared/questions/q01.md
# 学生完成 student/answers/q01.md 后：
python3 "$SKILL_DIR/scripts/session.py" submit --session .rdm --id q01 --from-file student/answers/q01.md
# 教练生成反馈后：
python3 "$SKILL_DIR/scripts/session.py" save-feedback --session .rdm --id q01 --from-file coach/feedback/q01.md
python3 "$SKILL_DIR/scripts/session.py" reveal-feedback --session .rdm --id q01
# 若反馈里有追问：
python3 "$SKILL_DIR/scripts/session.py" request-followup --session .rdm --id q01
```

若 `assessment_mode=executable`，Phase 2 可以改成最小执行回路：

```bash
python3 "$SKILL_DIR/scripts/session.py" start-task --session .rdm --id t01 \
  --title "修复失败测试" \
  --check-command "pytest -q" \
  --from-file shared/tasks/t01.md
python3 "$SKILL_DIR/scripts/session.py" submit-artifact --session .rdm --id t01 \
  --from-file student/artifacts/t01.diff
python3 "$SKILL_DIR/scripts/session.py" run-check --session .rdm --id t01
python3 "$SKILL_DIR/scripts/session.py" save-task-feedback --session .rdm --id t01 \
  --from-file coach/feedback/t01.md
python3 "$SKILL_DIR/scripts/session.py" reveal-task-feedback --session .rdm --id t01
```

这里有两条额外约束：

- `shared/runtime-feedback/` 里的环境反馈即时可见，不走 reveal 屏障。
- 但教练反馈必须建立在当前轮已经跑过 `run-check` 的结果上；学生重提产物后，要重新跑检查。

### Phase 3：边界探索与迁移验证

让学生先完成反事实推演、跨领域迁移、最小可行解释和未知问题生成，再解锁教练对因果链条和迁移边界的检查。

若 `assessment_mode=executable`，Phase 3 可以把迁移题变成可运行任务：

```bash
python3 "$SKILL_DIR/scripts/session.py" start-exec-task --session .rdm --phase 3 --id m01 \
  --title "迁移到陌生约束" \
  --check-command "pytest -q" \
  --from-file shared/migration-tasks/m01.md
python3 "$SKILL_DIR/scripts/session.py" submit-exec-artifact --session .rdm --phase 3 --id m01 \
  --from-file student/artifacts/phase3.m01.diff
python3 "$SKILL_DIR/scripts/session.py" run-exec-check --session .rdm --phase 3 --id m01
python3 "$SKILL_DIR/scripts/session.py" save-exec-feedback --session .rdm --phase 3 --id m01 \
  --from-file coach/feedback/phase3/m01.md
python3 "$SKILL_DIR/scripts/session.py" reveal-exec-feedback --session .rdm --phase 3 --id m01
```

### Phase 4：个人知识资产固化

让学生先整理自己的概念图、错题本、速查卡，再让教练补漏并校对，最后导出已解锁内容：

若 `assessment_mode=executable`，Phase 4 可以把“错题本”升级成可复跑的回归用例册：

```bash
python3 "$SKILL_DIR/scripts/session.py" start-exec-task --session .rdm --phase 4 --id r01 \
  --title "保留历史错误为回归用例" \
  --check-command "pytest -q" \
  --from-file shared/regression-cases/r01.md
python3 "$SKILL_DIR/scripts/session.py" submit-exec-artifact --session .rdm --phase 4 --id r01 \
  --from-file student/artifacts/phase4.r01.diff
python3 "$SKILL_DIR/scripts/session.py" run-exec-check --session .rdm --phase 4 --id r01
python3 "$SKILL_DIR/scripts/session.py" save-exec-feedback --session .rdm --phase 4 --id r01 \
  --from-file coach/feedback/phase4/r01.md
python3 "$SKILL_DIR/scripts/session.py" reveal-exec-feedback --session .rdm --phase 4 --id r01
```

```bash
python3 "$SKILL_DIR/scripts/session.py" finish-phase --session .rdm --phase 4
python3 "$SKILL_DIR/scripts/session.py" export --session .rdm --output exports/rdm-export
```

## 脚本命令速查

| 命令 | 用途 |
|---|---|
| `init` | 创建会话并记录材料清单 |
| `status` | 查看阶段、题目和隔断状态 |
| `record-attempt` | 记录 Phase 1/3/4 的学生尝试 |
| `save-phase-artifact` | 学生提交后保存教练阶段产物 |
| `reveal-phase` | 读取已解锁的教练阶段产物 |
| `start-question` | 创建 Phase 2 题目 |
| `submit` | 提交学生答案 |
| `save-feedback` | 学生提交后保存教练反馈 |
| `reveal-feedback` | 读取已解锁的教练反馈 |
| `request-followup` | 在已 reveal 的反馈后开启下一轮追问 |
| `start-task` | 创建 executable 模式下的 Phase 2 任务 |
| `submit-artifact` | 提交 executable 模式下的学生产物 |
| `run-check` | 运行 executable 模式下的即时环境检查 |
| `save-task-feedback` | 保存 executable 任务的教练反馈 |
| `reveal-task-feedback` | 读取 executable 任务已解锁的教练反馈 |
| `request-task-followup` | 为 executable 任务开启下一轮 |
| `start-exec-task` | 创建 Phase 3/4 的 executable 任务 |
| `submit-exec-artifact` | 提交 Phase 3/4 的学生产物 |
| `run-exec-check` | 运行 Phase 3/4 的即时环境检查 |
| `save-exec-feedback` | 保存 Phase 3/4 的教练反馈 |
| `reveal-exec-feedback` | 读取 Phase 3/4 已解锁的教练反馈 |
| `request-exec-followup` | 为 Phase 3/4 任务开启下一轮 |
| `finish-phase` | 校验并标记阶段完成 |
| `export` | 导出学生成果和已解锁教练内容 |
| `check` | 检查会话完整性 |
| `next` | 输出当前阶段推荐的下一条命令 |

## 注意事项

- 材料必须覆盖多个视角；单源材料会生成偏见框架。
- `init` 至少要提供一份材料；`check` 会在文件材料被替换或改写时报告漂移。
- 程序性知识领域（数学证明、编程、实验技能）不能只靠理解框架，必须叠加动手练习。
- `assessment_mode=executable` 是程序性技能扩展的基础层；最小执行回路会在后续 phase 补齐。
- 零基础或元认知不足时，先缩小范围或补充基础材料，不要硬套 48 小时压缩。
