# Frog

Agent-team harness. Version **0.9.0**.

The `mira`, `r0`, and `r0-shadow` commands still run, print a warning, and will be removed in v1.0.0.

## Quickstart

Python 3.9 or newer. No extra libraries.

```bash
pip install -e .
frog doctor
```

The five working commands:

```bash
frog giao "change the function and leave a check"
frog team "draft a report from files in this folder"
frog agent "read the README and summarize it"
frog keys
frog doctor
```

`frog` with no arguments opens a session. With no API key, `frog menu` lists those five commands.

`frog bench` prints `công cụ benchmark nội bộ`. It is the internal benchmark tool: the 320-task shadow run, the labeling sheet, scoring, and the stats screen. It is not on the default menu.

## Measurement

The close bar is the pair `completed_correct` > 0 and `false_complete` = 0. That pair is not met. v1.0.0 is not frozen.

Cost is that round's ledger estimate. A round with baseline B adds A and B. G3 also adds the separate reason call.

| Round | model | cost | completed_correct | false_complete |
| --- | --- | --- | --- | --- |
| W5 | gpt-5.6-luna | $0.001213 | — | — |
| F3 | gpt-5.6-luna | $0.002601 | — | — |
| D3 | gpt-5.6-luna | $0.019703 | — | — |
| FIX-V | gpt-5.6-luna | $0.022812 | 0 | 0 |
| G3 | gpt-5.6-luna | $0.036389 | 0 | 0 |
| G1b | gpt-5.6-luna | $0.015626 | 2 | 1 |
| X3 | gpt-5.6-luna | $0.011378 | 0 | 0 |
| X4 | gpt-5.6-luna | $0.000286 | 0 | 0 |
| F-2 | gpt-5.6-luna | $0.019379 | 0 | 1 |
| FINAL | gpt-5.6-luna | $0.021082 | 0 | 1 |
| CRIT | gpt-5.6-luna | $0.015603 | 0 | 0 |
| TIER-1 | gpt-5.6-sol + gpt-5.6-luna | $0.038587 | 0 | 0 |
| FINAL-2 | gpt-5.6-sol + gpt-5.6-luna | $0.153721 | 2 | 1 |

Every figure is a ledger estimate on a real OpenAI model from 2026-10-14, not an invoice. T-REAL on the old overnight suite is `not_evaluated`. See [docs/history/](docs/history/).

## Two-minute demo

Ask to fix `sum_to`, which loops with the wrong `range(n)`. frog: intake, then the brief, then the worker in staging, then the validator, then handoff with a table for each criterion. If the file changes after the check, the evidence expires and frog does not hand off.

This local stub finishes in well under two minutes. It does not call a paid model.

```bash
py -3 -m unittest discover -s tests -p test_giao_execute.py -k test_validator_di_het_giao_den_promote
```
