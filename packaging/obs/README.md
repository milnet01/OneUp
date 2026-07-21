# Publishing OneUp on the openSUSE Build Service (OBS)

OBS builds the RPM on openSUSE's infrastructure and hosts a repo so anyone can
`zypper install oneup` and get updates automatically. You need a free
[build.opensuse.org](https://build.opensuse.org) account. Everything below can be
done in the **web UI** — no local `osc` client required. `_service` fetches the
source **server-side** on OBS (which has network) and packs it **at build time**,
so you never run `osc service manualrun`.

> Account note: the OBS project is **`home:milnet`** (your OBS username). The
> GitHub source lives under **`milnet01`** (your GitHub username) — that's what
> `_service`'s clone URL points at. They're different accounts on purpose.

## One-time setup (web UI)

1. On [build.opensuse.org](https://build.opensuse.org), open **Your Home Project**
   (`home:milnet`) → **Create Package** → name it `oneup`, add a title/description.
2. On the package's **Overview** → **Add local files**, upload both:
   - `packaging/rpm/oneup.spec`
   - `packaging/obs/_service`
3. Add a build target: **project** `home:milnet` → **Repositories** →
   **Add from a distribution** → **openSUSE Tumbleweed** (and Leap if you want).
4. On the package page → **Trigger Services** (runs `obs_scm` server-side to fetch
   the tag; it also runs automatically when you upload/change `_service`).

That's it — OBS clones the tag server-side, packs it (tar → recompress →
`set_version`) and builds the RPM at build time, showing the result under **Build
Results**. Once green, the repo is live:

```
https://download.opensuse.org/repositories/home:/milnet/openSUSE_Tumbleweed/
```

*(Prefer the CLI? `zypper install osc`, then `osc checkout home:milnet oneup`, drop
the two files in, `osc add oneup.spec _service`, `osc commit`. The build-time
services mean you do **not** need `osc service manualrun`.)*

## Each release

Easiest: the repo's one-command release script (from the repo root):

```bash
./release.sh X.Y.Z      # bump all six version sites, gate, tag+push to GitHub,
                        # then update THIS OBS package via osc (which rebuilds)
```

It bumps the versions (`./bump.py`), runs `./local-CI.sh`, pushes the tag (GitHub
builds the AppImage), and — through your configured `osc` — commits the new
`_service`/`oneup.spec` here, retriggering the RPM build. Nothing to click.

**By hand (web UI)**, if you'd rather not use `osc`:

1. Push the new tag to GitHub (e.g. `v1.0.1`) so the source exists.
2. In `_service`, bump `revision` (the new tag) **and** `versionformat`, and
   re-upload `_service` (+ `oneup.spec` if its `%changelog` changed).
   `set_version` syncs the spec's `Version:` to the tag automatically.
3. **Trigger Services** → it rebuilds.

## Fully hands-off OBS rebuild (optional)

`./release.sh` already retriggers the OBS build (its `osc` step commits the new
`_service`/`oneup.spec`, which rebuilds the RPM). So the common path is **already
automated** — you don't need a webhook to get an OBS rebuild on release.

A GitHub → OBS **webhook** only adds value if you want a **bare `git push --tags`**
(bypassing `release.sh`) to rebuild OBS too. The repo ships the workflow config for
it at [`.obs/workflows.yml`](../../.obs/workflows.yml) (inert until you complete the
setup below). It's a one-time wiring:

1. **Create a workflow token on OBS.** Web UI: **Your Account → Tokens → Create
   Token → *Workflow*** (or `osc token --create --operation workflow --scm-token`).
   Copy the token secret.
2. **Add a webhook on GitHub.** Repo **Settings → Webhooks → Add webhook**:
   - Payload URL: `https://build.opensuse.org/trigger/workflow?id=<TOKEN_ID>`
   - Content type: `application/json`
   - Secret: the token secret from step 1
   - Events: **just the push event** (which carries tag pushes).
3. **Push a version tag** and watch OBS: the `rebuild_on_tag` workflow in
   `.obs/workflows.yml` fires `trigger_services`, so OBS re-clones the tag and
   rebuilds. Verify the build result shows the new version before relying on it.

> **Caveat (read `.obs/workflows.yml`'s header):** `trigger_services` rebuilds
> whatever `_service` pins as `<revision>`. `release.sh` keeps that revision in
> lockstep with the tag, so they agree. If you push tags **by hand**, bump
> `_service`'s `<revision>` in the same push, or convert the OBS package to build
> **directly from the git ref** (OBS's SCM-linked model) so any tag just works —
> a bigger one-time restructure, worth it only if you routinely tag without
> `release.sh`.

## Adding openSUSE Leap as a build target

OneUp already supports Leap at runtime — the engine runs `zypper update` on Leap
and `zypper dup` on Tumbleweed — so serving Leap is just adding a second OBS build
target. In the OBS web UI:

1. Open the package's **project** `home:milnet` → **Repositories** →
   **Add from a distribution** → pick the current **openSUSE Leap** (e.g.
   `openSUSE_Leap_15.6`) → **Add**.
2. OBS rebuilds the same `noarch` RPM against Leap automatically. Once green, the
   Leap repo is live alongside Tumbleweed:
   `https://download.opensuse.org/repositories/home:/milnet/openSUSE_Leap_15.6/`.

**One thing to verify:** the RPM `Requires: python3-pyside6`. That package is in
Tumbleweed's repos; on Leap it may be older or absent depending on the release. If
the Leap build's install check fails on `python3-pyside6` (or a Leap user hits an
unresolvable dependency), point Leap users at the **AppImage** instead — it bundles
its own Qt/PySide6 and doesn't depend on the distro's Python at all. Check with
`zypper info python3-pyside6` on a Leap box before advertising the Leap RPM.

## Notes

- `oneup.spec` is `BuildArch: noarch`, so one build serves every architecture.
- `obs_scm` runs server-side (it needs network to clone GitHub, which the isolated
  build VM doesn't have); `tar`/`recompress`/`set_version` run at build time off the
  committed source archive. If a build fails with *"no .obsinfo file found"*, the
  server-side fetch hasn't run yet — hit **Trigger Services** and rebuild.
