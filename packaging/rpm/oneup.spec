%define app_id za.co.antsprojectshub.OneUp

Name:           oneup
Version:        1.0.0
Release:        0
Summary:        One-click openSUSE update dashboard
License:        MIT
URL:            https://github.com/milnet01/OneUp
Source0:        oneup-%{version}.tar.gz
BuildArch:      noarch

# The GUI needs Qt for Python; the engine calls zypper. Everything else is
# optional — OneUp skips steps for tools that are not installed.
Requires:       python3-pyside6
Requires:       zypper
# The engine performs every privileged step via sudo; without it the app installs
# but no update can run.
Requires:       sudo
Recommends:     flatpak
Recommends:     fwupd
Recommends:     libnotify-tools
Recommends:     ksshaskpass
Recommends:     snapper

%description
OneUp is a small Qt dashboard that updates openSUSE system packages, Flatpaks
and firmware, and cleans up leftover packages and the download cache — each an
optional toggle. It can check for updates read-only, follow the desktop
light/dark theme, and optionally check weekly in the background and notify you.

The GUI never runs as root; a small engine script (update_system.sh) does the
privileged work behind a single password prompt.

%prep
%autosetup -n oneup-%{version}

%build
# Pure Python — nothing to compile.

%install
# Application payload (GUI + engine live side by side).
install -Dm0644 updater.py        %{buildroot}%{_datadir}/oneup/updater.py
install -Dm0755 update_system.sh  %{buildroot}%{_datadir}/oneup/update_system.sh

# Launcher on PATH. Supports `oneup` (GUI) and `oneup --check` (headless).
install -dm0755 %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/oneup <<'EOF'
#!/bin/sh
exec python3 %{_datadir}/oneup/updater.py "$@"
EOF
chmod 0755 %{buildroot}%{_bindir}/oneup

# Desktop entry, icon and AppStream metadata.
install -Dm0644 data/%{app_id}.desktop \
    %{buildroot}%{_datadir}/applications/%{app_id}.desktop
install -Dm0644 data/%{app_id}.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/%{app_id}.svg
install -Dm0644 data/%{app_id}.metainfo.xml \
    %{buildroot}%{_datadir}/metainfo/%{app_id}.metainfo.xml

%files
%license LICENSE
%doc README.md
%{_bindir}/oneup
%{_datadir}/oneup/
%{_datadir}/applications/%{app_id}.desktop
%{_datadir}/icons/hicolor/scalable/apps/%{app_id}.svg
%{_datadir}/metainfo/%{app_id}.metainfo.xml

%changelog
* Tue Jul 21 2026 Anthony Schemel <aant.schemel@gmail.com> - 1.0.0-0
- First release.
