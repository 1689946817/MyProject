# Performance Audit Report

## Overview

- Runs: 11
- Successes: 11
- Failures: 0
- Timeouts: 0

## Scenario Summary

| Scenario | Endpoint | Success Rate | P50 Total (ms) | P95 Total (ms) | P50 First Token (ms) |
| --- | --- | ---: | ---: | ---: | ---: |
| rag_table_non_stream | /api/rag/chat | 100.0% | 103167.179 | 103689.9 | - |
| rag_table_stream | /api/rag/chat/stream | 100.0% | 98448.062 | 105165.93 | 98359.682 |
| text_search_specs | /api/search/text-to-image | 100.0% | 36162.92 | 37538.625 | - |
| image_search_sample | /api/search/image-to-image | 100.0% | 81494.927 | 81494.927 | - |
| image_upload_sample | /api/knowledge-base/upload | 100.0% | 25740.094 | 25740.094 | - |
| document_upload_sample | /api/docs/upload | 100.0% | 17.446 | 17.446 | - |
| document_progress_once | /api/docs/82b50d9f-d77f-484f-a394-e09b6f7f56d2/progress | 100.0% | 0.079 | 0.079 | - |
| document_result_once | /api/docs/82b50d9f-d77f-484f-a394-e09b6f7f56d2/result | 100.0% | 0.107 | 0.107 | - |

## Top Bottlenecks

| Stage | Avg Elapsed (ms) | Avg Share | Runs |
| --- | ---: | ---: | ---: |
| rag_chat_total | 103167.11 | 100.0% | 2 |
| image_to_image_total | 81494.878 | 100.0% | 1 |
| adapter_image_to_image_search | 81493.716 | 100.0% | 1 |
| image_to_image_search_internal | 81493.687 | 100.0% | 1 |
| text_to_image_total | 36162.875 | 100.0% | 2 |
| adapter_text_to_image_search | 36162.268 | 100.0% | 2 |
| knowledge_base_upload_total | 25740.057 | 100.0% | 1 |
| process_image_uploads | 25737.902 | 100.0% | 1 |
| process_image_upload | 25737.862 | 100.0% | 1 |
| document_upload_total | 17.402 | 99.8% | 1 |

## Actionable Bottlenecks

| Stage | Avg Elapsed (ms) | Avg Share | Runs |
| --- | ---: | ---: | ---: |
| image_description_generation | 24782.453 | 96.3% | 1 |
| final_answer_generation | 64654.119 | 64.1% | 4 |
| rerank | 26688.735 | 39.5% | 7 |
| chat_completion_async | 29348.943 | 38.7% | 13 |
| rag_retrieval | 34980.38 | 34.7% | 4 |
| multi_query_hybrid_search | 12976.638 | 20.4% | 7 |
| image_query_description_generation | 15953.639 | 19.6% | 1 |
| query_expand | 11817.426 | 18.8% | 7 |
| image_vector_upsert | 878.655 | 3.4% | 1 |
| document_text_retrieval | 724.486 | 0.7% | 4 |

## Scenario Details

### rag_table_non_stream

- Endpoint: `/api/rag/chat`
- Runs: 2
- Success Rate: 100.0%
- Total Timing (ms): avg=103167.179, p50=103167.179, p95=103689.9, max=103747.98
- Top Stages:
  - rag_chat_total: avg_elapsed=103167.11ms, avg_share=100.0%, runs=2
  - adapter_rag_chat: avg_elapsed=102379.994ms, avg_share=99.2%, runs=2
  - final_answer_generation: avg_elapsed=63539.682ms, avg_share=61.6%, runs=2
  - rag_retrieval: avg_elapsed=37914.609ms, avg_share=36.7%, runs=2
  - async_search_with_dict_output: avg_elapsed=37914.582ms, avg_share=36.7%, runs=2

### rag_table_stream

