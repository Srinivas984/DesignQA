# Run DesignQA in UiPath Studio

Open `project.json`, then open `Main.xaml` and press **Run**. The Studio workflow is the primary interface. FastAPI and the React website are optional.

## Demo

Enter `demo` in the first Input Dialog and `both` in the viewport dialog. Studio prepares the Brewly baseline and seeded variant at 1440 px and 375 px. The preparation step recaptures the reference on the current machine to minimize browser and font drift. No Figma token is required.

## Figma and a live website

Set `FIGMA_TOKEN` in the environment inherited by Studio and its Robot before starting a run. Use a token with file content read access. Keep the token out of the dialogs and workbook. Enter `figma`, select the viewports, and paste the design and live site URLs. A viewport requires a Figma frame of the matching width. Enter its node ID when there are several candidates. A frame specified in the URL or the only matching frame can be selected automatically.

The bridge retrieves the frame image and layer data and inspects the live DOM. It keeps high-confidence automatic CSS mappings. Review the mapping count in Studio Output and the Mapping sheet. Skipped layers are unverified and visual comparison still runs when there are no approved suggestions. The optional web interface provides interactive mapping corrections.

## Activities to demonstrate

| Sequence | Studio activities and responsibilities |
| --- | --- |
| Collect analysis input | **Input Dialog** collects mode and viewports. **Assign** normalizes the values. **If** validates choices and branches into the Figma, live URL and frame prompts. |
| Initialize and prepare Excel | **Invoke Code** locates Python and calls the input bridge. **Assign** creates a unique run ID and a per-run workbook path. **Write Line** logs workbook details and mapping coverage. |
| Get transaction data from Excel | **Invoke Code** runs the Excel reader through `--list` and returns enabled Excel row numbers. **Write Line** displays which rows will run. |
| Process each page and breakpoint | **For Each** runs one Excel row at a time. **Invoke Code** captures the engine's JSON status and exit code. **If** retries a system fault once. **Write Line** logs the result of each attempt. |
| Generate and display reports | **Invoke Code** builds and checks both reports and opens the findings workbook through Windows’ Excel file association. **Write Line** displays the counts and paths. |

The run folder is `Output/uipath/<run-id>/`. It holds `Input/pages.xlsx`, `transactions.log`, individual row results, comparison images, `report.html`, `findings.xlsx`, and `summary.json`. The input workbook has **Pages** (one URL and width per check), **Mapping** (labels, node IDs and CSS selectors), and **Settings** (capture thresholds and tolerances). The output workbook has **Findings** and **Summary**. Python handles workbook I/O and visual and CSS comparison. UiPath controls input, branching, transaction iteration, retry decisions, and reporting.

Microsoft Excel desktop is required for the final launch activity. For a fresh checkout on Windows, run these from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

Use `DESIGNQA_PROJECT_PATH` if Studio cannot locate the checkout, and `DESIGNQA_PYTHON` if the interpreter is outside the project virtual environment. This workflow follows the REFramework stages as Studio sequences.
