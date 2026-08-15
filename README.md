# MIT Learning Skills

一个开源的 Codex skill 库，把“MIT 研究生用 NotebookLM 48 小时速通陌生课程”的社交媒体案例，转成可复用、可测试的 agent 学习方法。

> 原案例的真实性无法验证。仓库关注的不是故事真伪，而是其中的生成式学习（Generative Learning）机制是否可以被工程化为一个可控 skill。

## 已实现的 skill

- 名称：`rapid-domain-mastery`
- 位置：[skills/rapid-domain-mastery](skills/rapid-domain-mastery)
- 用途：把教材、论文、讲义等材料变成可验证的个人知识框架，并执行四个阶段的学习闭环。

## 方法论

传统学习瓶颈往往不是“理解速度”，而是认知框架搭建速度。该 skill 用逆向工程替代逐章熟悉：

| Generative Learning 层级 | Rapid Domain Mastery 阶段 | 具体动作 |
|---|---|---|
| 自我解释 | Phase 1：骨架提取 | 从多源材料提取核心心智模型、争议地图和承重骨架 |
| 可视化重构 | Phase 2：认知压力测试 | 生成跨概念“区分题”，暴露理解漏洞 |
| 对外教授/项目实践 | Phase 3：边界探索与迁移验证 | 反事实推演、跨领域迁移、最小可行解释 |
| 生成式反馈 | Phase 4：个人知识资产固化 | 概念图、错题本、速查卡 |

它不是“让 AI 替你学”，而是让 AI 当认知健身教练：先搭骨架，再压力测试，最后迁移验证。

## 防假学习：教练/学生隔断

skill 通过目录边界和脚本状态机强制“先学生、后教练”：

```text
session/
  student/            # 学生先写自己的框架、答案、推理
  coach/              # 教练在学生提交后才生成模型答案、反馈
  shared/questions/   # 只放双方都能看的题目
  state/session.json  # 记录隔断状态
```

关键约束：

- 教练内容不能直接读取，只能通过 `reveal-phase` 或 `reveal-feedback` 解锁。
- Phase 1/3/4：学生先写尝试文件，教练才能保存阶段产物。
- Phase 2：学生先提交答案，教练才能保存并显示逐题反馈。
- `export` 只导出学生成果和已解锁的教练内容。

详细规则见 [references/separation-protocol.md](skills/rapid-domain-mastery/references/separation-protocol.md)。

## 快速开始

```bash
# 1. 初始化会话
python3 skills/rapid-domain-mastery/scripts/session.py init \
  --output .rdm \
  --goal "掌握领域 X 的核心框架" \
  --budget "48 小时" \
  --student-persona "非技术背景的产品新人" \
  --coach-persona "麦肯锡资深分析家" \
  --materials ./materials/books ./materials/papers

# 2. 查看状态
python3 skills/rapid-domain-mastery/scripts/session.py status --session .rdm

# 3. Phase 1：学生先写自己的框架
python3 skills/rapid-domain-mastery/scripts/session.py record-attempt \
  --session .rdm --phase 1 --from-file student/attempts/phase1.md

# 教练生成骨架后解锁
python3 skills/rapid-domain-mastery/scripts/session.py save-phase-artifact \
  --session .rdm --phase 1 --from-file coach/phase-artifacts/phase1.md
python3 skills/rapid-domain-mastery/scripts/session.py reveal-phase \
  --session .rdm --phase 1
```

在 Codex 中调用时，把 `$SKILL_DIR` 指向 skill 目录：

```text
Use $rapid-domain-mastery to turn my materials into a four-phase mastery sprint with a coach/student barrier.
```

`--student-persona` 和 `--coach-persona` 是可选参数。设置后，身份会写入会话状态并自动带入四阶段 prompt。

## 仓库结构

```text
.
├── skills/
│   └── rapid-domain-mastery/
│       ├── SKILL.md
│       ├── agents/openai.yaml
│       ├── scripts/session.py
│       └── references/
│           ├── phase-prompts.md
│           └── separation-protocol.md
├── tests/
│   ├── test_session.py
│   └── test_skill_structure.py
└── .github/workflows/ci.yml
```

## 测试与 CI

本地运行：

```bash
python3 -m unittest discover -s tests -v
```

GitHub Actions 在每次 push 和 pull request 时：

- 运行单元测试；
- 编译 skill 脚本；
- 对 `session.py` 做 CLI 冒烟测试。

测试覆盖：目录隔离、阶段屏障、题目提交屏障、导出不泄漏锁定内容、会话完整性检查。

## 失效条件

该 skill 不是万能钥匙：

- 材料必须覆盖多个视角，单一教材会生成偏见框架。
- 学习者需要基础元认知，能判断 agent 输出是否合理。
- 陈述性知识效果最好；数学证明、编程、实验技能必须配合动手练习。
- 零基础者直接压缩时间可能陷入“框架幻觉”。

## 原始方法拆解

最初的 README 分析把案例拆成四个 agent 可执行阶段，核心 prompt 已迁移到 [phase-prompts.md](skills/rapid-domain-mastery/references/phase-prompts.md)，并由 [session.py](skills/rapid-domain-mastery/scripts/session.py) 增加状态机和隔断约束。

一句话总结：用 AI 的认知压缩能力替代“熟悉”阶段，把人的认知资源集中到“理解”和“生成”阶段。
