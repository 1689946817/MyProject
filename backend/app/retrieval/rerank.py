from typing import Any, Dict, List


def simple_rerank(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    基于得分从小到大排序（Chroma 默认距离越小越相似），
    返回重排序后的结果列表。
    """
    return sorted(results, key=lambda x: x.get("score", 0.0))

