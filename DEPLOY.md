# Deploying Ever / Tapestry

**Verified 2026-09-07.** All layers green: **34/34** suites inside the Docker
image (32/34 on the Mac VM — the two "skips" there are only a missing local JDK,
not failures). Two ship-blockers were found and fixed, both already in this repo:

- **PyPI** `pyproject.toml` `py-modules` was missing `ever, forgive, emit, ffi,
  builtins_ml` — `pip install` then `ever run` would have crashed on import.
- **Dockerfile** had a parse error (multi-line `RUN python3 -c "..."` with no
  line-continuations) — `docker build` failed before building anything.

Everything below runs on your Mac in `~/Downloads/4ever`. Each target needs one
account/login — the only part I can't do for you.

---

## 0 · GitHub  (the hub — do first)
    brew install gh                 # if needed
    gh auth login                   # GitHub.com -> HTTPS -> browser
    cd ~/Downloads/4ever
    git add -A
    git commit -m "Consolidate Ever/Tapestry; fix PyPI modules, npm manifest, Dockerfile"
    gh repo create Zdycomp/4ever --public --source=. --remote=origin --push

## 1 · PyPI   (name `ever-lang` — confirmed available)
    cd ~/Downloads/4ever/2-interpreter-python
    python3 -m pip install --upgrade build twine
    python3 -m build
    python3 -m twine upload dist/*  # user: __token__   pass: <your PyPI token>
Install:  `pip install ever-lang`  ->  `ever run file.ever`

## 2 · npm    (published as `refix-cli` — `refix` was taken; command is still `refix`)
    cd ~/Downloads/4ever/7-refix-node
    npm login
    npm publish
Install:  `npm i -g refix-cli`  ->  `refix scan build.log`
Prefer branding? set name to `@codric/refix` in package.json (needs the codric
org on npm), then `npm publish --access public`.

## 3 · Docker (needs Docker Desktop running; retag `codric` to your Docker Hub user if different)
    cd ~/Downloads/4ever
    docker login
    docker build -t codric/ever:3.4 -t codric/ever:latest .   # self-verifies at build
    docker push codric/ever:3.4
    docker push codric/ever:latest
Run tests:  `docker run --rm codric/ever:3.4`
Serve web:  `docker run --rm -p 8088:8088 codric/ever:3.4 python3 -m http.server 8088 --directory 6-interface-html`

## 4 · Web playground
Already live as a shareable page (the "Ever Live" artifact).
Your Vercel copy is deployed but gated by Vercel's default SSO. To make it public:
vercel.com -> project **ever** -> Settings -> Deployment Protection ->
Vercel Authentication -> Disable. Or connect the GitHub repo (step 0) to Vercel
for auto-deploys, root set to `6-interface-html`.

---
_Cleanup:_ `rm -rf ~/Downloads/4ever/.claude-tmp` (my temp build tarball).
