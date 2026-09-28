# Diversifying AI Ownership — essay site

A long-form reading page for **Part I** of the working paper *Diversifying AI Ownership*
(Hauke Hillebrandt), with a companion note on Nick Bostrom's **Open Global Investment**
model ([ogimodel.pdf](https://nickbostrom.com/ogimodel.pdf)), which cites the paper.

- `build.py` renders the Google Doc's **first tab** (Part I) at build time via
  `docrender.py` (a copy of the one in the `hfh.pw` repo; keep them in sync). Later tabs
  (Part II, appendix, notes) stay in Google Docs; Part II is linked at the end of the essay.
- Editing the doc updates the site on the next rebuild: every 3 hours, on push, or on
  demand (`gh workflow run deploy.yml -R HaukeHillebrandt/ai-ownership`).
- The companion page summarises Bostrom's paper (drafted with AI assistance, labelled on
  the page) and links the PDF rather than reproducing it.
- Stdlib-only build; Pillow optional for image optimization and social cards.

```sh
python3 build.py && cd dist && python3 -m http.server 8898
```
