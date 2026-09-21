# Repackage Brother's existing x86_64 executables without changing their bytes.
%global debug_package %{nil}
%global __os_install_post %{nil}
%global _build_id_links none
%global brother_dir /opt/brother/PTouch/ql810w

Name:           ql810wpdrv
Version:        3.1.5
Release:        2.local.el10
Summary:        Brother QL-810W CUPS driver (local x86_64 repack)
License:        LicenseRef-Brother AND GPL-2.0-or-later
URL:            https://support.brother.com/
Source0:        ql810wpdrv-3.1.5-1.i386.rpm
Source1:        prepare.py
ExclusiveArch:  x86_64
BuildRequires:  cpio
BuildRequires:  python3
BuildRequires:  perl-interpreter
BuildRequires:  perl(Cwd)
BuildRequires:  perl(File::Copy)
Requires:       /usr/bin/perl
Requires:       perl(Cwd)
Requires:       perl(File::Copy)
Requires:       cups
Requires:       cups-filters
Requires:       ghostscript
Requires:       coreutils
Requires:       file
Requires:       grep
Requires:       sed
Requires:       which
Requires(post): policycoreutils
Requires(post): policycoreutils-python-utils
Requires(postun): policycoreutils-python-utils

%description
Local RHEL 10 repack of Brother's QL-810W driver. Contains the vendor's
unmodified x86_64 binaries, its PPD, and the Perl print filters with small
CUPS argument/path fixes. No 32-bit binaries or multilib requirements.
Installs the driver but does not create queues or restart printing services.
This is a local repack, not an official Brother or Red Hat package.

%prep
%setup -q -c -T
echo '5fb73626883be56bbee60cceafe151a614cf8cb46114cd9f22381d7556768911  %{SOURCE0}' | sha256sum -c -
rpm2cpio %{SOURCE0} > vendor.cpio
cpio -idm --quiet --no-absolute-filenames < vendor.cpio
python3 %{SOURCE1}

%build
# The vendor only supplies source for part of the driver. Reuse its x86_64 ELF files.

%install
src=opt/brother/PTouch/ql810w
dst=%{buildroot}%{brother_dir}
install -d "$dst"/lpd/x86_64 "$dst"/inf "$dst"/cupswrapper
install -m 0644 "$src"/LICENSE_*.txt "$dst/"
install -m 0755 "$src"/lpd/x86_64/* "$dst/lpd/x86_64/"
install -m 0755 "$src/lpd/filter_ql810w" "$dst/lpd/"
install -m 0755 "$src/cupswrapper/brother_lpdwrapper_ql810w" "$dst/cupswrapper/"
install -m 0644 "$src/cupswrapper/brother_ql810w_printer_en.ppd" "$dst/cupswrapper/"
for data in ImagingArea brql810wfunc brql810wrc paperinfql810w pdt3534.bin; do
    install -m 0644 "$src/inf/$data" "$dst/inf/"
done
for binary in rastertobrpt1 brpapertoolcups brpapertoollpr_ql810w brprintconfpt1_ql810w; do
    ln -s "x86_64/$binary" "$dst/lpd/$binary"
done
# RHEL's CUPS server binaries live in /usr/lib/cups even on x86_64.
install -d %{buildroot}/usr/lib/cups/filter %{buildroot}%{_datadir}/cups/model/Brother %{buildroot}%{_bindir}
ln -s %{brother_dir}/cupswrapper/brother_lpdwrapper_ql810w %{buildroot}/usr/lib/cups/filter/brother_lpdwrapper_ql810w
ln -s %{brother_dir}/cupswrapper/brother_ql810w_printer_en.ppd %{buildroot}%{_datadir}/cups/model/Brother/brother_ql810w_printer_en.ppd
for binary in brpapertoollpr_ql810w brprintconfpt1_ql810w; do
    ln -s %{brother_dir}/lpd/$binary %{buildroot}%{_bindir}/$binary
done

%check
perl -c %{buildroot}%{brother_dir}/cupswrapper/brother_lpdwrapper_ql810w
perl -c %{buildroot}%{brother_dir}/lpd/filter_ql810w
for binary in %{buildroot}%{brother_dir}/lpd/x86_64/*; do
    cmp "$binary" "opt/brother/PTouch/ql810w/lpd/x86_64/$(basename "$binary")"
done

%post
# Match the types used by Brother's installer, without world-writable directories.
if /usr/sbin/selinuxenabled; then
    for directory in lpd cupswrapper inf; do
        type=bin_t
        [ "$directory" != inf ] || type=cupsd_rw_etc_t
        pattern="%{brother_dir}/$directory(/.*)?"
        /usr/sbin/semanage fcontext -a -t "$type" "$pattern" 2>/dev/null ||
            /usr/sbin/semanage fcontext -m -t "$type" "$pattern" ||
            echo "WARNING: could not set SELinux context rule for $pattern" >&2
    done
    /usr/sbin/restorecon -R %{brother_dir} ||
        echo "WARNING: could not restore Brother driver SELinux labels" >&2
fi
exit 0

%postun
if [ "$1" -eq 0 ]; then
    for directory in lpd cupswrapper inf; do
        /usr/sbin/semanage fcontext -d "%{brother_dir}/$directory(/.*)?" 2>/dev/null || :
    done
fi
exit 0

%files
%defattr(-,root,root,-)
%dir /opt/brother
%dir /opt/brother/PTouch
%dir %{brother_dir}
%license %{brother_dir}/LICENSE_ENG.txt
%license %{brother_dir}/LICENSE_JPN.txt
%dir %{brother_dir}/inf
%{brother_dir}/inf/ImagingArea
%{brother_dir}/inf/brql810wfunc
%config(noreplace) %{brother_dir}/inf/brql810wrc
%config(noreplace) %{brother_dir}/inf/paperinfql810w
%{brother_dir}/inf/pdt3534.bin
%{brother_dir}/lpd
%{brother_dir}/cupswrapper
/usr/lib/cups/filter/brother_lpdwrapper_ql810w
%dir %{_datadir}/cups/model/Brother
%{_datadir}/cups/model/Brother/brother_ql810w_printer_en.ppd
%{_bindir}/brpapertoollpr_ql810w
%{_bindir}/brprintconfpt1_ql810w

%changelog
* Mon Sep 21 2026 Local Repack <clee@localhost> - 3.1.5-2.local.el10
- Package only the vendor's x86_64 binaries with automatic ELF dependencies.
- Own CUPS links in the RPM and omit legacy queue/service management scripts.
- Correct the CUPS input filename handling and use an absolute helper path.
- Normalize PPD line endings so the wrapper reads its default options correctly.
- Apply SELinux file contexts and retain root-owned, non-world-writable files.
