# VolArb visual assets

The project wordmark is **VolArb**. File paths and canonical component identities remain unchanged.

## Identity

- [Light-background lockup](volarb-logo-light.svg) and [dark-background lockup](volarb-logo-dark.svg) combine the original VA mark and wordmark.
- [Standalone mark](volarb-mark.svg) is the compact two-form VA construction.
- The parallel diagonals give the V and A a shared rhythm; the A counter stays open at small sizes. The mark is not derived from NumPy's cube or another project's artwork.
- All final artwork is editable SVG: no embedded raster, remote fonts, gradients, shadows or scripts. The wordmark uses a system sans-serif fallback stack.

Light palette: cobalt `#4059d7`, teal `#008f88`, ink `#172544`.
Dark palette: cobalt `#8193ff`, teal `#43c9bf`, foreground `#f3f6fc`.

The README selects variants using GitHub's light/dark-mode link fragments so a repository theme override works even when it differs from the operating-system preference. Both sources have an accessible project-name alternative.

## Architecture

- [Desktop diagram](volarb-architecture.svg): ownership rail, prominent reusable engine, interface bar and supporting testbed.
- [Mobile diagram](volarb-architecture-mobile.svg): independently composed at the README's 768px breakpoint; not a scaled desktop layout.

These figures summarize the [canonical architecture](../../architecture/README.md), not a running deployment. Keep the implemented-contracts / incomplete-pipeline distinction when editing them. The near-white diagram panel is intentionally self-contained for either GitHub theme.

## Design provenance

The final identity was constructed directly as vector geometry. Built-in image generation was used only for discarded concept exploration; neither generated raster is a production asset. The final design brief was: a minimal two-form cobalt/teal VA monogram, one open A counter, consistent diagonal proportions, a restrained VolArb wordmark, and no decorative effects.

Review changes in actual GitHub rendering, including explicit light/dark themes, mobile layout and small mark sizes. Preserve the text alternatives and self-contained SVGs; keep screenshots and exploratory artwork outside source control.
