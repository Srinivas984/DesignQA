# Design-vs-Live QA Bot project audit

## Source and scope

Inspected `../DesignQA.zip` and the existing extraction in this directory. SHA-256 checks matched every regular file in the archive to its extracted copy. Reviewed all seven Python modules, the demo generator and launchers, requirements, the four workbook sheets, and the UiPath guide. The bundled reports are historical samples.

## Architecture and existing functionality

| File | Responsibility |
| --- | --- |
| `scripts/run_qa.py` | Reads workbook configuration, enumerates enabled rows, runs page checks, retries system faults, and assembles a run. |
| `scripts/common.py` | Resolves project-relative paths, normalizes CSS values, and defines business and system exceptions. |
| `scripts/figma_client.py` | Reads `FIGMA_TOKEN`, requests a rendered frame PNG and mapped node metadata, and converts supported Figma styles and frame-relative bounds. |
| `scripts/capture.py` | Uses Playwright Chromium to freeze animation, hide configured selectors, scroll to load content, take full-page screenshots, and read matched elements' computed styles and bounds. |
| `scripts/diff.py` | Uses OpenCV and scikit-image to align widths, compute grayscale SSIM over the common image area, and annotate changed regions. |
| `scripts/compare_styles.py` | Compares mapped elements for presence, typography, color, corner radius, and layout using tolerances. |
| `scripts/report.py` | Generates an HTML report with embedded images and an Excel workbook with Summary and Findings sheets. |
| `demo/make_demo.py` | Generates the Brewly responsive baseline, a variant with five combined bugs, local design PNGs and style snapshots, and the demo workbook. |

A result is `FAIL` when it contains High or Medium findings. A low-severity radius finding can coexist with `PASS`. The supplied font-size mutation only applies at 1440 px because mobile CSS overrides it. The report tracks page-height drift separately from SSIM.

## Workbook contract

- **Pages** has four enabled rows for the Brewly baseline and combined-bug page at 1440 and 375 px. A fifth row is a disabled Figma example. Headers are Enabled, PageName, Breakpoint, LiveURL, Threshold, FigmaFileKey, FigmaNodeId, DesignImage, and DesignStyles. Local design assets take precedence when both are supplied.
- **Mapping** has eight selector mappings per enabled page and breakpoint. Its join key is PageName plus Breakpoint. Each row holds a Label, FigmaNodeId, and CssSelector. Page ID and per-property validation or expected overrides are absent.
- **Settings** stores ColorTolerance, FontSizeTolerancePx, RadiusTolerancePx, LayoutTolerancePx, MinRegionArea, HideSelectors, TimeoutMs, and MaxRetries. Threshold lives on Pages, output is supplied with `--out`, and the capture viewport height defaults to 900 px. There is no separate UiPath settings workbook.
- **Legend** documents local and Figma setup. Generating the demo rewrites `config/pages.xlsx`, so preserve customized workbooks before running the launcher.

## CLI and UiPath integration

| Command | Contract from source |
| --- | --- |
| `python scripts/run_qa.py --list` | Returns an array of enabled transactions with physical Excel `row`, `page`, and `breakpoint`. |
| `python scripts/run_qa.py --row 2 --run-id R` | Returns a JSON object with row, page, breakpoint, status, SSIM, error, error_type, findings count, and high count. Full evidence is saved in `Output/R/rows/2.json`. |
| `python scripts/run_qa.py --report --run-id R` | Aggregates saved row JSON and returns the run ID, output directory, HTML path, and summary counts. Excel is written as `findings.xlsx` in that directory. Successful report generation exits 0 even with failed checks. |
| `python scripts/run_qa.py --all` | Executes enabled rows and builds reports in one command. |

