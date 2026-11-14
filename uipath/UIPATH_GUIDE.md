# Wiring the bot into UiPath (REFramework)

UiPath is the orchestrator; every heavy step is one `Start Process` / `Invoke Code` call to `scripts/run_qa.py`.
(The .xaml files themselves must be built in Studio - use the Autopilot prompts below to scaffold them.)

## Arguments / config
Add to Config.xlsx (Settings sheet of the REFramework project): `ProjectPath` (folder containing `scripts/`),
`PythonPath` (python.exe), `RunId` (set in Init as `"run_" & Now.ToString("yyyyMMdd_HHmmss")`).
Put the Figma token in an Orchestrator **Credential/Text asset** and set it as the `FIGMA_TOKEN` environment
variable for the process (Start Process > Environment variables, or Invoke PowerShell `$env:FIGMA_TOKEN=...`).
Never write the token to logs or Excel.

## State mapping
| REFramework state | What to do | Command |
|---|---|---|
| Init | read settings, create RunId, check Python | `python --version` |
| Get Transaction Data | get all rows once, deserialize JSON into a DataTable, give out one row per transaction | `python scripts/run_qa.py --list` |
| Process Transaction | run one row | `python scripts/run_qa.py --row <row> --run-id <RunId>` |
| Set Transaction Status | map exit code (below) | - |
| End | build the report, mail/Telegram the link | `python scripts/run_qa.py --report --run-id <RunId>` |

Use **Start Process** (FileName = PythonPath, Arguments as above, WorkingDirectory = ProjectPath, capture
StandardOutput and ExitCode), or the **Invoke Python Script** activity if you prefer the Python scope.

## Exit code -> transaction status
| Exit code | Meaning | Action |
|---|---|---|
| 0 | PASS | Success |
| 1 | design differences found | **Success** (the bot did its job; the findings are the output) - log a warning |
| 2 | row error; read `error_type` in the JSON | `BusinessError` -> BusinessRuleException (no retry); `SystemFault` -> throw System exception (REFramework retries) |

Parse stdout with **Deserialize JSON** (fields: row, page, breakpoint, status, ssim, findings, high, error, error_type).
`run_qa.py` already retries technical faults internally (MaxRetries in Settings).

## Optional steps after the report
- Read `Output/<RunId>/summary.json`; if `high > 0`, send an email / Telegram message with the report path.
- Read `findings.xlsx` (Read Range) and create a Trello/Jira ticket per High finding with the HTTP Request activity.
- Approval step: Action Center task "Accept these differences?" before closing tickets.

## Autopilot prompts (paste one at a time, test each before the next)
1. "Create a REFramework project. In Init read Config.xlsx Settings into a dictionary and set RunId to run_ plus the current timestamp. Check that PythonPath exists."
2. "In Get Transaction Data (first call only) run a process with PythonPath and arguments scripts/run_qa.py --list in ProjectPath, deserialize the standard output JSON array into a DataTable and return one row per transaction."
3. "In Process, run PythonPath with scripts/run_qa.py --row <row> --run-id <RunId>, capture StandardOutput and ExitCode, deserialize the JSON. If ExitCode is 2 and error_type is BusinessError throw BusinessRuleException with the error text; if SystemFault throw a System Exception. Exit codes 0 and 1 are success."
4. "In End, run scripts/run_qa.py --report --run-id <RunId>, read summary.json, and send an email with the report path and the counts of high, medium and low issues."
5. "Add a workflow that reads findings.xlsx and for each High row creates a Trello card with the HTTP Request activity."
