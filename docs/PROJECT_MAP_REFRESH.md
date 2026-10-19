# Project diagram PDF

Owner request, 15 October 2026: keep the horizontal project diagrams in a PDF and refresh it after meaningful project work, without scheduled checks.

## When to refresh

Before closing work that changes architecture, a research-loop connection, automatic behavior, model responsibilities, verification status or an operating blocker:

1. Read the latest checkpoint and relevant source. Compare with the last reviewed map. Do not turn planned behavior into implemented behavior because a document describes it.
2. Update the affected diagram, function descriptions, status and source references. Keep code-driven work, automatic loops, numerical models, language models and human approval distinct. Keep the diagrams horizontal.
3. Rebuild the PDF, inspect the rendered pages and verify every page and navigation link. Report any obstacle honestly; never mark an old map current merely by changing its date.

No timer, watcher, scheduled automation, service, Strata start or product runtime is authorized by this documentation workflow. It does not clear storage admission or permit project tests. Artifact generation and previews stay outside the storage-blocked repository. This refresh is an agent completion step, not an automatic background monitor.

## Stable local files

Artifact folder:

`C:\Users\bgonn\.codex\visualizations\2026\10\15\01a14191-f4fd-7730-8c3f-810c63c1b081`

- Editable interactive map: `compertum-project-map.html`.
- PDF roadmap page: `project-roadmap.json`; keep its completed work, missing pieces, implementation order and admission dependencies current.
- PDF generator: `build_project_map.py`.
- Reviewed source fingerprints: `map-source-review.json`.
- Current PDF: `output\pdf\Compertum-project-map.pdf`.
- Preview images: `tmp\pdfs\`.

The PDF has nine landscape pages, including a roadmap on page 2, internal page navigation, function descriptions and source references. The generator reads only source, schemas and named documentation; it does not run Compertum or inspect credentials, runtime databases or datasets.

Preserve the owner's visual design: charcoal background, orange highlights, warm-grey text and accents, and embedded Google Sans. Main diagram text is 11.2 points, with 14-point node headings. Source references are stored in clickable PDF notes to keep space for the larger text. The installed font is `C:\Users\bgonn\AppData\Local\Microsoft\Windows\Fonts\GoogleSans-Regular.ttf`; report a missing font rather than silently substituting another family.

## Refresh procedure

Use the current PDF skill and bundled workspace runtime. After actually reviewing the changed source and reconciling the HTML map, run:

```powershell
& 'C:\Users\bgonn\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' `
  'C:\Users\bgonn\.codex\visualizations\2026\10\15\01a14191-f4fd-7730-8c3f-810c63c1b081\build_project_map.py' `
  --record-reviewed-sources
```

Without `--record-reviewed-sources`, the generator refuses changed source, map or roadmap fingerprints. That protects against silently presenting stale diagrams as current. The flag records a completed review; it does not perform the review. Update the map's status footer when operating state changes; the PDF reads that same status rather than maintaining a separate copy.

Render all pages with bundled Poppler and inspect them before delivery. Keep the stable PDF path so later refreshes replace the current document. A PDF opened in a viewer may need reopening to show the replacement. If the artifact folder is unavailable in a future chat, report that limitation and reconstruct from reviewed source; do not claim a refresh occurred.
