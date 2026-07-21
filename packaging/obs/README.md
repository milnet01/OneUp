# Publishing OneUp on the openSUSE Build Service (OBS)

OBS builds the RPM on openSUSE's infrastructure and hosts a repo so anyone can
`zypper install oneup` and get updates automatically. You need a free
[build.opensuse.org](https://build.opensuse.org) account and the `osc` client
(`zypper install osc`).

## One-time setup

```bash
# Create your package (once):
osc meta pkg -e home:milnet01 oneup      # opens an editor; save to create it
osc checkout home:milnet01 oneup
cd home:milnet01/oneup
```

## Each release

Copy the packaging files in and let OBS fetch + build the source:

```bash
cp /path/to/OneUp/packaging/rpm/oneup.spec .
cp /path/to/OneUp/packaging/obs/_service .

osc service manualrun          # runs _service: clones the repo, makes the tarball
osc add oneup.spec _service *.tar.gz
osc commit -m "oneup 1.0.0"    # triggers the build; watch it on the web UI
```

Add openSUSE Tumbleweed (and Leap, if you want) as build targets in the web UI
under **Repositories**. Once green, enable the download repo and share:

```
https://download.opensuse.org/repositories/home:/milnet01/openSUSE_Tumbleweed/
```

## Notes

- `oneup.spec` is `BuildArch: noarch`, so one build serves every architecture.
- Bump `Version:` in the spec and the `versionformat` in `_service` together for
  each release (keep them in step with `CHANGELOG.md`).