Use the same config, output root, and unique run ID throughout a run. Drain stdout and stderr separately. Exit 0 for a row means PASS, exit 1 means FAIL from QA findings, and exit 2 represents a handled error. UiPath should treat 0 and 1 as completed transactions. Distinguish `BusinessError` from `SystemFault` using the JSON field. A config read failure, invalid row, or absent report inputs can exit 2 without that field. Unexpected failures can also terminate without structured JSON. Handle missing status, invalid JSON, and launch failures explicitly. Python already retries system faults according to MaxRetries. Configure one transaction retry owner to avoid multiplying attempts.

## Dependencies and gaps

- Python with Playwright, Chromium, opencv-python-headless, scikit-image, NumPy, openpyxl, and requests. The archive declares minimum versions in requirements.txt. Python 3.14.7 responds on this workstation.
- The UiPath folder has integration instructions only. No Studio project, XAML, settings template, transaction logs, or Studio execution evidence was supplied. Studio and Robot were not found on PATH or in the checked installation locations.
- There is no usable Figma file/frame mapping in the brief or archive. `FIGMA_TOKEN` is absent from the current process. Authenticated verification requires a readable Figma file, two real frame IDs, their mapped node IDs, a corresponding live URL, and a token available in the robot environment.
- The client accepts a file key and normalizes dashed node IDs. It does not extract the file key from a URL. It also sends the Figma API token header to the separate image download URL. Remove the credential from the export download before running a live Figma test.
- `HideSelectors` applies CSS visibility on the live capture, retaining the layout footprint. A matching reference needs the same visual treatment. Mapped elements are still queried for computed styles.
- No standalone variants for each bug, dynamic-content fixture, or reproducible ten-case execution record were supplied. Baseline exports may be sensitive to Chromium and font differences across operating systems. Exact zero findings need a fresh run.
- Browser startup and transient navigation faults can be system exceptions. Missing file, DNS lookup failure, connection refusal, and HTTP errors are currently classified as business errors. Use a distinct reproducible transient failure for retry verification.

## Implementation order

1. Run the existing CLI contract against the supplied workbook in an isolated output run. Confirm both breakpoint baselines and combined-bug evidence.
2. Correct Figma export authentication handling before live use. Configure and verify the real design at both widths once the inputs are available.
3. Wire UiPath REFramework with reusable workflows for settings, process execution, transaction status, and reports. Validate the project in Studio.
4. Execute the ten-case matrix, including independent bug variants, paired dynamic-content masking, and an observed technical retry. Preserve reports and timings.
5. Assemble setup, architecture, implementation, results, project report, and viva documentation using the verified behavior.

## Phase 1 verification on Windows

Executed with Python 3.14.7 and Playwright 1.65.2 in an isolated virtual environment. The supplied workbook and engine were preserved. Both runs exercised the actual CLI and produced HTML, Excel, and row JSON evidence.

| Check | Supplied reference captures | References regenerated in an isolated extraction |
| --- | --- | --- |
| `--list` | Exit 0, rows 2–5 | Exit 0, rows 2–5 |
| Row 2, baseline 1440 px | Exit 1, SSIM 0.9661, 10 findings | Exit 0, SSIM 1.0, zero findings |
| Row 3, baseline 375 px | Exit 1, SSIM 0.8727, 13 findings | Exit 0, SSIM 1.0, zero findings |
| Row 4, combined bugs 1440 px | Exit 1, 15 findings | Exit 1, 14 findings, including all five seeded bugs |
| Row 5, combined bugs 375 px | Exit 1, 16 findings | Exit 1, 13 findings, including all four bugs active at this width |
| `--report` | Exit 0, four checks | Exit 0, two PASS and two FAIL |

The regenerated desktop results directly identify font size (48 → 44 px), CTA background (#c8553d → #d98b2b), card radius (12 → 4 px), the missing badge, and the subtitle's 20 px vertical shift. Results are in `Output/verification_3699048b` and `Output/verification_regenerated/windows`. This phase verifies the combined fixture. The individual bug cases, exception and retry cases, dynamic-content case, authenticated Figma test, and UiPath run remain pending.
