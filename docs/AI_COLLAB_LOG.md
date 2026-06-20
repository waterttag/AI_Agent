# AI 协同记录

## 使用的 AI 工具

| 工具 | 用途 | 占比 |
|------|------|:---:|
| **Claude Code (CLI)** | 主力开发：架构设计、代码生成、调试、部署测试 | ~90% |
| **DeepSeek API (deepseek-chat)** | 游戏内容生成：HTML5游戏代码 | ~10% |

## 关键 Prompt 策略

### 1. 系统架构设计
```
设计一个 AI Native 互动游戏 Web 平台 MVP...
- 输入：测试文档(.docx)全文
- 输出：技术栈选型 + 项目结构 + DB Schema + API设计 + AI Agent Harness + 2天计划
- 迭代：1轮 → 确认Docker/LLM/前端偏好 → 终版方案
```

### 2. AI Agent Harness 提示词工程
```
核心 System Prompt:
- 要求输出自包含HTML5游戏(Phaser.js CDN 或 Canvas API)
- 强制约束：game loop、交互性、响应式设计
- 安全约束：禁止eval()、CDN白名单
- 素材注入：Vision API → 文本描述 → prompt嵌入
- Temperature: 0.8 (增强创意)

自动修复 Prompt:
- 将校验错误列表反馈给LLM
- "Fix the errors, output corrected complete HTML"
- Temperature: 0.5 (精确修复)
```

### 3. 前后端代码生成
```
每个文件的生成模式：
1. 描述文件职责 + 输入输出
2. 生成完整代码
3. 检验：检查导入、类型一致性、异常处理
```

## AI 辅助占比

| 类别 | AI生成 | 人工调整 |
|------|:---:|:---:|
| 项目结构/配置 | 95% | 5% (端口/路径适配) |
| 后端 ORM/Schemas | 95% | 5% (关系加载) |
| 后端 API 路由 | 90% | 10% (权限校验) |
| AI Agent Harness | 90% | 10% (DeepSeek适配器) |
| 前端组件 | 85% | 15% (UI细节) |
| 种子游戏HTML | 10% | 90% (手写) |
| 文档 | 80% | 20% (补充) |

## 人工修正的重点问题

1. **SQLAlchemy greenlet 错误**：`GameResponse`序列化触发懒加载assets关系，修复为 `selectinload`
2. **MinIO policy 序列化**：`set_bucket_policy` 需要 JSON 字符串而非 dict
3. **DeepSeek 适配器**：基于 `OpenAIAdapter` 继承，仅改 `base_url`；`describe_image` 提供文本fallback
4. **端口冲突**：Redis 6379被占用，改为6380；后端8000被占用，切换端口
5. **数据库路径**：`seed.py` 和 backend `uvicorn` 的 SQLite 路径需要统一
6. **作者名显示**：`GameResponse` 缺少 `author_name`，补充关联查询 + schema字段

## 开发过程日志

| 时间 | 阶段 | 关键操作 |
|------|------|---------|
| 22:00 | 需求分析 | 读取.docx，输出架构方案 |
| 22:15 | 脚手架 | docker-compose, .env, 目录结构 |
| 22:20 | 后端核心 | FastAPI, SQLAlchemy, 4个ORM模型 |
| 22:30 | 后端API | Auth/Game/Asset/Task 18个端点 |
| 22:35 | Agent Harness | 适配器工厂 + System Prompt + 校验器 + 打包器 |
| 22:40 | Celery | Worker配置 + generate_game_task |
| 22:45 | 前端 | Vite+React+Tailwind+shadcn + 5个页面 |
| 22:50 | 种子数据 | 3个HTML5游戏 + seed.py |
| 22:55 | 联调 | Docker启动, MinIO验证, API测试 |
| 23:00 | DeepSeek | 适配器集成, API Key配置 |
| 23:04 | 生成验证 | DeepSeek成功生成Pong游戏(23s) |
| 23:10 | 补齐 | 作者名/Play状态/Agent可视化/文档 |
