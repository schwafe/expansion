# The runs against each other

Gold: `data/to_compare_with/fable_expanded.csv`. Word accuracy asks whether the right word was chosen, form accuracy whether the text is right as it stands; both are those of the last stage the run reached.

| run | step 2 | step 3 | step 4 | scored at | word accuracy | form accuracy |
| --- | --- | --- | --- | --- | ---: | ---: |
| `gemma-4-31b-it-nothink` | `gemma-4-31b-it (off)` | `gemma-4-31b-it (off)` | `gemma-4-31b-it (off)` | step 4 (normalized) |  92.9% |  64.8% |
| `deepseek-v4-flash-0731-high` | `deepseek-v4-flash-0731 (off)` | `deepseek-v4-flash-0731 (effort high)` | — | step 3 (mined) |  94.2% |  48.0% |
| `deepseek-v4-flash-0731-nothink` | `deepseek-v4-flash-0731 (off)` | `deepseek-v4-flash-0731 (off)` | — | step 3 (mined) |  93.6% |  47.2% |
| `mistral-medium-3.5-128b-nothink` | `gemma-4-31b-it (off)` | `mistral-medium-3.5-128b (off)` | — | step 3 (mined) |  93.5% |  46.6% |
| `qwen3.8-27b-nothink` | `gemma-4-31b-it (off)` | `qwen3.8-27b (off)` | — | step 3 (mined) |  92.6% |  46.2% |
| `glm-4.7-nothink` | `glm-4.7 (off)` | — | — | step 2 (candidates) |  86.9% |  43.8% |
| `openai-gpt-oss-120b-low` | `openai-gpt-oss-120b (effort low)` | — | — | step 2 (candidates) |  82.7% |  41.8% |
| `apertus-70b-instruct-2509-nothink` | `apertus-70b-instruct-2509 (off)` | — | — | step 2 (candidates) |  80.7% |  41.6% |

## Step 2 on its own

Every chain that has a step 2, scored on the text it produced -- so the rows are comparable whatever the runs did afterwards. Sorted by word accuracy, which asks whether the right word was chosen; `gained` is the rise over step 1 (rule) as this step was handed it -- which after a `--from` is another run's file, and is named in the column for that step.

| produced by | step 2 | word accuracy | form accuracy | gained | scoreable |
| --- | --- | ---: | ---: | ---: | ---: |
| `deepseek-v4-flash-0731-high` | `deepseek-v4-flash-0731 (effort high)` |  90.9% |  44.1% | +32.0pp | 4967 |
| `gemma-4-31b-it-nothink` | `gemma-4-31b-it (off)` |  89.1% |  43.8% | +30.3pp | 4967 |
| `deepseek-v4-flash-0731-nothink` | `deepseek-v4-flash-0731 (off)` |  89.0% |  43.8% | +30.2pp | 4967 |
| `qwen3.8-27b-nothink` | `qwen3.8-27b (off)` |  87.4% |  43.3% | +28.6pp | 4967 |
| `mistral-medium-3.5-128b-nothink` | `mistral-medium-3.5-128b (off)` |  87.0% |  43.3% | +28.2pp | 4967 |
| `glm-4.7-nothink` | `glm-4.7 (off)` |  86.9% |  43.8% | +28.1pp | 4957 |
| `openai-gpt-oss-120b-low` | `openai-gpt-oss-120b (effort low)` |  82.7% |  41.8% | +23.9pp | 4967 |
| `apertus-70b-instruct-2509-nothink` | `apertus-70b-instruct-2509 (off)` |  80.7% |  41.6% | +21.8pp | 4967 |

## Step 3 on its own

Every chain that has a step 3, scored on the text it produced -- so the rows are comparable whatever the runs did afterwards. Sorted by word accuracy, which asks whether the right word was chosen; `gained` is the rise over step 2 (candidates) as this step was handed it -- which after a `--from` is another run's file, and is named in the column for that step.

| produced by | step 2 | step 3 | word accuracy | form accuracy | gained | scoreable |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `deepseek-v4-flash-0731-high` | `deepseek-v4-flash-0731 (off)` | `deepseek-v4-flash-0731 (effort high)` |  94.2% |  48.0% |  +5.3pp | 4967 |
| `deepseek-v4-flash-0731-nothink` | `deepseek-v4-flash-0731 (off)` | `deepseek-v4-flash-0731 (off)` |  93.6% |  47.2% |  +4.6pp | 4967 |
| `mistral-medium-3.5-128b-nothink` | `gemma-4-31b-it (off)` | `mistral-medium-3.5-128b (off)` |  93.5% |  46.6% |  +4.3pp | 4967 |
| `gemma-4-31b-it-nothink` | `gemma-4-31b-it (off)` | `gemma-4-31b-it (off)` |  92.9% |  46.4% |  +3.7pp | 4967 |
| `qwen3.8-27b-nothink` | `gemma-4-31b-it (off)` | `qwen3.8-27b (off)` |  92.6% |  46.2% |  +3.5pp | 4967 |

## Step 4 on its own

Every chain that has a step 4, scored on the text it produced -- so the rows are comparable whatever the runs did afterwards. Sorted by form accuracy, which asks whether the text is right as it stands; `gained` is the rise over step 3 (mined) as this step was handed it -- which after a `--from` is another run's file, and is named in the column for that step.

| produced by | step 2 | step 3 | step 4 | word accuracy | form accuracy | gained | scoreable |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| `gemma-4-31b-it-nothink` | `gemma-4-31b-it (off)` | `gemma-4-31b-it (off)` | `gemma-4-31b-it (off)` |  92.9% |  64.8% | +18.5pp | 4967 |

