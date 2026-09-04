# Step 3: thrice

Model `deepseek-v4-flash-0731` (thinking on, effort high), 156 vitae, 79 of them with something to do. Written 2026-09-04T14:04:25+00:00.

- abbreviations in the input: 436
- abbreviations in the output: 158

## Effort

What the run cost. A vita takes a second answer only when the model's reply cannot be read as JSON at all, so several answers per vita is a matter for the prompt, while a long time at one answer per vita is the model or the endpoint.

| | |
| --- | --- |
| vitae the model answered for | 79 |
| answers | 79, 1.00 per vita |
| seconds per vita | 303.3 on average, 122.0 median, 2009.4 at worst |
| seconds per answer | 303.3 |
| answers a minute | about 2.4 at 12 vita(e) at a time, of the 15 the rate limit allows |
| server errors waited out | 7 |

## Acceptance

| tier | occurrences |
| --- | ---: |
| free | 140 |
| suggestion | 138 |
| skip | 58 |
| rejected | 11 |

## Errors

The model's answer was rejected and the text left as it was.

| kind | occurrences |
| --- | ---: |
| Rejected expansion | 11 |
