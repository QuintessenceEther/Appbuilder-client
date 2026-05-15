# 百度千帆 AppBuilder API 文档

> 版本：AB31 | 日期：2026-03-04
> 内部接口文档，包含应用、知识库两大模块的完整 API 说明。

---

## 一、鉴权方式

### 1. API Key（推荐用于新建会话和对话）

- 在千帆控制台 → API Key 页面创建
- 仅适用于 **新建会话** 和 **对话** 两个接口
- 调用方式：Header 中传入 `Authorization: Bearer <APIKey>`

```
Authorization: Bearer sk-93f782fe-1186-443c-7f5b-7349c2bcedc0
```

### 2. AK/SK 生成 Token（用于其他接口）

- 使用个人 Access Key (AK) 和 Secret Key (SK) 生成签名
- 支持除新建会话和对话外的所有接口
- Token 生成算法：`SHA256(requestBody + SK + requestId + signTime)`

**请求中需要携带的 Header：**

| Header | 说明 |
|--------|------|
| `X-Bce-Request-ID` | UUID 请求ID |
| `Sign-Time` | 签名时间，格式 `yyyy-MM-dd HH:mm:ss` |
| `Access-Key` | AK 值 |
| `Token` | SHA256 签名结果 |

**Python Token 生成实现：**

```python
import uuid
import time
import hashlib
import requests.auth

class BMLServiceAuth(requests.auth.AuthBase):
    def __init__(self, ak, sk, user_id=None):
        self.ak = ak
        self.sk = sk
        self.user_id = user_id

    def __call__(self, r):
        r.headers["X-Bce-Request-ID"] = uuid.uuid4().hex
        r.headers["Sign-Time"] = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(time.time())
        )
        r.headers["Access-Key"] = self.ak

        encode_str = ""
        if "application/json" in r.headers.get("Content-Type", "") and r.body:
            encode_str = r.body
            if isinstance(encode_str, bytes):
                encode_str = str(encode_str, encoding="utf-8")
        encode_str = (
            encode_str
            + self.sk
            + r.headers["X-Bce-Request-ID"]
            + r.headers["Sign-Time"]
        )
        sha256 = hashlib.sha256(bytes(encode_str, encoding="utf-8"))
        r.headers["Token"] = sha256.hexdigest()
        return r
```

### 3. 密钥鉴权（即将下线，不推荐）

---

## 二、应用模块 API

### 2.1 新建会话

```
POST http(s)://{host}:{port}/api/ai_apaas/v1/app/conversation
```

**鉴权方式：** API Key

**请求 Body：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `app_id` | string | 是 | 应用ID |

**请求示例：**

```bash
curl --location 'http://IP:PORT/api/ai_apaas/v1/app/conversation' \
--header 'Authorization: Bearer sk-93f782fe-1186-443c-7f5b-7349c2bcedc0' \
--header 'Content-Type: application/json' \
--data '{"app_id": "91f2a62f-a06c-438c-924d-1177dc2c5a1e"}'
```

**响应示例：**

```json
{
  "request_id": "73316d1c-546b-4cb2-a1d9-4fca7bc8a096",
  "conversation_id": "7c193c13-8ae9-442e-bb2f-7b545cb11245"
}
```

---

### 2.2 对话

这是核心接口，用于向 Agent 应用发送消息，支持普通对话、流式/非流式、Function Call、工具调用结果上报、信息收集节点回复等多种场景。

```
POST http(s)://{host}:{port}/api/ai_apaas/v1/app/conversation/runs
```

**鉴权方式：** API Key

**请求 Body 参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `app_id` | string | 是 | 应用ID |
| `query` | string | 否 | 用户输入内容 |
| `stream` | boolean | 否 | `true`=SSE流式返回，`false`=一次性返回 |
| `conversation_id` | string | 否 | 会话ID（首次对话可不传） |
| `file_ids` | string[] | 否 | 文件ID数组 |
| `tools` | object[] | 否 | 本地函数定义（Function Call） |
| `tool_choice` | object | 否 | 强制执行指定组件 |
| `tool_outputs` | object[] | 否 | 上报工具调用结果 |
| `action` | object | 否 | 回复信息收集节点 |

**响应数据结构：**

```json
{
  "request_id": "xxx",
  "date": "2024-10-24T07:18:42Z",
  "answer": "",
  "conversation_id": "xxx",
  "message_id": "xxx",
  "is_completion": false,
  "content": [
    {
      "result_type": "",
      "event_code": 0,
      "event_message": "",
      "event_type": "function_call",
      "event_id": "1",
      "event_status": "done",
      "content_type": "function_call",
      "visible_scope": "",
      "outputs": {
        "text": {
          "arguments": {},
          "component_code": "ChatAgent",
          "component_name": "聊天助手"
        }
      },
      "usage": {
        "prompt_tokens": 536,
        "completion_tokens": 0,
        "total_tokens": 536,
        "name": "eb-speed-appbuilder",
        "type": "chat"
      }
    }
  ]
}
```

