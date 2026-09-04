# Step 2: twice

Model `qwen3.8-27b` (thinking off), 156 vitae, 156 of them with something to do. Written 2026-09-02T11:37:30+00:00.

- abbreviations in the input: 1682
- abbreviations in the output: 435

## Effort

What the run cost. A vita takes a second answer only when the model's reply cannot be read as JSON at all, so several answers per vita is a matter for the prompt, while a long time at one answer per vita is the model or the endpoint.

| | |
| --- | --- |
| vitae the model answered for | 156 |
| answers | 157, 1.01 per vita |
| vitae that took more than one | 1, at worst 2 answers |
| seconds per vita | 191.8 on average, 166.9 median, 951.0 at worst |
| seconds per answer | 190.6 |
| answers a minute | about 3.1 at 10 vita(e) at a time, of the 15 the rate limit allows |
| server errors waited out | 7 |

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
