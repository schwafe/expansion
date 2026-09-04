# Step 3: thrice

Model `deepseek-v4-flash-0731` (thinking off), 156 vitae, 79 of them with something to do. Written 2026-09-04T11:23:09+00:00.

- abbreviations in the input: 436
- abbreviations in the output: 186

## Effort

What the run cost. A vita takes a second answer only when the model's reply cannot be read as JSON at all, so several answers per vita is a matter for the prompt, while a long time at one answer per vita is the model or the endpoint.

| | |
| --- | --- |
| vitae the model answered for | 79 |
| answers | 79, 1.00 per vita |
| seconds per vita | 72.4 on average, 56.3 median, 298.4 at worst |
| seconds per answer | 72.4 |
| answers a minute | about 12.4 at 15 vita(e) at a time, of the 15 the rate limit allows |
| server errors waited out | 20 |

## Acceptance

| tier | occurrences |
| --- | ---: |
| suggestion | 158 |
| free | 92 |
| rejected | 56 |
| skip | 41 |

## Errors

The model's answer was rejected and the text left as it was.

| kind | occurrences |
| --- | ---: |
| Rejected expansion | 56 |