**`content` 中的 `event_type` 常见值：**
- `function_call` — 组件/工具调用
- `ChatAgent` — 聊天助手输出
- `thought` — 思考过程
- `chat_reasoning` — 推理过程
- `Interrupt` — 信息收集节点中断

**`event_status` 常见值：**
- `preparing` — 准备中
- `running` — 执行中
- `done` — 执行完成
- `success` — 成功结束
- `interrupt` — 等待用户回复

**流式响应：** 当 `stream: true` 时，响应以 SSE 格式返回，每条数据以 `data: ` 前缀，`is_completion: true` 表示结束。

**对话场景示例：**

**(1) 普通对话：**
```bash
curl --location --request POST 'http://IP:PORT/api/ai_apaas/v1/app/conversation/runs' \
--header 'Authorization: Bearer sk-93f782fe-1186-443c-7f5b-7349c2bcedc0' \
--header 'Content-Type: application/json' \
--data '{
    "app_id": "80048546-2920-4529-bb10-28b1cc57b5bf",
    "query": "统计这几所学校小学生有多少",
    "stream": true,
    "conversation_id": "411effa0-5f25-4fdd-9d62-1dad9201f8b7",
    "file_ids": ["cdd1e194-cfb7-4173-a154-795fae8535d9"]
}'
```

**(2) 强制执行组件：**
```json
{
    "app_id": "xxx",
    "query": "你好",
    "stream": false,
    "conversation_id": "xxx",
    "tool_choice": {
        "type": "function",
        "function": {
            "name": "QueryFlights",
            "input": {"flight_number": "CZ8889"}
        }
    }
}
```

**(3) Function Call + tools 定义：**
```json
{
    "app_id": "xxx",
    "query": "今天北京的天气怎么样",
    "stream": false,
    "conversation_id": "xxx",
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "get_current_weather",
                "description": "仅支持中国城市的天气查询",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "城市名称"},
                        "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
                    },
                    "required": ["location", "unit"]
                }
            }
        }
    ]
}
```

**(4) 上报工具调用结果：**
```json
{
    "app_id": "xxx",
    "stream": false,
    "conversation_id": "xxx",
    "tool_outputs": [
        {
            "tool_call_id": "dc7c1d58-cbe3-40be-a5ec-a4fe4c7fb6ef",
            "output": "北京今天天气晴朗，温度32度"
        }
    ]
}
```

**(5) 回复信息收集节点：**
```json
{
    "app_id": "xxx",
    "query": "这是回复信息收集节点的消息",
    "stream": false,
    "conversation_id": "xxx",
    "action": {
        "action_type": "resume",
        "parameters": {
            "interrupt_event": {
                "id": "0",
                "type": "function_call"
            }
        }
    }
}
```

---

### 2.3 查询应用详情

```
POST http(s)://{host}:{port}/api/ai_apaas/v1/app?Action=DescribeApp
```

**鉴权方式：** AK/SK Token

**请求 Body：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 应用ID |

**响应包含：** 应用基本信息、instruction、exampleQueries、followUpQueries、components、knowledgeBaseConfig（含 retrieval 策略）、modelConfig（plan/chat 模型及超参）、background（含 mobile/pc 配置）等。

---

### 2.4 上传文件

```
POST http(s)://{host}:{port}/api/ai_apaas/v1/app/conversation/file/upload
```

**鉴权方式：** AK/SK Token

**请求方式：** multipart/form-data

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | file | 是 | 文件 |
| `app_id` | string | 是 | 应用ID |
| `conversation_id` | string | 是 | 会话ID |

**响应示例：**
```json
{
    "request_id": "43552d7c-020f-443d-be3f-2be7d2594ec9",
    "id": "f9d178b1-e205-49b4-a9ab-e3887c9e0e14",
    "conversation_id": "2fdc67d9-cc7a-4148-9cac-50e959e106e6"
}
```

---

### 2.5 历史对话记录列表

```
POST http(s)://{host}:{port}/api/ai_apaas/v1/conversation?Action=DescribeConversations
```

**鉴权方式：** AK/SK Token

**请求 Body：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `app_id` | string | 是 | 应用ID |
| `page` | int | 否 | 页码 |
| `limit` | int | 否 | 每页条数 |

---

### 2.6 点赞点踩

```
POST http(s)://{host}:{port}/api/ai_apaas/v1/app/conversation/feedback
```

**鉴权方式：** AK/SK Token

**请求 Body：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `app_id` | string | 是 | 应用ID |
| `conversation_id` | string | 是 | 会话ID |
| `message_id` | string | 是 | 消息ID |
| `type` | string | 是 | `upvote` / `downvote` / `cancel` |
| `flag` | string[] | 否 | 标签，如 `["答非所问"]` |
| `reason` | string | 否 | 评价原因 |

---

## 三、知识库模块 API

所有知识库接口使用 AK/SK Token 鉴权。

### 3.1 上传文档到知识库

```
POST http(s)://{host}:{port}/api/ai_apaas/v1/knowledgeBase?Action=UploadDocuments
```

