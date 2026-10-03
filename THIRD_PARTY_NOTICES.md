# Third-party notices

VolArb's proprietary license covers only rights owned by Shunya. Third-party
software and assets retain their respective copyright and license terms; the
restrictions in the root LICENSE do not override those terms.

Upstream notice text retains its original whitespace and line endings; the
narrow `.gitattributes` exceptions preserve those bytes without relaxing source
checks elsewhere.

## Bundled Plotly.js

`services/essvi-dashboard/vendor/plotly.min.js` is the unmodified Plotly.js
**2.35.2** distribution, copyright 2012–2024 Plotly, Inc., licensed under MIT.
The upstream license file records copyright (c) 2021 Plotly, Inc.; it is
reproduced without alteration in
[`plotly.LICENSE.txt`](services/essvi-dashboard/vendor/plotly.LICENSE.txt).
Preserve the bundled dependency notices in
[`plotly.min.js.LICENSE.txt`](services/essvi-dashboard/vendor/plotly.min.js.LICENSE.txt)
and the [supplemental dependency notices](services/essvi-dashboard/vendor/plotly-dependencies.NOTICES.txt).
The supplemental inventory preserves the upstream frozen dependency closure,
including notices absent from the minified file.

Sources: [versioned source](https://github.com/plotly/plotly.js/tree/v2.35.2),
[unmodified distribution](https://cdn.plot.ly/plotly-2.35.2.min.js),
[distribution notices](https://cdn.plot.ly/plotly-2.35.2.min.js.LICENSE.txt).

The vendored distribution's SHA-256 is
`6d21266ce1bd7d9e5ab4e115989c70c20de0382fd973a8f26ab58619eba4d603`.

## Embedded Recursive font

The five SVG diagrams in `agent/docs/diagrams/` embed Recursive font subsets,
**version 1.085**. Their font metadata records copyright 2019 The Recursive
Project Authors. The project's versioned license file records copyright 2020
The Recursive Project Authors and is retained verbatim in
[`Recursive-OFL.txt`](agent/docs/diagrams/Recursive-OFL.txt).

The embedded font software remains under the **SIL Open Font License 1.1**.
The OFL does not require the surrounding diagrams or repository to use that
license. Preserve the font license when redistributing the embedded font.
Source: [Recursive v1.085](https://github.com/arrowtype/recursive/tree/v1.085).

## Package-manager dependencies

Python and Node dependencies referenced by the repository's manifests and locks
are installed separately, not relicensed by Shunya. Their upstream license and
notice files apply to those packages. No dependency installation grants broader
rights to VolArb's proprietary source.
