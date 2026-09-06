# Language (fixed)

- Write all wiki prose in Simplified Chinese (zh-CN).
- Keep code identifiers, paths, API names, and commands unchanged.
- Do not switch the wiki language.

# Required structure

- `index.md` / quickstart: navigation and how to use this wiki
- Architecture overview: system context, major components, runtime topology
- One page (or section) per substantial module/service with:
  - purpose and boundaries
  - key APIs / extension points
  - important invariants
  - primary source files and focused tests
- Cross-cutting concerns (auth, data, ops) when evidence warrants

# Format rules

- Use clear Markdown headings; keep page titles stable
- Link related pages with relative `.md` links
- Do not invent APIs or modules you have not inspected
- Do not rewrite `INSTRUCTIONS.md` or `FORMAT.md`