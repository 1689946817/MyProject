import asyncio
import sys
import traceback
sys.path.insert(0, 'backend')

async def test_rag():
    try:
        from app.application.rag_engine import rag_chat
        print("正在测试 RAG 引擎...")
        answer, retrieved = await rag_chat(query='这是什么图片？', top_k=3)
        print(f"测试成功!")
        print(f"答案: {answer[:100]}...")
        print(f"检索到 {len(retrieved)} 个结果")
    except Exception as e:
        print(f"RAG 引擎测试失败: {type(e).__name__}: {e}")
        traceback.print_exc()

async def test_llm():
    try:
        from app.application.llm_client import OpenAIStyleLLMClient
        print("\n正在测试 LLM 客户端...")
        client = OpenAIStyleLLMClient()
        messages = [{'role': 'user', 'content': 'Hello'}]
        response = await client.chat(messages)
        print(f"LLM 测试成功: {response[:50]}...")
    except Exception as e:
        print(f"LLM 测试失败: {type(e).__name__}: {e}")
        traceback.print_exc()

async def test_retrieval():
    try:
        from app.application.dispatcher import text_to_image_search
        print("\n正在测试文本检索...")
        results = await text_to_image_search(query='test', top_k=3)
        print(f"文本检索测试成功，返回 {len(results)} 个结果")
    except Exception as e:
        print(f"文本检索测试失败: {type(e).__name__}: {e}")
        traceback.print_exc()

async def main():
    print("开始测试后端功能...")
    await test_retrieval()
    await test_llm()
    await test_rag()

if __name__ == "__main__":
    asyncio.run(main())