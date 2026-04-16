# Performance Audit Report

## Overview

- Runs: 11
- Successes: 8
- Failures: 3
- Timeouts: 0

## Scenario Summary

| Scenario | Endpoint | Success Rate | P50 Total (ms) | P95 Total (ms) | P50 First Token (ms) |
| --- | --- | ---: | ---: | ---: | ---: |
| rag_table_non_stream | /api/rag/chat | 50.0% | 182480.503 | 182480.503 | - |
| rag_table_stream | /api/rag/chat/stream | 0.0% | - | - | - |
| text_search_specs | /api/search/text-to-image | 100.0% | 68405.826 | 69193.871 | - |
| image_search_sample | /api/search/image-to-image | 100.0% | 109897.037 | 109897.037 | - |
| image_upload_sample | /api/knowledge-base/upload | 100.0% | 33410.084 | 33410.084 | - |
| document_upload_sample | /api/docs/upload | 100.0% | 11.612 | 11.612 | - |
| document_progress_once | /api/docs/cf2627c2-8106-41a5-bcdd-6394dde91b56/progress | 100.0% | 0.322 | 0.322 | - |
| document_result_once | /api/docs/cf2627c2-8106-41a5-bcdd-6394dde91b56/result | 100.0% | 0.098 | 0.098 | - |

## Top Bottlenecks

| Stage | Avg Elapsed (ms) | Avg Share | Runs |
| --- | ---: | ---: | ---: |
| rag_chat_total | 182480.378 | 100.0% | 1 |
| image_to_image_total | 109896.998 | 100.0% | 1 |
| adapter_image_to_image_search | 109896.849 | 100.0% | 1 |
| image_to_image_search_internal | 109896.827 | 100.0% | 1 |
| text_to_image_total | 68405.782 | 100.0% | 2 |
| adapter_text_to_image_search | 68405.688 | 100.0% | 2 |
| knowledge_base_upload_total | 33409.904 | 100.0% | 1 |
| process_image_uploads | 33409.3 | 100.0% | 1 |
| process_image_upload | 33409.204 | 100.0% | 1 |
| adapter_rag_chat | 182417.101 | 100.0% | 1 |

## Actionable Bottlenecks

| Stage | Avg Elapsed (ms) | Avg Share | Runs |
| --- | ---: | ---: | ---: |
| image_description_generation | 32299.398 | 96.7% | 1 |
| multi_query_hybrid_search | 46580.778 | 51.2% | 4 |
| query_expand | 45807.472 | 50.3% | 4 |
| chat_completion_async | 44665.304 | 48.2% | 8 |
| rag_retrieval | 68391.686 | 37.5% | 1 |
| final_answer_generation | 57774.834 | 31.7% | 1 |
| intent_classification | 55965.006 | 30.7% | 1 |
| rerank | 25164.953 | 26.7% | 4 |
| image_query_description_generation | 28066.663 | 25.5% | 1 |
| image_vector_upsert | 1001.162 | 3.0% | 1 |

## Scenario Details

### rag_table_non_stream

- Endpoint: `/api/rag/chat`
- Runs: 2
- Success Rate: 50.0%
- Total Timing (ms): avg=182480.503, p50=182480.503, p95=182480.503, max=182480.503
- Top Stages:
  - rag_chat_total: avg_elapsed=182480.378ms, avg_share=100.0%, runs=1
  - adapter_rag_chat: avg_elapsed=182417.101ms, avg_share=100.0%, runs=1
  - rag_retrieval: avg_elapsed=68391.686ms, avg_share=37.5%, runs=1
  - async_search_with_dict_output: avg_elapsed=68391.654ms, avg_share=37.5%, runs=1
  - final_answer_generation: avg_elapsed=57774.834ms, avg_share=31.7%, runs=1

### rag_table_stream

- Endpoint: `/api/rag/chat/stream`
- Runs: 2
- Success Rate: 0.0%

### text_search_specs

- Endpoint: `/api/search/text-to-image`
- Runs: 2
- Success Rate: 100.0%
- Total Timing (ms): avg=68405.826, p50=68405.826, p95=69193.871, max=69281.431
- Top Stages:
  - text_to_image_total: avg_elapsed=68405.782ms, avg_share=100.0%, runs=2
  - adapter_text_to_image_search: avg_elapsed=68405.688ms, avg_share=100.0%, runs=2
  - text_to_image_search_internal: avg_elapsed=68405.656ms, avg_share=100.0%, runs=2
  - multi_query_hybrid_search: avg_elapsed=47521.39ms, avg_share=69.5%, runs=2
  - query_expand: avg_elapsed=46640.576ms, avg_share=68.2%, runs=2

### image_search_sample

- Endpoint: `/api/search/image-to-image`
- Runs: 1
- Success Rate: 100.0%
- Total Timing (ms): avg=109897.037, p50=109897.037, p95=109897.037, max=109897.037
- Top Stages:
  - image_to_image_total: avg_elapsed=109896.998ms, avg_share=100.0%, runs=1
  - adapter_image_to_image_search: avg_elapsed=109896.849ms, avg_share=100.0%, runs=1
  - image_to_image_search_internal: avg_elapsed=109896.827ms, avg_share=100.0%, runs=1
  - text_to_image_search_internal: avg_elapsed=81829.008ms, avg_share=74.5%, runs=1
  - multi_query_hybrid_search: avg_elapsed=44191.897ms, avg_share=40.2%, runs=1

### image_upload_sample

- Endpoint: `/api/knowledge-base/upload`
- Runs: 1
- Success Rate: 100.0%
- Total Timing (ms): avg=33410.084, p50=33410.084, p95=33410.084, max=33410.084
- Top Stages:
  - knowledge_base_upload_total: avg_elapsed=33409.904ms, avg_share=100.0%, runs=1
  - process_image_uploads: avg_elapsed=33409.3ms, avg_share=100.0%, runs=1
  - process_image_upload: avg_elapsed=33409.204ms, avg_share=100.0%, runs=1
  - image_description_generation: avg_elapsed=32299.398ms, avg_share=96.7%, runs=1
  - chat_completion_async: avg_elapsed=32295.142ms, avg_share=96.7%, runs=1

### document_upload_sample

- Endpoint: `/api/docs/upload`
- Runs: 1
- Success Rate: 100.0%
- Total Timing (ms): avg=11.612, p50=11.612, p95=11.612, max=11.612
- Top Stages:
  - document_upload_total: avg_elapsed=11.538ms, avg_share=99.4%, runs=1

### document_progress_once

- Endpoint: `/api/docs/cf2627c2-8106-41a5-bcdd-6394dde91b56/progress`
- Runs: 1
- Success Rate: 100.0%
- Total Timing (ms): avg=0.322, p50=0.322, p95=0.322, max=0.322

### document_result_once

- Endpoint: `/api/docs/cf2627c2-8106-41a5-bcdd-6394dde91b56/result`
- Runs: 1
- Success Rate: 100.0%
- Total Timing (ms): avg=0.098, p50=0.098, p95=0.098, max=0.098
