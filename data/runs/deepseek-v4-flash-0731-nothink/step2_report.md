# Step 2: twice

Model `deepseek-v4-flash-0731` (thinking off), 156 vitae, 156 of them with something to do. Written 2026-09-02T12:30:27+00:00.

- abbreviations in the input: 1682
- abbreviations in the output: 436

## Effort

What the run cost. A vita takes a second answer only when the model's reply cannot be read as JSON at all, so several answers per vita is a matter for the prompt, while a long time at one answer per vita is the model or the endpoint.

| | |
| --- | --- |
| vitae the model answered for | 138 |
| answers | 138, 1.00 per vita |
| seconds per vita | 216.2 on average, 6.8 median, 1831.6 at worst |
| seconds per answer | 216.2 |
| answers a minute | about 4.2 at 15 vita(e) at a time, of the 15 the rate limit allows |
| server errors waited out | 60 |

## Choices

| outcome | occurrences |
| --- | ---: |
| chosen | 1754 |
| left standing | 3 |

## Errors

The model's answer was rejected and the text left as it was.

| kind | occurrences |
| --- | ---: |
| Invalid choice | 3 |
