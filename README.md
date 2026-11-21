# Research portfolio

The GitHub Pages destination is [computational-social-science.github.io](https://computational-social-science.github.io/). The site uses the root of the `main` branch in `Computational-social-science/computational-social-science.github.io`.

The homepage presents the Matthew Effect case. The [working manuscript](manuscript.html) includes the research narrative, [individual scientist cards](manuscript.html#robert-k-merton), [annual name frequencies](manuscript.html#figure-1), [paired summary scores](manuscript.html#figure-2) and source notes. Printed pages retain the figures and captions. Mathematical expressions are typeset locally from the chapter’s LaTeX. The [standalone poster](assets/matthew-effect-poster.svg) and [print PDF](assets/matthew-effect-poster.pdf) use the same A4 canvas.

The [name-frequency explorer](matthew-matilda/explorer.html) displays the original paired observations and fits alongside the current Google Books English name queries. Its [A4 figure sheet](matthew-matilda/figures-a4.pdf) includes both panels for printing. The exporter verifies these assets against their figure and input hashes in Horisma.

## Update an edition

Run `scripts/sync_horisma.py <Horisma workspace>` with the Python environment used to generate the Horisma manuscript and poster. The exporter checks the saved manuscript against its editorial revision, checks both poster files against that edition’s receipt, and rebuilds the static files. Repeating the export with identical inputs preserves their contents.

For a changed edition, review the public text and media together, then commit the changed site files to `main`. GitHub Pages serves the repository root. After deployment, verify the served manuscript and artwork against the committed files. The Horisma research cycle performs this update when a verified finding changes the edition. Raw sources and editorial work files stay in the research workspace.

Run `python scripts/publish_pages.py --check-only` to verify a clean committed edition locally. Run `python scripts/publish_pages.py` after authorizing the `Computational-social-science` account in Git Credential Manager. The publisher checks that account and origin, enables Pages from `main:/` if needed, and compares the files GitHub Pages serves with the committed edition.
