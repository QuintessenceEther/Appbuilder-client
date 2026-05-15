# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 语言
始终使用中文回复。

## 项目概述
基于百度千帆 AppBuilder API（内部版 AB31）的智能体开发项目。通过封装 AppBuilder 的 REST API，构建可调用大模型、知识库、Function Call 的 Agent 应用。

## Python 环境
使用 conda 环境 `Quant`：
```bash
conda activate Quant
```
- **内网 Python 版本为 3.7**，代码需兼容 3.7 语法
- 禁止使用 Python 3.9+ 的类型注解（如 `list[str]`、`dict[str, Any]`），必须用 `typing` 模块：`List[str]`、`Dict[str, Any]`
- 唯一外部依赖为 `requests`，已安装

## 项目文件结构

| 文件 | 用途 |
|------|------|
| `baidu_appbuilder_api.md` | AppBuilder API 完整接口文档 |
| `appbuilder_client.py` | Python 封装客户端，智能体开发的唯一入口 |
| `demo_route1_app.py` | 路线一 demo：直接调已建应用（仅需 API Key） |
| `demo_route2_custom.py` | 路线二 demo：自定义流程编排（需 API Key + AK/SK） |
| `AB_API_3_1.docx` | 原始 Word 接口文档（源文件，勿删） |

## 核心架构：`appbuilder_client.py`

### 两层设计

**`AppBuilderClient`** — 底层 HTTP 客户端，一一对应 API 接口：
- 鉴权机制：API Key（用于 `create_conversation` 和 `run` 系列）和 AK/SK Token 签名（用于其他所有接口）
- 所有接口均为 POST，基路径 `/api/ai_apaas/v1/`
- 流式响应通过 SSE 解析，`_parse_sse_stream()` 处理 `data:` 行

**`AppBuilderAgent`** — 高层 Agent 便利层：
- `ask()` — 自动创建会话 + 问答，不传 `conversation_id` 时自动新建
- `ask_stream()` — 流式版本
- `ask_with_functions()` — 带 Function Call 的自动多轮，检测响应中的 `Interrupt` 事件，自动执行本地函数并上报结果（最多 5 轮）
- `collect_answer()` — 从响应的 `content` 数组中提取 `content_type == "text"` 的纯文本

### 鉴权分界线（必须记住）

| 鉴权方式 | 适用接口 |
|----------|----------|
| API Key（Header: `Authorization: Bearer xxx`） | `create_conversation`、`run`/`run_stream`（对话） |
| AK/SK Token（多 Header 签名） | 其他所有接口：describe_app、upload_file、list_conversations、feedback、知识库全部接口 |

错误使用鉴权方式会导致 401/403。

### API 端点速查

```
POST /api/ai_apaas/v1/app/conversation          # 新建会话 (API Key)
POST /api/ai_apaas/v1/app/conversation/runs      # 对话 (API Key)
POST /api/ai_apaas/v1/app?Action=DescribeApp      # 应用详情 (AK/SK)
POST /api/ai_apaas/v1/app/conversation/file/upload # 上传文件 (AK/SK)
POST /api/ai_apaas/v1/conversation?Action=DescribeConversations # 会话列表 (AK/SK)
POST /api/ai_apaas/v1/app/conversation/feedback   # 点赞点踩 (AK/SK)
POST /api/ai_apaas/v1/knowledgeBase?Action=DescribeKnowledgeBases # 知识库列表 (AK/SK)
POST /api/ai_apaas/v1/knowledgeBase?Action=UploadDocuments # 上传文档 (AK/SK)
POST /api/ai_apaas/v1/knowledgeBase?Action=CreateDocuments  # 导入URL (AK/SK)
POST /api/ai_apaas/v1/knowledgeBase?Action=DescribeDocuments # 文档列表 (AK/SK)
POST /api/ai_apaas/v1/knowledgeBase?Action=DeleteDocument   # 删除文档 (AK/SK)
POST /api/ai_apaas/v1/knowledgebases/query       # 知识库检索 (AK/SK)
```

### 对话响应的关键字段

- `answer` — 主回答文本（流式时逐步累积）
- `content[]` — 组件执行事件数组，每个事件包含 `event_type`、`event_status`、`content_type`、`outputs`
- `is_completion` — 流式结束标记；非流式为 `null`
- 常见 `event_type`：`function_call`（组件调用）、`ChatAgent`（文本输出）、`thought`（思考）、`Interrupt`（中断等待用户输入）
- 工具调用从 `content[].outputs.text.function_call` 或顶层 `tool_calls` 中提取
