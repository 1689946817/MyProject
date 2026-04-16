# Performance Audit Report

## Overview

- Runs: 11
- Successes: 11
- Failures: 0
- Timeouts: 0

## Scenario Summary

| Scenario | Endpoint | Success Rate | P50 Total (ms) | P95 Total (ms) | P50 First Token (ms) |
| --- | --- | ---: | ---: | ---: | ---: |
| rag_table_non_stream | /api/rag/chat | 100.0% | 200257.226 | 215833.197 | - |
| rag_table_stream | /api/rag/chat/stream | 100.0% | 182668.803 | 192331.645 | 182568.957 |
| text_search_specs | /api/search/text-to-image | 100.0% | 52437.978 | 61816.99 | - |
| image_search_sample | /api/search/image-to-image | 100.0% | 94466.66 | 94466.66 | - |
| image_upload_sample | /api/knowledge-base/upload | 100.0% | 28576.964 | 28576.964 | - |
| document_upload_sample | /api/docs/upload | 100.0% | 43.776 | 43.776 | - |
| document_progress_once | /api/docs/feedbeeb-eff3-4831-a08d-abdf1b1fb9d3/progress | 100.0% | 0.17 | 0.17 | - |
| document_result_once | /api/docs/feedbeeb-eff3-4831-a08d-abdf1b1fb9d3/result | 100.0% | 0.114 | 0.114 | - |

## Top Bottlenecks

| Stage | Avg Elapsed (ms) | Avg Share | Runs |
| --- | ---: | ---: | ---: |
| rag_chat_total | 200257.177 | 100.0% | 2 |
| image_to_image_total | 94466.622 | 100.0% | 1 |
| adapter_image_to_image_search | 94465.042 | 100.0% | 1 |
| image_to_image_search_internal | 94465.02 | 100.0% | 1 |
| text_to_image_total | 52437.93 | 100.0% | 2 |
| adapter_text_to_image_search | 52436.166 | 100.0% | 2 |
| knowledge_base_upload_total | 28576.74 | 100.0% | 1 |
| process_image_uploads | 28573.772 | 100.0% | 1 |
| process_image_upload | 28573.672 | 100.0% | 1 |
| adapter_rag_chat | 199449.382 | 99.6% | 2 |

## Scenario Details

### rag_table_non_stream

- Endpoint: `/api/rag/chat`
- Runs: 2
- Success Rate: 100.0%
- Total Timing (ms): avg=200257.226, p50=200257.226, p95=215833.197, max=217563.861
- Top Stages:
  - rag_chat_total: avg_elapsed=200257.177ms, avg_share=100.0%, runs=2
  - adapter_rag_chat: avg_elapsed=199449.382ms, avg_share=99.6%, runs=2
  - final_answer_generation: avg_elapsed=76273.029ms, avg_share=38.3%, runs=2
  - intent_classification: avg_elapsed=64160.769ms, avg_share=32.0%, runs=2
  - rag_retrieval: avg_elapsed=58302.068ms, avg_share=28.9%, runs=2

### rag_table_stream

- Endpoint: `/api/rag/chat/stream`
- Runs: 2
- Success Rate: 100.0%
- Total Timing (ms): avg=182668.803, p50=182668.803, p95=192331.645, max=193405.294
- First Token (ms): avg=182568.957, p50=182568.957, p95=192239.08, max=193313.538
- Top Stages:
  - rag_retrieval: avg_elapsed=65627.853ms, avg_share=36.1%, runs=2
  - async_search_with_dict_output: avg_elapsed=65627.799ms, avg_share=36.1%, runs=2
  - intent_classification: avg_elapsed=63351.588ms, avg_share=34.7%, runs=2
  - chat_completion_async: avg_elapsed=53345.062ms, avg_share=29.2%, runs=6
  - final_answer_generation: avg_elapsed=52997.813ms, avg_share=28.8%, runs=2

### text_search_specs

- Endpoint: `/api/search/text-to-image`
- Runs: 2
- Success Rate: 100.0%
- Total Timing (ms): avg=52437.978, p50=52437.978, p95=61816.99, max=62859.102
- Top Stages:
  - text_to_image_total: avg_elapsed=52437.93ms, avg_share=100.0%, runs=2
  - adapter_text_to_image_search: avg_elapsed=52436.166ms, avg_share=100.0%, runs=2
  - text_to_image_search_internal: avg_elapsed=52436.13ms, avg_share=100.0%, runs=2
  - multi_query_hybrid_search: avg_elapsed=31466.004ms, avg_share=58.6%, runs=2
  - query_expand: avg_elapsed=30705.782ms, avg_share=57.1%, runs=2

### image_search_sample

- Endpoint: `/api/search/image-to-image`
- Runs: 1
- Success Rate: 100.0%
- Total Timing (ms): avg=94466.66, p50=94466.66, p95=94466.66, max=94466.66
- Top Stages:
  - image_to_image_total: avg_elapsed=94466.622ms, avg_share=100.0%, runs=1
  - adapter_image_to_image_search: avg_elapsed=94465.042ms, avg_share=100.0%, runs=1
  - image_to_image_search_internal: avg_elapsed=94465.02ms, avg_share=100.0%, runs=1
  - text_to_image_search_internal: avg_elapsed=74670.793ms, avg_share=79.0%, runs=1
  - multi_query_hybrid_search: avg_elapsed=39225.822ms, avg_share=41.5%, runs=1

### image_upload_sample

- Endpoint: `/api/knowledge-base/upload`
- Runs: 1
- Success Rate: 100.0%
- Total Timing (ms): avg=28576.964, p50=28576.964, p95=28576.964, max=28576.964
- Top Stages:
  - knowledge_base_upload_total: avg_elapsed=28576.74ms, avg_share=100.0%, runs=1
  - process_image_uploads: avg_elapsed=28573.772ms, avg_share=100.0%, runs=1
  - process_image_upload: avg_elapsed=28573.672ms, avg_share=100.0%, runs=1
  - image_description_generation: avg_elapsed=27557.59ms, avg_share=96.4%, runs=1
  - chat_completion_async: avg_elapsed=27550.729ms, avg_share=96.4%, runs=1

### document_upload_sample

- Endpoint: `/api/docs/upload`
- Runs: 1
- Success Rate: 100.0%
- Total Timing (ms): avg=43.776, p50=43.776, p95=43.776, max=43.776
- Top Stages:
  - document_upload_total: avg_elapsed=43.551ms, avg_share=99.5%, runs=1

### document_progress_once

- Endpoint: `/api/docs/feedbeeb-eff3-4831-a08d-abdf1b1fb9d3/progress`
- Runs: 1
- Success Rate: 100.0%
- Total Timing (ms): avg=0.17, p50=0.17, p95=0.17, max=0.17

### document_result_once

- Endpoint: `/api/docs/feedbeeb-eff3-4831-a08d-abdf1b1fb9d3/result`
- Runs: 1
- Success Rate: 100.0%
- Total Timing (ms): avg=0.114, p50=0.114, p95=0.114, max=0.114
