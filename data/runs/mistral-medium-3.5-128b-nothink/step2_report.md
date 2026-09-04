# Step 2: twice

Model `mistral-medium-3.5-128b` (thinking off), 156 vitae, 156 of them with something to do. Written 2026-09-04T11:00:21+00:00.

- abbreviations in the input: 1682
- abbreviations in the output: 447

## Effort

What the run cost. A vita takes a second answer only when the model's reply cannot be read as JSON at all, so several answers per vita is a matter for the prompt, while a long time at one answer per vita is the model or the endpoint.

| | |
| --- | --- |
| vitae the model answered for | 156 |
| answers | 156, 1.00 per vita |
| seconds per vita | 69.3 on average, 57.5 median, 292.0 at worst |
| seconds per answer | 69.3 |
| answers a minute | about 13.0 at 15 vita(e) at a time, of the 15 the rate limit allows |
| server errors waited out | 83 |

## Choices

| outcome | occurrences |
| --- | ---: |
| chosen | 1719 |
| left standing | 38 |

## Errors

The model's answer was rejected and the text left as it was.

| kind | occurrences |
| --- | ---: |
| Invalid choice | 38 |
