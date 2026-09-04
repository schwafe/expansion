# Step 2: twice

Model `glm-4.7` (thinking off), 156 vitae, 156 of them with something to do. Written 2026-09-04T10:15:37+00:00.

- abbreviations in the input: 1682
- abbreviations in the output: 494

## Effort

What the run cost. A vita takes a second answer only when the model's reply cannot be read as JSON at all, so several answers per vita is a matter for the prompt, while a long time at one answer per vita is the model or the endpoint.

| | |
| --- | --- |
| vitae the model answered for | 156 |
| answers | 156, 1.00 per vita |
| seconds per vita | 123.6 on average, 56.6 median, 1694.5 at worst |
| seconds per answer | 123.6 |
| answers a minute | about 0.5 at 1 vita(e) at a time, of the 15 the rate limit allows |
| server errors waited out | 95 |

## Choices

| outcome | occurrences |
| --- | ---: |
| chosen | 1657 |
| left standing | 100 |

## Errors

The model's answer was rejected and the text left as it was.

| kind | occurrences |
| --- | ---: |
| Invalid choice | 100 |