**Content-Type：** multipart/form-data

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `file` | file | 文档文件 |
| `payload` | JSON string | 包含 id、source、contentFormat、processOption、tags 等 |

**payload 结构：**

```json
{
    "id": "知识库ID",
    "source": {"type": "file"},
    "contentFormat": "rawText",
    "processOption": {
        "template": "custom",
        "parser": {"choices": ["ocr", "layoutAnalysis"]},
        "chunker": {
            "choices": ["separator"],
            "separator": {
                "separators": ["!", "?", "。"],
                "targetLength": 600,
                "overlapRate": 0.1
            },
            "prependInfo": ["title", "filename"]
        },
        "knowledgeAugmentation": {"choices": ["faq", "shortSummary"]}
    },
    "tags": [{"key": "hello", "values": ["world"]}]
}
```

**processOption 枚举值：**
- `template`: `custom` / `default`
- `parser.choices`: `ocr` / `layoutAnalysis`
- `chunker.choices`: `separator` / `semantic`
- `knowledgeAugmentation.choices`: `faq` / `shortSummary` / `spokenQuery`

---

### 3.2 导入 URL

```
POST http(s)://{host}:{port}/api/ai_apaas/v1/knowledgeBase?Action=CreateDocuments
```

**Content-Type：** application/json

**Body 核心参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | string | 知识库ID |
| `source.type` | string | 固定为 `web` |
| `source.urlDepth` | int | 抓取深度 |
| `source.urls` | string[] | URL列表（简单模式） |
| `source.urlConfigs` | object[] | URL配置列表（可分别设置深度和刷新频率） |
| `contentFormat` | string | 内容格式 |
| `processOption` | object | 处理选项，同上 |
| `tags` | object[] | 标签 |

---

### 3.3 查询知识库文档列表

```
POST http(s)://{host}:{port}/api/ai_apaas/v1/knowledgeBase?Action=DescribeDocuments
```

**请求 Body：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `knowledgeBaseId` | string | 是 | 知识库ID |
| `marker` | string | 否 | 分页标记 |
| `maxKeys` | int | 否 | 每页最大数量 |

---

### 3.4 删除文档

```
POST http(s)://{host}:{port}/api/ai_apaas/v1/knowledgeBase?Action=DeleteDocument
```

**请求 Body：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `knowledgeBaseId` | string | 是 | 知识库ID |
| `documentId` | string | 是 | 文档ID |

---

### 3.5 知识库列表

```
POST http(s)://{host}:{port}/api/ai_apaas/v1/knowledgeBase?Action=DescribeKnowledgeBases
```

**请求 Body：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `projectId` | string | 是 | 项目ID |
| `pageNo` | int | 否 | 页码 |
| `pageSize` | int | 否 | 每页条数 |

---

### 3.6 知识库检索

```
POST http(s)://{host}:{port}/api/ai_apaas/v1/knowledgebases/query
```

**请求 Body：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `type` | string | `fulltext` 全文检索 或 语义检索 |
| `query` | string | 检索查询内容 |
| `knowledgebase_ids` | string[] | 知识库ID列表 |
| `rerankModelName` | string | 重排序模型名称 |
| `projectId` | string | 项目ID |
| `metadata_filters` | object | 元数据过滤 `{"filters": [...], "condition": "or"/"and"}` |
| `top` | int | 返回Top N结果 |
| `skip` | int | 跳过条数 |
| `rank_score_threshold` | float | 排序分数阈值 |
| `expand_chunk` | boolean | 是否展开chunk |
| `enable_cache` | boolean | 是否启用缓存 |

**响应包含：** `chunks` 数组，每个 chunk 包含 `chunk_id`, `content`, `retrieval_score`, `rank_score`, `locations`（页面坐标）, `children`（子chunk）, `meta` 等。

---

## 四、典型调用流程

```
1. 创建会话
   POST /api/ai_apaas/v1/app/conversation  (API Key)
   → 获得 conversation_id

2. 发起对话（支持多轮）
   POST /api/ai_apaas/v1/app/conversation/runs  (API Key)
   → 普通问答、带文件问答、Function Call、工具调用

3. [可选] 上传文件到会话
   POST /api/ai_apaas/v1/app/conversation/file/upload  (Token)

4. [可选] 知识库操作
   UploadDocuments → CreateDocuments → DescribeDocuments → query
```

---

## 五、常见 event_type 含义

| event_type | 说明 |
|------------|------|
| `function_call` | 组件/工具调用 |
| `ChatAgent` | 聊天助手文本输出 |
| `thought` | 大模型思考过程 |
| `chat_reasoning` | 大模型推理过程 |
| `Interrupt` | 信息收集节点，需要用户回复后继续 |

## 六、stream vs 非stream

- **stream=true：** SSE 格式返回，`is_completion: false` 表示中间数据，`is_completion: true` 且 `content: []` 表示流结束
- **stream=false：** 一次性返回完整 JSON，`is_completion: null`
