# Brother QL-810W — local RHEL 10 x86_64 repack

This directory contains locally authored packaging tools, not Brother's driver
or source code. Download the input RPM from the official
[Brother QL-810W / 810Wc downloads page](https://support.brother.com/g/b/downloadlist.aspx?c=us&lang=en&os=131&prod=lpql810weus):
choose **CUPS wrapper/LPR printer driver (rpm package) (32-bit)** and save
`ql810wpdrv-3.1.5-1.i386.rpm` into a local `drivers/` directory.

Build the package using the instructions below before installing it. The output,
`drivers/ql810wpdrv-3.1.5-2.local.el10.x86_64.rpm`, reuses Brother's four supplied
x86_64 binaries unchanged. It is a local repack, not an official Brother or Red
Hat release. All input downloads, generated RPMs (including source RPMs), and
extracted files are excluded from Git. No vendor artifacts are published here.

## Install

From the project directory:

```sh
sudo dnf install ./drivers/ql810wpdrv-3.1.5-2.local.el10.x86_64.rpm
```

The package installs the driver and sets SELinux file contexts when SELinux is
enabled. It does not create a printer queue, change the default printer, restart
CUPS, or print a label. Configure a queue in the CUPS interface using the
**Brother QL-810W CUPS** model and the actual USB device URI. Select the paper size
matching the installed roll; the vendor default is **29 × 90 mm**.

For command-line configuration, first inspect `lpinfo -v`, then use the selected
URI with `lpadmin` and this PPD:

```text
/usr/share/cups/model/Brother/brother_ql810w_printer_en.ppd
```

## Changes

- Removes the i686 payload and regenerates dependencies from only x86_64 ELF files.
- Packages CUPS links directly, replacing the vendor's legacy installer scripts
  that manage queues, services, and `/etc/printcap`.
- Retains the vendor directory layout and configuration utilities.
- Fixes the wrapper's optional input filename handling, including filenames with
  spaces, and resolves its configuration helper by absolute path.
- Normalizes PPD line endings to LF. The vendor Perl wrapper leaves CR characters
  in default option values when reading the original CRLF file.
- Keeps files root-owned and directories non-world-writable. Configuration changes
  using Brother's utilities require suitable administrative permissions.
- Registers SELinux `bin_t` labels for executables and `cupsd_rw_etc_t` for the
  configuration directory, following the original installer's types. Removes
  these local context rules on final package removal.

## Build and verify

Build dependencies include `rpm-build`, `cpio`, `python3`, `perl-interpreter`,
`perl-PathTools`, and `perl-File-Copy`. No compiler is needed. Run as a normal user:

```sh
bash packaging/build.sh
```

The script pins the original RPM's SHA-256 and creates both the binary RPM and
`drivers/ql810wpdrv-3.1.5-2.local.el10.src.rpm`. The source RPM contains the original
vendor RPM, the repack spec, and the wrapper/PPD preparation script; it is not the
source code for the proprietary renderer. Build files remain in `build/rpmbuild/`.

With `bubblewrap`, CUPS tools, Ghostscript, and runtime dependencies installed:

```sh
python3 packaging/verify.py
sudo rpm -U --test ./drivers/ql810wpdrv-3.1.5-2.local.el10.x86_64.rpm
```

The verifier extracts the finished RPM and checks architecture, dependencies,
permissions, dynamic loading, and the PPD. It renders a PostScript label from both
stdin and a filename and checks identical output, then renders a PDF label.
These checks run in private namespaces with writable temporary directories and
no network or USB access. Namespace creation must be permitted on the host.
The RPM dry run checks host dependencies and file conflicts without installation.

These checks do not validate physical label output or the running CUPS service's
SELinux access. A USB print test after installation is still needed. The PPD
validator reports advisory warnings about Brother's nonstandard paper-size names;
those names are retained because the driver uses them.
