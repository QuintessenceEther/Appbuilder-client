"""
demo_route1_app.py
路线一：直接调用已建好的 AppBuilder 应用
只需 API Key，应用内部已配好 文档解析→知识库→大模型 流水线

使用方法：
    1. 填好下方四个配置
    2. conda activate Quant
    3. python demo_route1_app.py
"""

from appbuilder_client import AppBuilderClient

# ============================================
# 配置区 —— 替换成你自己的值
# ============================================
HOST        = "http://你的内网IP:8080"
API_KEY     = "sk-你的APIKey"                  # 千帆控制台 → API Key
APP_ID      = "你的应用ID"

# 测试用的问题
TEST_QUERIES = [
    "你好，请介绍一下你自己",
    "帮我总结一下已上传文档的核心内容",
]
# ============================================


def main():
    client = AppBuilderClient(host=HOST, api_key=API_KEY)

    # ---------- 1. 新建会话 ----------
    print("=" * 60)
    print("1. 新建会话")
    conv = client.create_conversation(app_id=APP_ID)
    conversation_id = conv["conversation_id"]
    print(f"   conversation_id: {conversation_id}")
    print()

    # ---------- 2. 多轮对话 ----------
    for i, query in enumerate(TEST_QUERIES, 1):
        print("=" * 60)
        print(f"2.{i} 对话 - 用户: {query}")

        # ---- 非流式 ----
        result = client.run(
            app_id=APP_ID,
            query=query,
            conversation_id=conversation_id,
        )

        print(f"   answer: {result.get('answer', '(无文本回答)')}")
        print(f"   message_id: {result.get('message_id', 'N/A')}")

        # 打印 content 事件摘要
        for item in result.get("content", []):
            event_type = item.get("event_type", "")
            status     = item.get("event_status", "")
            text       = item.get("outputs", {}).get("text", "")
            if isinstance(text, str) and len(text) > 100:
                text = text[:100] + "..."
            print(f"   [{event_type}] {status} → {text}")
        print()

    # ---------- 3. 流式对话 ----------
    print("=" * 60)
    print("3. 流式对话测试")
    query = "用一句话介绍你自己"
    print(f"   用户: {query}")
    print("   回答: ", end="", flush=True)

    for event in client.run_stream(
        app_id=APP_ID,
        query=query,
        conversation_id=conversation_id,
    ):
        answer_chunk = event.get("answer", "")
        if answer_chunk:
            print(answer_chunk, end="", flush=True)
        if event.get("is_completion"):
            break
    print("\n")

    print("=" * 60)
    print("全部测试通过 ✓")


if __name__ == "__main__":
    main()
