# RDM Executable Rollout

把 `rapid-domain-mastery` 从“陈述性学习闭环”扩到“概念层 + 执行层”的双回路学习框架。

## 目标

- 保留 RDM 已有的“先学生、后教练”隔断。
- 对程序性技能引入即时环境反馈，不再把压力测试只放在教练文案里。
- 让编程教学场景支持“先提交产物、再看讲解”的学习顺序。

## 分 Phase 落地

### Phase 1：基础层

- 会话增加 `assessment_mode`：
  - `conceptual`
  - `executable`
- 为 executable 模式增加最小目录结构：
  - `student/artifacts/`
  - `shared/tasks/`
  - `shared/runtime-feedback/`
- 在状态文件里持久化 `workspace_root`，为后续运行检查做准备。
- 文档明确：RDM 可以扩展到程序性技能，但 executable 模式仍是渐进增强。

### Phase 2：最小执行回路

- 为 executable 模式增加 Phase 2 的最小闭环：
  - 创建任务
  - 提交学生产物
  - 运行检查命令
  - 保存即时 runtime feedback
- 环境反馈即时可见，教练反馈仍延迟 reveal。
- 最小可运行对象优先支持：
  - diff / patch
  - 单文件源码
  - 指定测试命令

### Phase 3：双反馈分层

- 把反馈拆成两层：
  - `runtime feedback`：编译器、测试、类型检查、lint 输出
  - `coach feedback`：hint、解释、参考实现、迁移点评
- `next` / `check` / `export` 都能理解这两层反馈。

### Phase 4：迁移与固化

- Phase 3 的迁移任务改成陌生约束下的最小程序。
- Phase 4 固化为：
  - 概念图
  - 错题本
  - 回归用例册
  - 典型修复手法

## 执行原则

1. 编译器和测试器是第一反馈源，不受 reveal 隔断限制。
2. 标准答案、hint、参考实现仍属于教练内容，继续延迟 reveal。
3. 概念层和执行层共享同一会话状态机，不做两套互不兼容的 workflow。
