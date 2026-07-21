# Publishing OneUp on the openSUSE Build Service (OBS)

OBS builds the RPM on openSUSE's infrastructure and hosts a repo so anyone can
`zypper install oneup` and get updates automatically. You need a free
[build.opensuse.org](https://build.opensuse.org) account. Everything below can be
done in the **web UI** — no local `osc` client required, because `_service` fetches
and packs the source **at build time** on OBS's servers.

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

That's it — OBS runs the build-time services (clone GitHub → tar → recompress →
`set_version`), builds the RPM, and shows the result under **Build Results**. Once
green, the repo is live:

```
https://download.opensuse.org/repositories/home:/milnet/openSUSE_Tumbleweed/
```

*(Prefer the CLI? `zypper install osc`, then `osc checkout home:milnet oneup`, drop
the two files in, `osc add oneup.spec _service`, `osc commit`. The build-time
services mean you do **not** need `osc service manualrun`.)*

## Each release

1. Push the new tag to GitHub (e.g. `v1.0.1`) so the source exists.
2. In `_service`, bump **`revision`** (the new tag) and **`versionformat`** to match,
   and re-upload `_service`. `set_version` (build-time) then syncs the spec's
   `Version:` to the tag automatically, so the tarball and spec versions can't drift.
3. Re-upload `oneup.spec` too if its `%changelog` changed (keeps rpmlint quiet).
4. Trigger a rebuild (it rebuilds on a new `_service`/`oneup.spec` automatically).

## Notes

- `oneup.spec` is `BuildArch: noarch`, so one build serves every architecture.
- All services run `mode="buildtime"`, so the whole fetch→pack→build happens
  server-side in the build VM — nothing is committed to the package but the two
  text files above.
