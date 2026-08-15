# 教练/学生隔断协议

本协议是 Rapid Domain Mastery 的防假学习机制。核心原则：**先学生、后教练**，即学生先产出、教练后评价。教练的标准答案、推理链和反馈在对应的学生尝试存在且非空之前，不能生成、写入或读取。

## 目录边界

| 目录 | 所有者 | 允许存在的内容 |
|---|---|---|
| `student/attempts/` | 学生 | 学生自己写的框架、边界推理、个人知识资产初稿 |
| `student/answers/` | 学生 | 学生对每道区分题的答案和推理过程 |
| `student/notes/` | 学生 | 学习笔记、标记、未定稿想法 |
| `coach/phase-artifacts/` | 教练 | 只存放已经 reveal 的 Phase 1/3/4 产物 |
| `coach/feedback/` | 教练 | 只存放已经 reveal 的逐轮反馈 |
| `shared/questions/` | 双方 | 题目本身，不含标准答案或“陷阱”解释 |
| `state/locked/` | 系统 | 未 reveal 的教练阶段产物和逐轮反馈 |
| `state/session.json` | 系统 | 会话状态、材料清单、隔断状态 |

教练内容不应写入 `student/` 或 `shared/`。学生内容可以读取，但教练不得替学生生成。

## 操作顺序

### Phase 1 / 3 / 4

1. 学生先写 `student/attempts/phase{N}.md`。
2. 使用 `record-attempt` 把该文件登记为非空尝试。
3. 教练生成阶段产物。
4. 使用 `save-phase-artifact` 把产物登记到 `state/locked/phase-artifacts/phase{N}.md`。脚本会再次检查学生尝试是否非空，但此时内容仍未对学生解锁。
5. 使用 `reveal-phase` 把教练产物复制到 `coach/phase-artifacts/phase{N}.md` 并显示给学生，同时把该阶段标记为已解锁。

在步骤 2 之前调用 `save-phase-artifact` 会失败；在步骤 4 之前调用 `reveal-phase` 会失败；在步骤 5 之前导出会话不会带出该教练产物。

### Phase 2

1. 教练把题目写入 `shared/questions/{id}.md`，并用 `start-question` 登记。
2. 学生作答到 `student/answers/{id}.round{n}.md`，并用 `submit` 登记。答案至少包含两行非空内容：结论，以及推理。
3. 教练生成当前轮反馈，并用 `save-feedback` 登记到 `state/locked/feedback/{id}/round{n}.md`。
4. 使用 `reveal-feedback` 把反馈复制到 `coach/feedback/{id}/round{n}.md` 并显示给学生，同时把该轮反馈标记为已解锁。
5. 若反馈包含追问，使用 `request-followup` 打开下一轮；下一轮仍重复步骤 2-4。

在步骤 2 之前调用 `save-feedback` 或 `reveal-feedback` 会失败；在步骤 4 之前导出会话不会带出该反馈。

## 代理行为规则

- 不直接读取 `coach/` 目录。即使文件系统允许，也应只通过 `reveal-phase` 和 `reveal-feedback` 读取。
- 不直接读取 `state/locked/` 目录。该目录属于系统隔断的一部分，比 `coach/` 更不该被代理直接读取。
- 不要为学生补写答案。学生文件中的内容必须来自学生自己的输入；代理只能转写学生明确口述的内容，不得补全推理。
- 不要提前暗示正确答案。学生卡住时，可以追问、缩小范围或让学生写出“目前不确定的地方”，但不能给出判断或修正推理。
- 教练反馈应定位逻辑漏洞，而不是只给答案。参考 `phase-prompts.md` 中的反馈格式。
- 不要跳阶段操作。脚本会校验当前阶段，Phase 1 完成前不能开始 Phase 2，后续阶段同理。
- 不要覆盖旧轮次。Phase 2 的追问必须新开 round，保留上一轮答案和反馈供复盘。

## 失效模式

| 假学习信号 | 处理方式 |
|---|---|
| 学生直接说“把答案给我” | 拒绝，并要求先提交自己的答案和推理 |
| 学生复制题目内容却没有推理 | 将状态保持在 open，追问“你的推理过程是什么” |
| 教练把标准答案写进 `shared/questions/` | 立即移到 `coach/feedback/` 并重新生成不含答案的题目 |
| 教练在未提交时直接 `cat coach/` | 停止操作，按协议重新走一遍 |
| 导出的文件包含未解锁教练内容 | `export` 会排除锁定内容；若发现泄漏，检查会话状态 |

## 校验命令

```bash
python3 "$SKILL_DIR/scripts/session.py" check --session .rdm
```

该命令检查：

- 已解锁的阶段是否同时拥有学生尝试和教练产物路径。
- 已 reviewed 的题目是否一定存在学生答案。
- 有反馈的题目是否已经 reviewed。
- 材料文件是否在会话开始后被替换或改写。
- `coach/` 目录中是否出现未登记到状态文件的越权产物。
- `state/locked/` 中是否出现未登记到状态文件的越权产物。
