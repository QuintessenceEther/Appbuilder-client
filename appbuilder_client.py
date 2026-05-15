"""
百度千帆 AppBuilder API 封装客户端

支持 API Key 和 AK/SK 两种鉴权方式，覆盖应用模块和知识库模块的所有接口。
用于 Agent 开发时直接调用。

环境要求: conda activate Quant
依赖: pip install requests
"""

import uuid
import time
import json
import hashlib
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import urljoin

import requests


# ---------------------------------------------------------------------------
# 异常定义
# ---------------------------------------------------------------------------

class AppBuilderError(Exception):
    """AppBuilder 通用异常"""
    pass


class AuthError(AppBuilderError):
    """鉴权相关异常"""
    pass


class APIError(AppBuilderError):
    """API 返回错误"""
    pass


# ---------------------------------------------------------------------------
# Token 鉴权处理器（AK/SK）
# ---------------------------------------------------------------------------

class _BMLServiceAuth(requests.auth.AuthBase):
    """使用 AK/SK 生成签名 Token 的 requests 鉴权处理器"""

    def __init__(self, ak: str, sk: str):
        self.ak = ak
        self.sk = sk

    def __call__(self, r):
        r.headers["X-Bce-Request-ID"] = uuid.uuid4().hex
        r.headers["Sign-Time"] = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(time.time())
        )
        r.headers["Access-Key"] = self.ak

        encode_str = ""
        content_type = r.headers.get("Content-Type", "")
        if "application/json" in content_type and r.body:
            encode_str = r.body
            if isinstance(encode_str, bytes):
                encode_str = str(encode_str, encoding="utf-8")

        sign_raw = encode_str + self.sk + r.headers["X-Bce-Request-ID"] + r.headers["Sign-Time"]
        r.headers["Token"] = hashlib.sha256(sign_raw.encode("utf-8")).hexdigest()
        return r


# ---------------------------------------------------------------------------
# 主客户端
# ---------------------------------------------------------------------------

