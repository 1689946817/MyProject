import pathlib

code = open(__file__, encoding='utf-8').read()
# This file writes run_unidoc_gen_batch.py

target = pathlib.Path(r'E:/BiShe/Code2/MyProject/evaluation/run_unidoc_gen_batch.py')
target.write_text(CONTENT, encoding='utf-8')
print('written', target.stat().st_size)
