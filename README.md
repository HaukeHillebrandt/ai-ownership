# Diversifying AI Ownership — essay site

A situational-awareness.ai-style reading experience for the working paper
**Diversifying AI Ownership** (Hauke Hillebrandt, 2025), with a companion note on
Nick Bostrom's **Open Global Investment** model
([ogimodel.pdf](https://nickbostrom.com/ogimodel.pdf)), which cites it.

- `build.py` fetches the [Google Doc](https://docs.google.com/document/d/1ISGuSmNMRT_nVhGQ.../edit)
  at build time and converts the export into clean semantic HTML — so **editing the
  doc updates the site** on the next rebuild (daily at 06:17 UTC, on push, or manual).
- Bostrom's paper is summarised, not reproduced (copyright); the page links to the PDF.
- Stdlib-only build; Pillow optional for image optimization and social cards.

```sh
python3 build.py && cd dist && python3 -m http.server 8898
```
