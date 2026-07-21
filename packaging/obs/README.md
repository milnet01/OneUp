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

**Fully hands-off (optional):** OBS can rebuild on its own whenever you push a tag,
via its GitHub token + webhook ("SCM/CI workflow") integration — no local `osc`, no
re-upload. It's a one-time setup (an OBS token, a repo webhook, and building this
package from the git checkout instead of an uploaded `_service`); see the OBS docs
on *token/workflow integration*. Ask to have it wired up.

## Notes

- `oneup.spec` is `BuildArch: noarch`, so one build serves every architecture.
- `obs_scm` runs server-side (it needs network to clone GitHub, which the isolated
  build VM doesn't have); `tar`/`recompress`/`set_version` run at build time off the
  committed source archive. If a build fails with *"no .obsinfo file found"*, the
  server-side fetch hasn't run yet — hit **Trigger Services** and rebuild.
