# UiPath verification

## Executed checks

| Check | Result |
| --- | --- |
| Studio demo transaction loop | Two baseline passes, two expected seeded failures, zero execution errors. |
| Authenticated Main live run | Executed against Flipkart frame 1:2 and the supplied published app. Fourteen elements mapped, one QA FAIL, zero execution errors. Reports generated and Excel opened. |
| Text mapping corrections | Direct text candidates now outrank their surrounding buttons. Text-only controls exclude padding from measured text bounds. Browser colours are normalized before comparison. |
| Input selection | Tests cover explicit frame links, known page defaults, an unknown multi-frame selection, ambiguity and missing credentials. |
| Saved frame comparison in Studio | UiPath created, saved and opened the Excel workbook using Excel automation. |
| Grouped Flipkart frame report in Studio | Findings has 6 primary findings. Measurements retains all 14 original findings. Related measurements remain attached to the primary findings. |
| Independent position changes | NX/US CTA shifts remain primary findings. Grouping tests also preserve independent alignment changes. |
| Regression suite | 15 tests passed. Includes real Chromium baseline and seeded-defect captures. |

## Evidence and limits

The live Main run used the current Figma REST API with the configured local user credential and the published website. During investigation, the report initially included measurements of containers matched to text. The mapping and text-measurement fixes were checked through engine execution and regression tests. Main completed in Studio and opened Excel before the final text measurement refinement. That final refinement passed engine checks and remains available for subsequent Studio runs.

The frame workflow uses saved Figma node data and exports. Its optimized workbook was generated in Studio and checked against comparison JSON. Grouped measurements show consistent geometric relationships and do not establish the underlying CSS cause.

The frame picker is implemented and its selection path is covered by fixture-backed tests. A new arbitrary-file picker interaction in Studio has not been visually verified.

Tokens, user exports, local logs and generated run evidence are excluded from the repository. A fresh checkout requires its own Figma credential for Main or a matching export bundle for the frame workflow.
