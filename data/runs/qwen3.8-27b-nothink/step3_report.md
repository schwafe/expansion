# Step 3: thrice

Model `qwen3.8-27b` (thinking off), 156 vitae, 78 of them with something to do. Written 2026-09-04T12:14:55+00:00.

- abbreviations in the input: 434
- abbreviations in the output: 232

## Effort

What the run cost. A vita takes a second answer only when the model's reply cannot be read as JSON at all, so several answers per vita is a matter for the prompt, while a long time at one answer per vita is the model or the endpoint.

| | |
| --- | --- |
| vitae the model answered for | 78 |
| answers | 78, 1.00 per vita |
| seconds per vita | 112.3 on average, 40.8 median, 604.0 at worst |
| seconds per answer | 112.3 |
| answers a minute | about 6.4 at 12 vita(e) at a time, of the 15 the rate limit allows |

## Acceptance

| tier | occurrences |
| --- | ---: |
| suggestion | 162 |
| rejected | 85 |
| skip | 58 |
| free | 40 |

## Errors

The model's answer was rejected and the text left as it was.

| kind | occurrences |
| --- | ---: |
| Rejected expansion | 85 |
