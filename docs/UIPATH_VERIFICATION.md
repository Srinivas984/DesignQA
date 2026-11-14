# UiPath verification

## Recorded checks

| Check | Result |
| --- | --- |
| Studio demo transaction loop | Executed. Two baseline passes, two expected seeded failures, zero execution errors. |
| Flipkart frame comparison in Studio | Executed. UiPath created the Excel workbook using Excel automation, saved it and displayed it. All 14 rows matched comparison JSON. |
| Main input contract | Automated test passed. Exactly two prompts for frame URL and live URL. |
| Main automatic width | Fixture-backed test passed using an 858 px selected frame with another frame of the same width in the file. |
| Main ambiguous page input | Fixture-backed test passed. It requests a frame-specific link. |
| Main missing-token handling | Test passed. The error explains the one-time Windows user environment setup. |
| Python API regression suite | Four test methods passed, including real Chromium demo capture and report generation. |
| Main authenticated Figma-to-website run | Pending. No FIGMA_TOKEN or corresponding implemented website URL has been supplied. |

The updated Main input contract and backend preparation tests do not establish an authenticated end-to-end run. The connected Figma tool and the standalone UiPath Robot use separate credentials.

The frame entry point operates on exported source data already present in Output. The repository excludes user exports and run artifacts. After cloning, supply a matching source bundle before executing that entry point.
