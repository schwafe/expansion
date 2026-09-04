# Step 2: twice

Model `openai-gpt-oss-120b` (thinking on, effort low), 156 vitae, 156 of them with something to do. Written 2026-09-04T10:00:41+00:00.

- abbreviations in the input: 1682
- abbreviations in the output: 434

## Effort

What the run cost. A vita takes a second answer only when the model's reply cannot be read as JSON at all, so several answers per vita is a matter for the prompt, while a long time at one answer per vita is the model or the endpoint.

| | |
| --- | --- |
| vitae the model answered for | 156 |
| answers | 156, 1.00 per vita |
| seconds per vita | 94.4 on average, 58.7 median, 360.9 at worst |
| seconds per answer | 94.4 |
| answers a minute | about 0.6 at 1 vita(e) at a time, of the 15 the rate limit allows |
| server errors waited out | 158 |

## Choices

| outcome | occurrences |
| --- | ---: |
| chosen | 1756 |
| left standing | 1 |

## Errors

The model's answer was rejected and the text left as it was.

| kind | occurrences |
| --- | ---: |
| Invalid choice | 1 |
