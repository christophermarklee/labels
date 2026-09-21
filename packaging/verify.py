"""Validate the built RPM and render labels without installing or using USB.

Needs bubblewrap, CUPS tools, Ghostscript, and the RPM's runtime dependencies.
"""
import hashlib
from pathlib import Path
import subprocess
import tempfile

project = Path(__file__).resolve().parent.parent
rpm = project / "drivers/ql810wpdrv-3.1.5-2.local.el10.x86_64.rpm"


def run(args, **kwargs):
    result = subprocess.run(args, capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError(f"{args[0]} exited {result.returncode}:\n"
                           + result.stdout.decode(errors="replace")
                           + result.stderr.decode(errors="replace"))
    return result


assert run(["rpm", "-qp", "--qf", "%{ARCH}", str(rpm)]).stdout == b"x86_64"
requires = run(["rpm", "-qp", "--requires", str(rpm)]).stdout.decode()
for requirement in requires.splitlines():
    if requirement.startswith("libc.so.6"):
        assert "(64bit)" in requirement, requirement
assert "i686" not in requires
run(["rpm", "-K", str(rpm)])

with tempfile.TemporaryDirectory(prefix="ql810w-verify-", dir=project / "build") as work:
    root = Path(work)
    payload = run(["rpm2cpio", str(rpm)]).stdout
    run(["cpio", "-idm", "--quiet", "--no-absolute-filenames"], input=payload, cwd=root)
    base = root / "opt/brother/PTouch/ql810w"
    assert not (base / "lpd/i686").exists()
    for path in root.rglob("*"):
        if not path.is_symlink():
            assert not path.stat().st_mode & 0o022, f"Writable by group/other: {path}"
    binaries = sorted((base / "lpd/x86_64").iterdir())
    assert len(binaries) == 4
    for binary in binaries:
        assert "ELF 64-bit" in run(["file", str(binary)]).stdout.decode()
        run(["/lib64/ld-linux-x86-64.so.2", "--list", str(binary)])

    # Each invocation gets private temporary directories, no network or USB.
    sandbox = [
        "bwrap", "--die-with-parent", "--unshare-all", "--uid", "0", "--gid", "0", "--ro-bind", "/", "/",
        "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--tmpfs", "/var/tmp", "--tmpfs", "/run",
        "--ro-bind", str(root / "opt"), "/opt",
        "--ro-bind", str(root / "usr/lib/cups/filter"), "/usr/lib/cups/filter",
        "--setenv", "PPD", "/opt/brother/PTouch/ql810w/cupswrapper/brother_ql810w_printer_en.ppd",
        "--setenv", "DEVICE_URI", "offline-test",
    ]
    run(sandbox + ["cupstestppd", "/opt/brother/PTouch/ql810w/cupswrapper/brother_ql810w_printer_en.ppd"])
    label = root / "input label.ps"
    label.write_text(
        "%!PS-Adobe-3.0\n%%Pages: 1\n"
        "<</PageSize [82.2 255.1]>> setpagedevice\n"
        "/Helvetica findfont 10 scalefont setfont\n"
        "10 100 moveto (QL-810W) show\n10 50 50 20 rectfill\nshowpage\n"
    )
    wrapper = ["/usr/lib/cups/filter/brother_lpdwrapper_ql810w", "1", "test", "Offline label", "1", "PageSize=29x90"]
    stdin_result = run(sandbox + wrapper, input=label.read_bytes())
    file_result = run(sandbox + wrapper + [str(label)], input=b"")
    assert stdin_result.stdout == file_result.stdout, "stdin/filename rendering differs"
    pdf = root / "input label.pdf"
    run(["gs", "-q", "-dBATCH", "-dNOPAUSE", "-sDEVICE=pdfwrite", f"-sOutputFile={pdf}", str(label)])
    pdf_result = run(sandbox + wrapper + [str(pdf)], input=b"")
    for name, result in [("PostScript stdin", stdin_result), ("PostScript filename", file_result), ("PDF filename", pdf_result)]:
        # The vendor renderer writes page counters and INFO progress to stderr.
        errors = [line for line in result.stderr.decode(errors="replace").splitlines()
                  if not line.startswith(("Page = ", "Copies = ", "iPage = ", "INFO: "))]
        assert not errors, f"{name}: {errors}"
        assert len(result.stdout) > 1000, f"{name}: {len(result.stdout)} bytes; prefix={result.stdout[:300]!r}"
        assert b"\x1b\x40" in result.stdout[:1024], f"{name}: missing printer initialization: {result.stdout[:100]!r}"
        print(f"PASS {name}: {len(result.stdout)} bytes, SHA256 {hashlib.sha256(result.stdout).hexdigest()}")
print("PASS RPM architecture, dependencies, permissions, ELF loading, and CUPS PPD validation")
