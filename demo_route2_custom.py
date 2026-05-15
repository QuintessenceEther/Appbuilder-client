"""
demo_route2_custom.py
路线二：自己写流程，编排每一步
需要 API Key + AK/SK

流程：上传文档 → 知识库检索 → 拼 prompt → 大模型回答

使用方法：
    1. 填好下方配置
    2. conda activate Quant
    3. python demo_route2_custom.py
"""

from appbuilder_client import AppBuilderClient

# ============================================
# 配置区 —— 替换成你自己的值
# ============================================
HOST        = "http://你的内网IP:8080"
API_KEY     = "sk-你的APIKey"                  # 千帆控制台 → API Key
AK          = "你的AccessKey"                   # 千帆控制台 → 用户详情 → AK
SK          = "你的SecretKey"                   # 千帆控制台 → 用户详情 → SK
APP_ID      = "你的应用ID"
KB_ID       = "你的知识库ID"
PROJECT_ID  = "你的项目ID"

# 你想要检索并提问的问题
TEST_QUERY = "根据已上传的文档，回答以下问题：XXX是什么？"
# ============================================


def pprint(title: str, data: dict, max_str: int = 200):
    """辅助打印，截断过长的字符串"""
    import json
    s = json.dumps(data, ensure_ascii=False, indent=2)
    if len(s) > max_str:
        s = s[:max_str] + "\n  ... (已截断)"
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    print(s)


def main():
    # 初始化客户端 —— 三种凭据一次性传入
    client = AppBuilderClient(
        host=HOST,
        api_key=API_KEY,
        ak=AK,
        sk=SK,
    )

    # ================================================================
    # 步骤1：查看知识库列表（了解有哪些可用知识库）
    # ================================================================
    print("\n>>> 步骤1: 查看知识库列表")
    kb_list = client.list_knowledge_bases(project_id=PROJECT_ID)
    for kb in kb_list.get("data", [])[:3]:
        print(f"   知识库: {kb['name']}  (id: {kb['id']})")
    print(f"   共 {kb_list.get('total', 0)} 个知识库")

    # ================================================================
    # 步骤2：查看知识库中已有文档
    # ================================================================
    print("\n>>> 步骤2: 查看知识库中的文档")
    docs = client.list_documents(kb_id=KB_ID, max_keys=5)
    for doc in docs.get("data", []):
        print(f"   文档: {doc['name']}  (id: {doc['id']})  [{doc.get('displayStatus', 'N/A')}]")
    if not docs.get("data"):
        print("   （当前知识库为空，后续可调用 upload_document_to_kb 上传）")

    # ================================================================
    # 步骤3：知识库检索
    # ================================================================
    print(f"\n>>> 步骤3: 知识库检索\n   查询内容: {TEST_QUERY}")
    kb_result = client.query_knowledge_base(
        query=TEST_QUERY,
        kb_ids=[KB_ID],
        project_id=PROJECT_ID,
        top=3,
        expand_chunk=True,
    )

    chunks = kb_result.get("chunks", [])
    if chunks:
        for i, c in enumerate(chunks):
            score = c.get("rank_score", 0)
            content_preview = c["content"][:80].replace("\n", " ")
            print(f"   [{i+1}] score={score:.4f}  {content_preview}...")
        context = "\n\n---\n\n".join([c["content"] for c in chunks])
    else:
        print("   ⚠ 未检索到相关内容")
        context = "（无参考资料）"

    # ================================================================
    # 步骤4：拼接 prompt，调大模型回答
    # ================================================================
    print("\n>>> 步骤4: 拼 prompt + 大模型回答")

    full_prompt = f"""请根据以下参考资料回答问题。
如果参考资料中没有相关信息，请如实说明。

【参考资料】
{context}

【问题】
{TEST_QUERY}"""

    # 新建会话
    conv = client.create_conversation(app_id=APP_ID)
    conversation_id = conv["conversation_id"]
    print(f"   会话已创建: {conversation_id}")

    # 非流式对话
    result = client.run(
        app_id=APP_ID,
        query=full_prompt,
        conversation_id=conversation_id,
    )

    print(f"\n   最终回答:\n   {'-'*50}")
    print(f"   {result.get('answer', '(无)')}")
    print(f"   {'-'*50}")

    # 打印 token 用量（如果有）
    for item in result.get("content", []):
        usage = item.get("usage")
        if usage:
            print(f"   token用量: {usage.get('total_tokens', 'N/A')} "
                  f"(模型: {usage.get('name', 'N/A')})")

    print("\n>>> 全流程完成 ✓")


if __name__ == "__main__":
    main()
