# Web application verification

Executed on Windows using Python 3.14.7, Playwright Chromium, and the production React build.

| Check | Evidence | Result |
| --- | --- | --- |
| Figma URL parsing and missing token | Local parser and FastAPI input tests | Passed |
| Invalid live URL | FastAPI rejected loopback input | Passed |
| DNS failure | Injected resolver failure returned a failed job with SystemFault | Passed |
| Frame discovery and manual mapping review | Fixture-backed state-transition test covered selection, rejection of a nonunique selector, approval, and persistence | Passed |
| Mapping confidence | Exact text, ambiguous candidates, and saved selector tests | Passed |
| Export credential handling | Transport test verified no token header and disabled redirects | Passed |
| Brewly baseline | Actual Chromium captures and Python comparisons at both widths | PASS at 1440 and 375 px, zero findings and SSIM 1.0 |
| Brewly seeded page | Actual Chromium captures and Python comparisons at both widths | 14 findings at 1440 px, SSIM 0.9569. 13 findings at 375 px, SSIM 0.9406. |
| Report and screenshot artifacts | API checked PNG signatures, embedded HTML images, Excel sheets and JSON parity | Passed |
| Browser flow | Submitted demo; checked desktop and mobile results; switched to overlay; downloaded Excel; reopened history | Passed |
| Public live DOM and capture | Chromium inspected the IANA Reserved Domains page at desktop width and captured a mapped heading at mobile width | Passed |
| Authenticated Figma comparison | Requires a readable file and access token | Pending |

The seeded desktop findings include font size, CTA background colour, corner radius, missing badge and vertical shift. The mobile CSS overrides the seeded font-size change, and the remaining four seeded defects were detected on mobile. The demo regenerates its reference through Chromium at each requested width to control for installed fonts and browser rendering.

Fixture-backed review and transport tests exercise controlled inputs. The demo and browser smoke test execute the real capture, comparison, and report pipeline.

