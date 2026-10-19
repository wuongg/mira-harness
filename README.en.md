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

| Round | completed_correct | false_complete | Result |
| --- | --- | --- | --- |
| FINAL | 0 | 1 | V09 delivered `BAN NHAP` |
| CRIT | 0 | 0 | every task was held |
| TIER-1 | 0 | 0 | stopped after V05 |
| FINAL-2 | 2 | 1 | V01 and V04 correct; V09 still delivered the wrong text |

The detailed trail is in [docs/history/](docs/history/).
