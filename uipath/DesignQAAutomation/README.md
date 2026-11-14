# Run DesignQA in UiPath Studio

Open `project.json`, then open `Main.xaml` and press **Run**. The Studio workflow is the primary interface. FastAPI and the React website are optional.

Main asks for two URLs: the Figma design/file link and corresponding deployed website link. A frame-specific link selects that frame. Known file defaults are recorded in `config/figma_frames.json`. For another file containing several eligible frames, Main opens a picker with their names, sizes and IDs. Choose the reference and click **Compare**. Cancel stops the run. The chosen frame sets the viewport dimensions. The website URL comes from your implementation's hosting dashboard or developer.

The frame-comparison report groups typography dimensions and position changes that follow the measured heading-height change within the same container. **Findings** lists the primary checks and related measurements. **Measurements** retains every original finding, and **Summary** shows both counts. Independent position changes remain separate. Grouping expresses an observed layout relationship and does not prove the implementation's CSS cause. Main's live website measurements continue to use the existing comparison rules.

Supported inputs are accessible Figma Design or File URLs and public HTTP(S) websites. File permissions, token validity, network availability and screenshot limits still apply. Login-protected websites and Figma prototype URLs are outside this workflow. Generic or ambiguous layers may remain unmapped and appear as unverified coverage.

Configure `FIGMA_TOKEN` once as a Windows user environment variable. The bridge reads that value even when Studio was started earlier. The Figma plugin connection in this chat provides access for chat tools independently of the local Robot.

## Demo

For the connected Flipkart Figma export verification, open `FigmaFrameComparison.xaml` and select **Debug File (F6)**. It asks for the Figma file URL and finds its matching exported frames and node measurements under `Output`, runs the Python comparison in JSON-only mode, then uses Excel automation inside UiPath to create and save a new workbook. It populates Findings and Summary and leaves Excel visible. Each run has a unique folder under `Output/uipath/figma_<id>`. The source export must already be present. This entry point does not refresh Figma through the plugin.

The optional website's Demo Analysis still runs the Brewly baseline and seeded variant at 1440 px and 375 px. Main is dedicated to the two-link workflow.

## Figma and a live website

Verified example inputs for Main:

- Figma reference frame: https://www.figma.com/design/jBFz1c5xbu8mYP7FCSdQwE/Untitled?node-id=1-2
- Published website: https://boar-serve-28825024.figma.site

The original page link contains two frames. The frame-specific link above selects the reference at 858 px. Main now uses both its width and height for the live viewport. QA differences are a completed run, and appear as FAIL in the report when they exceed severity rules.

Set `FIGMA_TOKEN` in the environment inherited by Studio and its Robot before starting a run. Use a token with file content read access. Keep the token out of the dialogs and workbook. Paste the selected reference-frame URL and the implemented website URL into the two dialogs. The frame width is selected automatically. If the page has several frames, copy the intended frame link before running.

The bridge retrieves the frame image and layer data and inspects the live DOM. It keeps high-confidence automatic CSS mappings. Review the mapping count in Studio Output and the Mapping sheet. Skipped layers are unverified and visual comparison still runs when there are no approved suggestions. The optional web interface provides interactive mapping corrections.

## Activities to demonstrate

| Sequence | Studio activities and responsibilities |
| --- | --- |
| Collect analysis input | Two **Input Dialog** activities collect the Figma frame link and website link. **Assign** requests automatic frame-width selection. |
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
