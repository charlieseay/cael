# Sidecar Packaging and Startup — Lessons Learned

Two hard-won lessons from the embedded sidecar work (2026-04-26).

## Python Dependencies in Portable Tarballs

Never use a virtualenv when packaging Python deps into a tarball for distribution or sidecar deployment.

Venv activation scripts embed absolute symlinks to the build-time temp directory. When the tarball is extracted to any other path, those symlinks are dead — the environment silently fails to load.

**Do this instead:**

```bash
python3 -m pip install --target ./site-packages <package> <package>
```

Install directly into a standalone directory using `--target`. This produces regular files with no symlinks, which survive relocation intact.

**Rule:** any Python environment that moves after installation (tarballs, bundles, sidecar drops) must use `--target` install, not a venv.

## Startup Timeouts for Model-Loading Services

Generic web service timeouts (15–30s) are wrong for services that load ML models on cold start.

faster-whisper loads a 244 MB model in 60–90s. A 30s `waitForReady` timeout caused the sidecar to silently enter `.failed` state and fall back to networked mode — with no error visible to the user.

**Fix:** set the startup timeout to at least **2× the model load time**.

For the faster-whisper sidecar, that means 120s minimum.

**Rule:** before setting any `waitForReady` or health-check timeout on a service, ask whether it loads a model or large artifact at startup. If yes, measure or estimate the load time and set the timeout to at least 2× that value. Never inherit a timeout from a generic web service template.
