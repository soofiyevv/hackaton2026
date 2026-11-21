# UniResolve AI - evaluation run
Run at 2026-11-21 11:23 on 20 hand-written student problems ({'live_llm': 11, 'mixed': 9}). Expected departments were labelled by the team before the run.

| metric | value |
|---|---|
| Routing accuracy (19 in-scope cases) | 95% |
| Staff-decision flag accuracy | 95% |
| Accepted by auditor on first attempt | 16/20 |
| Self-corrected after auditor rejection | 4/20 |
| Escalated to human after failed revisions | 0/20 |
| Queued for staff decision (policy) | 7/20 |
| Total auditor rejections | 4 |
| Median / mean time per ticket | 3.2 s / 5.9 s |
| Live LLM calls / simulated | 99 / 9 |
| Failed tickets | 0 |

Routing misses:
- "The washing machines in my dormitory have been broken for a week." -> Facilities Management (expected Dormitory Office)

Small hand-made test set; these numbers describe this run, not real-world performance.