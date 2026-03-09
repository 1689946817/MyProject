"""
重排序模块

该模块负责对检索结果进行重排序，目前实现了基于得分的简单重排序。

重排序是检索系统中的重要环节，可以进一步提高检索结果的准确性和相关性。
"""
from typing import Any, Dict, List


def simple_rerank(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """简单重排序
    
    基于得分从小到大排序（Chroma 默认距离越小越相似），
    返回重排序后的结果列表。
    
    Args:
        results: 原始检索结果列表，每个元素包含 score 字段
    
    Returns:
        List[Dict[str, Any]]: 重排序后的结果列表，按相似度从高到低排序
    """
    # 按得分从小到大排序，因为 Chroma 返回的是距离值，值越小相似度越高
    return sorted(results, key=lambda x: x.get("score", 0.0))

