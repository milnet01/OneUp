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
   **Add from a distribution** → **openSUSE Tumbleweed** and **openSUSE Leap 16.0**
   (both are already configured — see *Build targets* below).
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

A GitHub → OBS **webhook** only adds value if you want a **bare `git push`**
(bypassing `release.sh`) to poke OBS too. The repo ships the workflow config for it
at [`.obs/workflows.yml`](../../.obs/workflows.yml) (inert until you complete the
setup below). It's a one-time wiring — verified 2026-07-21 (home:milnet, token id
11691):

1. **Create the OBS workflow token.** OBS web UI: **Your Profile → Tokens → Create
   Token**, then:
   - **Type:** `workflow`
   - **Description:** anything, e.g. `OneUp — rebuild on GitHub push`
   - **SCM Token:** a **GitHub Personal Access Token** — OBS uses it to talk back to
     the repo. Create one at GitHub → **Settings → Developer settings → Personal
     access tokens → Tokens (classic)** with the **`public_repo`** scope (OneUp is
     public), and paste it here.
   - **Path for Workflows Configuration File:** `.obs/workflows.yml` (the default —
     leave it; it's read from the ref that triggered the build).
   - **URL to Workflows Configuration File:** leave **blank** (a URL, if given,
     overrides the path).

   On save, OBS shows the token's **Id**, its **Secret** (shown once — save it), and
   a **trigger URL** like `https://build.opensuse.org/trigger/workflow?id=<ID>`.
2. **Add the webhook on GitHub.** Repo **Settings → Webhooks → Add webhook**:
   - **Payload URL:** the token's trigger URL from step 1.
   - **Content type:** `application/json`
   - **Secret:** the OBS token **Secret** from step 1 (OBS verifies the payload's
     HMAC signature with it).
   - **Events:** *Just the push event* (tag pushes arrive as push events).

   A green "Last delivery was successful" on the webhook's ping means OBS accepted
   the connection.
3. **Push** and watch OBS: the `rebuild_on_tag` workflow in `.obs/workflows.yml`
   fires `trigger_services`, so OBS re-runs the package's services. Verify the build
   result before relying on it.

> **Caveat (read `.obs/workflows.yml`'s header):** `trigger_services` rebuilds
> whatever `_service` pins as `<revision>`. `release.sh` keeps that revision in
> lockstep with the tag, so they agree. If you push tags **by hand**, bump
> `_service`'s `<revision>` in the same push, or convert the OBS package to build
> **directly from the git ref** (OBS's SCM-linked model) so any tag just works —
> a bigger one-time restructure, worth it only if you routinely tag without
> `release.sh`.

## Build targets

Two, both live since 1.4.1 (2026-08-07):

| Target | Repository for users |
| --- | --- |
| `openSUSE_Tumbleweed` (i586, x86_64) | `https://download.opensuse.org/repositories/home:/milnet/openSUSE_Tumbleweed/` |
| `openSUSE_Leap_16.0` (x86_64) | `https://download.opensuse.org/repositories/home:/milnet/openSUSE_Leap_16.0/` |

OneUp supports both at runtime — the engine runs `zypper update` on Leap and
`zypper dup` on Tumbleweed — and `oneup.spec` is `BuildArch: noarch`, so the same
package serves each. The Leap build is tagged `lp160`
(`oneup-1.4.1-lp160.1.1.noarch.rpm`).

**Leap means 16.0 only.** Leap 15.6 reached end of life on 2026-04-30, and
`docs/standards/coding.md` §1 sets the Python floor at 3.13 on the strength of
that — 16.0 ships 3.13, 15.6 never did. Do not re-add a 15.x target without
revisiting the floor. Leap 16.0 also drops i586, which is why that arch is
Tumbleweed-only.

**The `Requires: python3-pyside6` question is settled, and the answer is not
obvious.** Leap 16.0 has no package of that name — it ships `python313-pyside6`.
It resolves anyway, because that package carries the unversioned provide:

```
$ rpm -qp --provides python313-pyside6-6.9.1-bp160.1.9.x86_64.rpm
python3-pyside6 = 6.9.1-bp160.1.9
python313-pyside6 = 6.9.1-bp160.1.9
```

So the spec needs no Leap-specific `Requires`. Re-check this if Leap ever moves its
primary Python flavour, since the unversioned provide follows whichever flavour is
primary. If it ever stops resolving, point Leap users at the **AppImage** — it
bundles its own Qt/PySide6 and does not depend on the distro's Python at all.

### Adding a further target

Project meta rather than the web UI, so the change is reviewable:

```bash
osc meta prj home:milnet > prj.xml     # edit: add a <repository> block
osc meta prj home:milnet -F prj.xml
osc results home:milnet oneup          # watch it build
```

## Notes

- `oneup.spec` is `BuildArch: noarch`, so one build serves every architecture.
- `obs_scm` runs server-side (it needs network to clone GitHub, which the isolated
  build VM doesn't have); `tar`/`recompress`/`set_version` run at build time off the
  committed source archive. If a build fails with *"no .obsinfo file found"*, the
  server-side fetch hasn't run yet — hit **Trigger Services** and rebuild.