- Endpoint: `/api/rag/chat/stream`
- Runs: 2
- Success Rate: 100.0%
- Total Timing (ms): avg=98448.062, p50=98448.062, p95=105165.93, max=105912.36
- First Token (ms): avg=98359.682, p50=98359.682, p95=105080.631, max=105827.403
- Top Stages:
  - final_answer_generation: avg_elapsed=65768.556ms, avg_share=66.7%, runs=2
  - chat_completion_async: avg_elapsed=37927.452ms, avg_share=38.5%, runs=4
  - rag_retrieval: avg_elapsed=32046.152ms, avg_share=32.7%, runs=2
  - async_search_with_dict_output: avg_elapsed=32046.126ms, avg_share=32.7%, runs=2
  - rerank: avg_elapsed=21216.55ms, avg_share=21.7%, runs=2

### text_search_specs

- Endpoint: `/api/search/text-to-image`
- Runs: 2
- Success Rate: 100.0%
- Total Timing (ms): avg=36162.92, p50=36162.92, p95=37538.625, max=37691.481
- Top Stages:
  - text_to_image_total: avg_elapsed=36162.875ms, avg_share=100.0%, runs=2
  - adapter_text_to_image_search: avg_elapsed=36162.268ms, avg_share=100.0%, runs=2
  - text_to_image_search_internal: avg_elapsed=36162.238ms, avg_share=100.0%, runs=2
  - rerank: avg_elapsed=22604.42ms, avg_share=62.6%, runs=2
  - multi_query_hybrid_search: avg_elapsed=13539.376ms, avg_share=37.4%, runs=2

### image_search_sample

- Endpoint: `/api/search/image-to-image`
- Runs: 1
- Success Rate: 100.0%
- Total Timing (ms): avg=81494.927, p50=81494.927, p95=81494.927, max=81494.927
- Top Stages:
  - image_to_image_total: avg_elapsed=81494.878ms, avg_share=100.0%, runs=1
  - adapter_image_to_image_search: avg_elapsed=81493.716ms, avg_share=100.0%, runs=1
  - image_to_image_search_internal: avg_elapsed=81493.687ms, avg_share=100.0%, runs=1
  - text_to_image_search_internal: avg_elapsed=65538.987ms, avg_share=80.4%, runs=1
  - rerank: avg_elapsed=46259.373ms, avg_share=56.8%, runs=1

### image_upload_sample

- Endpoint: `/api/knowledge-base/upload`
- Runs: 1
- Success Rate: 100.0%
- Total Timing (ms): avg=25740.094, p50=25740.094, p95=25740.094, max=25740.094
- Top Stages:
  - knowledge_base_upload_total: avg_elapsed=25740.057ms, avg_share=100.0%, runs=1
  - process_image_uploads: avg_elapsed=25737.902ms, avg_share=100.0%, runs=1
  - process_image_upload: avg_elapsed=25737.862ms, avg_share=100.0%, runs=1
  - image_description_generation: avg_elapsed=24782.453ms, avg_share=96.3%, runs=1
  - chat_completion_async: avg_elapsed=24777.632ms, avg_share=96.3%, runs=1

### document_upload_sample

- Endpoint: `/api/docs/upload`
- Runs: 1
- Success Rate: 100.0%
- Total Timing (ms): avg=17.446, p50=17.446, p95=17.446, max=17.446
- Top Stages:
  - document_upload_total: avg_elapsed=17.402ms, avg_share=99.8%, runs=1

### document_progress_once

- Endpoint: `/api/docs/82b50d9f-d77f-484f-a394-e09b6f7f56d2/progress`
- Runs: 1
- Success Rate: 100.0%
- Total Timing (ms): avg=0.079, p50=0.079, p95=0.079, max=0.079

### document_result_once

- Endpoint: `/api/docs/82b50d9f-d77f-484f-a394-e09b6f7f56d2/result`
- Runs: 1
- Success Rate: 100.0%
- Total Timing (ms): avg=0.107, p50=0.107, p95=0.107, max=0.107
