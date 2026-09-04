# Step 2: twice

Model `apertus-70b-instruct-2509` (thinking off), 156 vitae, 156 of them with something to do. Written 2026-09-04T10:38:06+00:00.

- abbreviations in the input: 1682
- abbreviations in the output: 447

## Effort

What the run cost. A vita takes a second answer only when the model's reply cannot be read as JSON at all, so several answers per vita is a matter for the prompt, while a long time at one answer per vita is the model or the endpoint.

| | |
| --- | --- |
| vitae the model answered for | 156 |
| answers | 156, 1.00 per vita |
| seconds per vita | 54.3 on average, 28.4 median, 296.9 at worst |
| seconds per answer | 54.3 |
| answers a minute | about 11.0 at 10 vita(e) at a time, of the 15 the rate limit allows |
| server errors waited out | 70 |

## Choices

| outcome | occurrences |
| --- | ---: |
| chosen | 1735 |
| left standing | 22 |

## Errors

The model's answer was rejected and the text left as it was.

| kind | occurrences |
| --- | ---: |
| Invalid choice | 21 |
| Missing choice | 1 |