class AppBuilderClient:
    """
    百度千帆 AppBuilder API 客户端

    使用方式:

        # 方式一：仅 API Key（只能调 新建会话 + 对话）
        client = AppBuilderClient(
            host="https://your-host",
            api_key="sk-xxx",
        )

        # 方式二：API Key + AK/SK（可调所有接口）
        client = AppBuilderClient(
            host="https://your-host",
            api_key="sk-xxx",
            ak="your-access-key",
            sk="your-secret-key",
        )

        # 新建会话
        conv_id = client.create_conversation(app_id="xxx")

        # 对话（流式）
        for chunk in client.run_stream(app_id="xxx", conversation_id=conv_id, query="你好"):
            print(chunk)

        # 对话（非流式）
        result = client.run(app_id="xxx", conversation_id=conv_id, query="你好")
    """

    def __init__(
        self,
        host: str,
        api_key: Optional[str] = None,
        ak: Optional[str] = None,
        sk: Optional[str] = None,
        timeout: int = 120,
    ):
        """
        Parameters
        ----------
        host : str
            AppBuilder 服务地址，如 "http://10.58.12.179:8080"
        api_key : str, optional
            API Key，用于新建会话和对话接口
        ak : str, optional
            Access Key，用于 Token 鉴权（其他接口）
        sk : str, optional
            Secret Key，用于 Token 鉴权（其他接口）
        timeout : int
            请求超时时间（秒），默认 120
        """
        self.host = host.rstrip("/")
        self.api_key = api_key
        self.ak = ak
        self.sk = sk
        self.timeout = timeout
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # 内部工具方法
    # ------------------------------------------------------------------

    def _api_key_headers(self) -> dict:
        if not self.api_key:
            raise AuthError("需要 API Key，请在初始化 AppBuilderClient 时传入 api_key 参数")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _aksk_auth(self) -> _BMLServiceAuth:
        if not self.ak or not self.sk:
            raise AuthError("需要 AK/SK，请在初始化 AppBuilderClient 时传入 ak/sk 参数")
        return _BMLServiceAuth(self.ak, self.sk)

    def _post(self, path: str, json_data: Optional[dict] = None,
              auth: str = "api_key", **kwargs) -> requests.Response:
        """统一 POST 请求"""
        url = urljoin(self.host, path)
        if auth == "api_key":
            kwargs.setdefault("headers", self._api_key_headers())
        elif auth == "aksk":
            kwargs.setdefault("auth", self._aksk_auth())
        kwargs.setdefault("timeout", self.timeout)

        if json_data is not None:
            kwargs["json"] = json_data

        resp = self._session.post(url, **kwargs)
        if resp.status_code >= 400:
            raise APIError(f"HTTP {resp.status_code}: {resp.text[:500]}")
        return resp

    def _post_multipart(self, path: str, data: dict, files: dict,
                        auth: str = "aksk") -> requests.Response:
        """multipart/form-data 请求"""
        url = urljoin(self.host, path)
        kwargs = {"timeout": self.timeout}
        if auth == "aksk":
            kwargs["auth"] = self._aksk_auth()
        resp = self._session.post(url, data=data, files=files, **kwargs)
        if resp.status_code >= 400:
            raise APIError(f"HTTP {resp.status_code}: {resp.text[:500]}")
        return resp

    @staticmethod
    def _parse_sse_stream(response: requests.Response) -> Iterator[dict]:
        """解析 SSE 流式响应，逐条 yield JSON 数据"""
        for line in response.iter_lines(decode_unicode=True):
            if line is None:
                continue
            line = line.strip()
            if not line:
                continue
            if line.startswith("data:"):
                payload = line[5:].strip()
                if not payload:
                    continue
                try:
                    yield json.loads(payload)
                except json.JSONDecodeError:
                    continue

    # ==================================================================
    # 应用模块 —— API Key 鉴权
    # ==================================================================

    # ------------------------------------------------------------------
    # 新建会话
    # ------------------------------------------------------------------

    def create_conversation(self, app_id: str) -> dict:
        """
        新建会话，返回 conversation_id。

        Returns
        -------
        dict : {"request_id": "...", "conversation_id": "..."}
        """
        return self._post(
            "/api/ai_apaas/v1/app/conversation",
            json_data={"app_id": app_id},
            auth="api_key",
        ).json()

    # ------------------------------------------------------------------
    # 对话（非流式）
    # ------------------------------------------------------------------

    def run(
        self,
        app_id: str,
        query: str = "",
        conversation_id: str = "",
        stream: bool = False,
        file_ids: Optional[List[str]] = None,
        tools: Optional[List[dict]] = None,
        tool_choice: Optional[dict] = None,
        tool_outputs: Optional[List[dict]] = None,
        action: Optional[dict] = None,
    ) -> dict:
        """
        发起一次非流式对话，返回完整的响应 JSON。

        Parameters
        ----------
        app_id : str
            应用ID
        query : str
            用户输入
        conversation_id : str
            会话ID（首次对话可不传）
        stream : bool
            是否流式，默认 False
        file_ids : List[str], optional
            关联文件ID列表
        tools : List[dict], optional
            本地 Function Call 工具定义
        tool_choice : dict, optional
            强制执行指定组件
        tool_outputs : List[dict], optional
            上报工具调用结果
        action : dict, optional
            用于回复信息收集节点

        Returns
        -------
        dict : 完整响应
        """
        body: Dict[str, Any] = {
            "app_id": app_id,
            "query": query,
            "stream": stream,
            "conversation_id": conversation_id,
        }
        if file_ids is not None:
            body["file_ids"] = file_ids
        if tools is not None:
            body["tools"] = tools
        if tool_choice is not None:
            body["tool_choice"] = tool_choice
        if tool_outputs is not None:
            body["tool_outputs"] = tool_outputs
        if action is not None:
            body["action"] = action

        return self._post(
            "/api/ai_apaas/v1/app/conversation/runs",
            json_data=body,
            auth="api_key",
        ).json()

    # ------------------------------------------------------------------
    # 对话（流式）
    # ------------------------------------------------------------------

    def run_stream(
        self,
        app_id: str,
        query: str = "",
        conversation_id: str = "",
        file_ids: Optional[List[str]] = None,
        tools: Optional[List[dict]] = None,
        tool_choice: Optional[dict] = None,
        tool_outputs: Optional[List[dict]] = None,
        action: Optional[dict] = None,
    ) -> Iterator[dict]:
        """
        发起一次流式对话，返回 SSE 事件的迭代器。

        for event in client.run_stream(app_id="xxx", query="你好"):
            # event 是解析后的 JSON dict
            if event.get("is_completion"):
                break
            answer = event.get("answer", "")
            content = event.get("content", [])

        Yields
        ------
        dict : 每个 SSE data 块解析后的 JSON
        """
        body: Dict[str, Any] = {
            "app_id": app_id,
            "query": query,
            "stream": True,
            "conversation_id": conversation_id,
        }
        if file_ids is not None:
            body["file_ids"] = file_ids
        if tools is not None:
            body["tools"] = tools
        if tool_choice is not None:
            body["tool_choice"] = tool_choice
        if tool_outputs is not None:
            body["tool_outputs"] = tool_outputs
        if action is not None:
            body["action"] = action

        resp = self._post(
            "/api/ai_apaas/v1/app/conversation/runs",
            json_data=body,
            auth="api_key",
            stream=True,
        )
        yield from self._parse_sse_stream(resp)


    # ------------------------------------------------------------------
    # 便捷方法：回复信息收集节点
    # ------------------------------------------------------------------

    def resume_interrupt(
        self,
        app_id: str,
        conversation_id: str,
        interrupt_event_id: str,
        query: str = "",
        event_type: str = "function_call",
        stream: bool = False,
    ):
        """回复信息收集节点的中断"""
        action = {
            "action_type": "resume",
            "parameters": {
                "interrupt_event": {
                    "id": interrupt_event_id,
                    "type": event_type,
                }
            },
        }
        if stream:
            return self.run_stream(
                app_id=app_id, query=query, conversation_id=conversation_id,
                action=action,
            )
        else:
            return self.run(
                app_id=app_id, query=query, conversation_id=conversation_id,
                action=action,
            )

    # ==================================================================
    # 应用模块 —— AK/SK Token 鉴权
    # ==================================================================

    # ------------------------------------------------------------------
    # 查询应用详情
    # ------------------------------------------------------------------

    def describe_app(self, app_id: str) -> dict:
        """
        查询应用完整配置（模型、知识库、组件、背景等）。
        """
        return self._post(
            "/api/ai_apaas/v1/app?Action=DescribeApp",
            json_data={"id": app_id},
            auth="aksk",
        ).json()

    # ------------------------------------------------------------------
    # 上传文件
    # ------------------------------------------------------------------

    def upload_file(
        self,
        app_id: str,
        conversation_id: str,
        file_path: str,
    ) -> dict:
        """
        上传文件到指定会话。

        Parameters
        ----------
        app_id : str
        conversation_id : str
        file_path : str
            本地文件路径

        Returns
        -------
        dict : {"request_id": "...", "id": "...(file_id)", "conversation_id": "..."}
        """
        with open(file_path, "rb") as f:
            files = {"file": (file_path.split("/")[-1], f)}
            data = {
                "app_id": app_id,
                "conversation_id": conversation_id,
            }
            return self._post_multipart(
                "/api/ai_apaas/v1/app/conversation/file/upload",
                data=data,
                files=files,
                auth="aksk",
            ).json()

    # ------------------------------------------------------------------
    # 历史对话列表
    # ------------------------------------------------------------------

    def list_conversations(
        self,
        app_id: str,
        page: int = 1,
        limit: int = 10,
    ) -> dict:
        """查询历史对话记录列表"""
        return self._post(
            "/api/ai_apaas/v1/conversation?Action=DescribeConversations",
            json_data={"app_id": app_id, "page": page, "limit": limit},
            auth="aksk",
        ).json()

    # ------------------------------------------------------------------
    # 点赞点踩
    # ------------------------------------------------------------------

    def feedback(
        self,
        app_id: str,
        conversation_id: str,
        message_id: str,
        feedback_type: str,
        flags: Optional[List[str]] = None,
        reason: str = "",
    ) -> dict:
        """
        对对话内容进行评价。

        Parameters
        ----------
        feedback_type : str
            "upvote" / "downvote" / "cancel"
        flags : List[str], optional
            标签，如 ["答非所问"]
        reason : str
            评价原因
        """
        body: Dict[str, Any] = {
            "app_id": app_id,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "type": feedback_type,
        }
        if flags is not None:
            body["flag"] = flags
        if reason:
            body["reason"] = reason

        return self._post(
            "/api/ai_apaas/v1/app/conversation/feedback",
            json_data=body,
            auth="aksk",
        ).json()

    # ==================================================================
    # 知识库模块 —— AK/SK Token 鉴权
    # ==================================================================

    # ------------------------------------------------------------------
    # 上传文档到知识库
    # ------------------------------------------------------------------

    def upload_document_to_kb(
        self,
        kb_id: str,
        file_path: str,
        content_format: str = "rawText",
        template: str = "custom",
        parser_choices: Optional[List[str]] = None,
        separator_config: Optional[dict] = None,
        augmentation_choices: Optional[List[str]] = None,
        tags: Optional[List[dict]] = None,
    ) -> dict:
        """
        上传文档到知识库。

        Parameters
        ----------
        kb_id : str
            知识库ID
        file_path : str
            本地文档路径
        content_format : str
            "rawText" 等
        template : str
            "custom" / "default"
        parser_choices : List[str], optional
            如 ["ocr", "layoutAnalysis"]
        separator_config : dict, optional
            自定义分隔配置，如 {"separators": ["。", "！"], "targetLength": 600, "overlapRate": 0.1}
        augmentation_choices : List[str], optional
            如 ["faq", "shortSummary"]
        tags : List[dict], optional
            如 [{"key": "department", "values": ["finance"]}]

        Returns
        -------
        dict : {"requestId": "...", "documentId": "..."}
        """
        process_option: Dict[str, Any] = {"template": template}

        if parser_choices:
            process_option["parser"] = {"choices": parser_choices}

        if separator_config:
            process_option["chunker"] = {
                "choices": ["separator"],
                "separator": separator_config,
            }

        if augmentation_choices:
            process_option["knowledgeAugmentation"] = {"choices": augmentation_choices}

        if template == "custom" and "chunker" not in process_option:
            process_option["chunker"] = {
                "choices": ["separator"],
                "separator": {"separators": ["。"], "targetLength": 600, "overlapRate": 0.1},
            }

        payload = json.dumps({
            "id": kb_id,
            "source": {"type": "file"},
            "contentFormat": content_format,
            "processOption": process_option,
            "tags": tags or [],
        })

        with open(file_path, "rb") as f:
            files = {"file": (file_path.split("/")[-1], f)}
            data = {"payload": payload}
            return self._post_multipart(
                "/api/ai_apaas/v1/knowledgeBase?Action=UploadDocuments",
                data=data,
                files=files,
                auth="aksk",
            ).json()

    # ------------------------------------------------------------------
    # 导入 URL
    # ------------------------------------------------------------------

    def import_url(
        self,
        kb_id: str,
        urls: Optional[List[str]] = None,
        url_configs: Optional[List[dict]] = None,
        content_format: str = "rawText",
        template: str = "default",
        augmentation_choices: Optional[List[str]] = None,
        tags: Optional[List[dict]] = None,
    ) -> dict:
        """
        导入 URL 到知识库。

        Parameters
        ----------
        kb_id : str
        urls : List[str], optional
            URL列表（简单模式，统一深度）
        url_configs : List[dict], optional
            [{"url": "...", "urlDepth": 1, "updateFrequency": 7}, ...]
        content_format : str
        template : str
        augmentation_choices : List[str], optional
        tags : List[dict], optional
        """
        if not urls and not url_configs:
            raise ValueError("urls 和 url_configs 至少提供一组")

        source: Dict[str, Any] = {"type": "web"}
        if urls:
            source["urls"] = urls
            source["urlDepth"] = 1
        if url_configs:
            source["urlConfigs"] = url_configs

        process_option: Dict[str, Any] = {"template": template}
        if augmentation_choices:
            process_option["knowledgeAugmentation"] = {"choices": augmentation_choices}

        body: Dict[str, Any] = {
            "id": kb_id,
            "source": source,
            "contentFormat": content_format,
            "processOption": process_option,
        }
        if tags:
            body["tags"] = tags

        return self._post(
            "/api/ai_apaas/v1/knowledgeBase?Action=CreateDocuments",
            json_data=body,
            auth="aksk",
        ).json()

    # ------------------------------------------------------------------
    # 知识库文档列表
    # ------------------------------------------------------------------

    def list_documents(
        self,
        kb_id: str,
        marker: str = "",
        max_keys: int = 10,
    ) -> dict:
        """查询知识库中的文档列表"""
        return self._post(
            "/api/ai_apaas/v1/knowledgeBase?Action=DescribeDocuments",
            json_data={"knowledgeBaseId": kb_id, "marker": marker, "maxKeys": max_keys},
            auth="aksk",
        ).json()

    # ------------------------------------------------------------------
    # 删除文档
    # ------------------------------------------------------------------

    def delete_document(self, kb_id: str, document_id: str) -> dict:
        """删除知识库中的指定文档"""
        return self._post(
            "/api/ai_apaas/v1/knowledgeBase?Action=DeleteDocument",
            json_data={"knowledgeBaseId": kb_id, "documentId": document_id},
            auth="aksk",
        ).json()

    # ------------------------------------------------------------------
    # 知识库列表
    # ------------------------------------------------------------------

    def list_knowledge_bases(
        self,
        project_id: str,
        page_no: int = 1,
        page_size: int = 10,
    ) -> dict:
        """查询项目下的知识库列表"""
        return self._post(
            "/api/ai_apaas/v1/knowledgeBase?Action=DescribeKnowledgeBases",
            json_data={"projectId": project_id, "pageNo": page_no, "pageSize": page_size},
            auth="aksk",
        ).json()

    # ------------------------------------------------------------------
    # 知识库检索
    # ------------------------------------------------------------------

    def query_knowledge_base(
        self,
        query: str,
        kb_ids: List[str],
        project_id: str = "",
        search_type: str = "fulltext",
        top: int = 10,
        skip: int = 0,
        rank_score_threshold: float = 0.0,
        expand_chunk: bool = True,
        enable_cache: bool = True,
        rerank_model: str = "",
        metadata_filters: Optional[dict] = None,
    ) -> dict:
        """
        检索知识库。

        Parameters
        ----------
        query : str
            检索内容
        kb_ids : List[str]
            知识库ID列表
        project_id : str
        search_type : str
            "fulltext" 或语义检索
        top : int
            返回数量
        skip : int
            跳过条数
        rank_score_threshold : float
            排序分数阈值
        expand_chunk : bool
        enable_cache : bool
        rerank_model : str
            重排序模型名
        metadata_filters : dict, optional
            {"filters": [{"operator": "==", "field": "doc_id", "value": "xxx"}], "condition": "or"}

        Returns
        -------
        dict : {"chunks": [...]}
        """
        body: Dict[str, Any] = {
            "type": search_type,
            "query": query,
            "knowledgebase_ids": kb_ids,
            "top": top,
            "skip": skip,
            "rank_score_threshold": rank_score_threshold,
            "expand_chunk": expand_chunk,
            "enable_cache": enable_cache,
        }
        if project_id:
            body["projectId"] = project_id
        if rerank_model:
            body["rerankModelName"] = rerank_model
        if metadata_filters:
            body["metadata_filters"] = metadata_filters

        return self._post(
            "/api/ai_apaas/v1/knowledgebases/query",
            json_data=body,
            auth="aksk",
        ).json()


