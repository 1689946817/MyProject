"""
辅助脚本：将嵌入的 CONTENT 字符串写入 run_unidoc_gen_batch.py。

用途：
    run_unidoc_gen_batch.py 的内容以 CONTENT 变量的形式嵌入本文件，
    运行本脚本即可将 CONTENT 写出为目标文件。
    这是一种简单的"单文件分发"方式，避免多文件依赖。

使用方式（从项目根目录）：
    python evaluation/_write_batch.py

输出：
    evaluation/run_unidoc_gen_batch.py
"""

import pathlib

code = open(__file__, encoding='utf-8').read()
# 读取自身源码（保留用途，可能用于调试或校验）

# This file writes run_unidoc_gen_batch.py
# ---- 将 CONTENT 写入目标文件 ----

target = pathlib.Path(r'E:/BiShe/Code2/MyProject/evaluation/run_unidoc_gen_batch.py')
target.write_text(CONTENT, encoding='utf-8')
print('written', target.stat().st_size)
