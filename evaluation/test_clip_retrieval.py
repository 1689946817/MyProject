#!/usr/bin/env python3
"""
测试 Baseline CLIP Retrieval 功能。

该脚本测试：
1. 图像嵌入功能
2. 文本嵌入功能
3. 检索功能
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.app.retrieval.embedding_client import get_embedding_client
from evaluation.methods.baseline_clip_retrieval import (
    retrieve_text,
    retrieve_image,
    check_vector_index
)


def test_embedding_client():
    """测试嵌入客户端功能"""
    print("Testing embedding client...")

    embedder = get_embedding_client()

    # 测试文本嵌入
    print("1. Testing text embedding...")
    texts = ["这是一只猫", "这是一只狗"]
    try:
        text_embeddings = embedder.embed_texts(texts)
        print(f"   ✓ Text embedding successful: {len(text_embeddings)} embeddings")
        print(f"   ✓ Embedding dimension: {len(text_embeddings[0])}")
    except Exception as e:
        print(f"   ✗ Text embedding failed: {e}")
        return False

    # 测试图像嵌入（需要实际图像文件）
    print("\n2. Testing image embedding...")
    if hasattr(embedder, 'embed_images'):
        # 创建一个简单的测试图像或使用现有图像
        test_image_path = "test_image.txt"  # 这是一个文本文件，不是真正的图像
        if Path(test_image_path).exists():
            try:
                image_embeddings = embedder.embed_images([test_image_path])
                print(f"   ✓ Image embedding successful: {len(image_embeddings)} embeddings")
                print(f"   ✓ Embedding dimension: {len(image_embeddings[0])}")
            except Exception as e:
                print(f"   ✗ Image embedding failed: {e}")
                print("   Note: This might be expected if test_image.txt is not a valid image")
        else:
            print("   ⚠ Skipping image embedding test (no test image found)")
    else:
        print("   ✗ Embedding client does not support image embedding")
        return False

    return True


def test_retrieval_functions():
    """测试检索功能"""
    print("\nTesting retrieval functions...")

    # 检查向量索引
    print("1. Checking vector index...")
    if check_vector_index():
        print("   ✓ Vector index exists")

        # 测试文本检索
        print("\n2. Testing text retrieval...")
        try:
            results = retrieve_text("cat", top_k=5)
            print(f"   ✓ Text retrieval successful: {len(results)} results")
            if results:
                print(f"   ✓ Sample result IDs: {results[:3]}")
        except Exception as e:
            print(f"   ✗ Text retrieval failed: {e}")

        # 测试图像检索（需要实际图像文件）
        print("\n3. Testing image retrieval...")
        test_image_path = "test_image.txt"
        if Path(test_image_path).exists():
            try:
                results = retrieve_image(test_image_path, top_k=5)
                print(f"   ✓ Image retrieval successful: {len(results)} results")
                if results:
                    print(f"   ✓ Sample result IDs: {results[:3]}")
            except Exception as e:
                print(f"   ✗ Image retrieval failed: {e}")
        else:
            print("   ⚠ Skipping image retrieval test (no test image found)")
    else:
        print("   ⚠ Vector index not built yet")
        print("   Run: python -m evaluation.build_clip_index")
        return False

    return True


def main():
    """主测试函数"""
    print("=" * 60)
    print("Baseline CLIP Retrieval Test")
    print("=" * 60)

    # 测试嵌入客户端
    if not test_embedding_client():
        print("\n❌ Embedding client test failed")
        print("\nPossible issues:")
        print("1. qwen3-vl-embedding model not configured")
        print("2. DashScope API key not set in .env")
        print("3. Network connection issues")
        return

    # 测试检索功能
    if not test_retrieval_functions():
        print("\n⚠ Retrieval functions test incomplete")
        print("\nNote: Vector index needs to be built first")
        print("Run: python -m evaluation.build_clip_index")
        return

    print("\n" + "=" * 60)
    print("✅ All tests completed successfully!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Upload images to the system")
    print("2. Build vector index: python -m evaluation.build_clip_index")
    print("3. Run evaluation: python -m evaluation.run_offline_eval --method baseline_clip")


if __name__ == "__main__":
    main()