# ===================================================================
# Agent 专用便利层
# ===================================================================

class AppBuilderAgent:
    """
    Agent 开发便利层，封装了完整的对话生命周期管理。

    使用示例:

        agent = AppBuilderAgent(client)

        # 简单问答
        answer = agent.ask(app_id="xxx", query="你好")

        # 带工具的多轮对话
        def get_weather(location: str, unit: str = "celsius") -> str:
            return f"{location}今天天气晴朗，温度32度"

        tools = [{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "查询天气",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "城市名"},
                        "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
                    },
                    "required": ["location", "unit"]
                }
            }
        }]

        answer = agent.ask_with_functions(
            app_id="xxx",
            query="今天北京天气怎么样",
            tools=tools,
            function_map={"get_weather": get_weather},
        )
    """

    def __init__(self, client: AppBuilderClient):
        self.client = client

    def ask(
        self,
        app_id: str,
        query: str,
        conversation_id: str = "",
        file_ids: Optional[List[str]] = None,
        stream: bool = False,
    ) -> dict:
        """
        简单问答，自动管理会话创建。

        Returns
        -------
        dict : 包含 answer, conversation_id, message_id 等
        """
        if not conversation_id:
            conv = self.client.create_conversation(app_id=app_id)
            conversation_id = conv["conversation_id"]

        result = self.client.run(
            app_id=app_id,
            query=query,
            conversation_id=conversation_id,
            file_ids=file_ids,
            stream=stream,
        )

        result["_conversation_id"] = conversation_id
        return result

    def ask_stream(
        self,
        app_id: str,
        query: str,
        conversation_id: str = "",
        file_ids: Optional[List[str]] = None,
    ) -> Iterator[dict]:
        """流式问答的迭代器"""
        if not conversation_id:
            conv = self.client.create_conversation(app_id=app_id)
            conversation_id = conv["conversation_id"]

        for event in self.client.run_stream(
            app_id=app_id,
            query=query,
            conversation_id=conversation_id,
            file_ids=file_ids,
        ):
            event["_conversation_id"] = conversation_id
            yield event

    def ask_with_functions(
        self,
        app_id: str,
        query: str,
        tools: List[dict],
        function_map: dict,
        conversation_id: str = "",
        max_rounds: int = 5,
    ) -> dict:
        """
        带 Function Call 的自动多轮对话。

        Parameters
        ----------
        tools : List[dict]
            OpenAI 格式的工具定义
        function_map : dict
            {"function_name": callable} 映射
        max_rounds : int
            最大自动回调轮数

        Returns
        -------
        dict : 最终回答
        """
        if not conversation_id:
            conv = self.client.create_conversation(app_id=app_id)
            conversation_id = conv["conversation_id"]

        for _ in range(max_rounds):
            result = self.client.run(
                app_id=app_id,
                query=query,
                conversation_id=conversation_id,
                tools=tools,
            )

            # 检查是否有中断/工具调用需要处理
            tool_calls = self._extract_tool_calls(result)
            if not tool_calls:
                result["_conversation_id"] = conversation_id
                return result

            # 执行本地函数并上报结果
            tool_outputs = []
            for tc in tool_calls:
                func = function_map.get(tc["name"])
                if func:
                    output = func(**tc.get("arguments", {}))
                    tool_outputs.append({
                        "tool_call_id": tc["id"],
                        "output": str(output),
                    })

            if tool_outputs:
                result = self.client.run(
                    app_id=app_id,
                    conversation_id=conversation_id,
                    tool_outputs=tool_outputs,
                )
                result["_conversation_id"] = conversation_id
                return result

        result["_conversation_id"] = conversation_id
        return result

    def _extract_tool_calls(self, result: dict) -> List[dict]:
        """从响应中提取工具调用信息"""
        tool_calls = result.get("tool_calls", [])
        if not tool_calls:
            for item in result.get("content", []):
                if item.get("event_type") == "Interrupt":
                    outputs = item.get("outputs", {})
                    text = outputs.get("text", {})
                    fn_call = text.get("function_call", {})
                    if fn_call:
                        tool_calls.append({
                            "id": fn_call.get("tool_call_id", ""),
                            "name": fn_call.get("name", ""),
                            "arguments": fn_call.get("arguments", {}),
                        })
        return tool_calls

    def collect_answer(self, content: List[dict]) -> str:
        """从 content 数组中提取最终的文本回答"""
        texts = []
        for item in content:
            if item.get("content_type") == "text":
                output_text = item.get("outputs", {}).get("text", "")
                if isinstance(output_text, str) and output_text.strip():
                    texts.append(output_text)
        return "\n".join(texts)

    def close(self):
        self.client._session.close()
