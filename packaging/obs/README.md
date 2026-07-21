# Publishing OneUp on the openSUSE Build Service (OBS)

OBS builds the RPM on openSUSE's infrastructure and hosts a repo so anyone can
`zypper install oneup` and get updates automatically. You need a free
[build.opensuse.org](https://build.opensuse.org) account and the `osc` client
(`zypper install osc`).

## One-time setup

```bash
# Create your package (once):
osc meta pkg -e home:milnet oneup      # opens an editor; save to create it
osc checkout home:milnet oneup
cd home:milnet/oneup
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
https://download.opensuse.org/repositories/home:/milnet/openSUSE_Tumbleweed/
```

## Notes

- `oneup.spec` is `BuildArch: noarch`, so one build serves every architecture.
- Bump `Version:` **and** the `%changelog` stanza in the spec, and the `versionformat`
  **and** `revision` (the new release tag, e.g. `v1.0.1`) in `_service`, together for each
  release — keep them in step with `CHANGELOG.md`. `revision` is a tag, not `main`, so an
  `osc service manualrun` can't repackage post-release commits under the old version.
