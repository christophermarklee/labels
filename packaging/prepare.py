"""Apply CUPS compatibility fixes to the checksum-pinned vendor payload."""
from pathlib import Path
import re

wrapper = Path("opt/brother/PTouch/ql810w/cupswrapper/brother_lpdwrapper_ql810w")
text = wrapper.read_text()
changes = {
    r"(?m)^[ \t]*\$CUPSINPUT\s*=\s*\$ARGV\[\d+\];[ \t]*$": (
        "    # Local repack: CUPS supplies its optional input filename in argv[5].\n"
        "    # Open it directly so spaces and shell metacharacters are safe.\n"
        "    open(STDIN, '<', $ARGV[5]) or die \"Cannot open CUPS input: $!\\n\";"
    ),
    r"(?m)^[ \t]*my\s+\$lpdconf\s*=[^;\n]+;[ \t]*$": (
        "# Local repack: resolve the helper independently of the CUPS PATH.\n"
        "    my $lpdconf = $lpddir.$LPDCONFIGEXE.$PRINTER;"
    ),
}
for pattern, replacement in changes.items():
    text, count = re.subn(pattern, lambda match: replacement, text)
    if count != 1:
        raise SystemExit(f"Unexpected vendor wrapper: expected one match for {pattern!r}")
wrapper.write_text(text)

# Perl chomp removes LF but leaves CR, preventing the wrapper from matching
# the vendor PPD's default values. read_text normalizes CRLF before writing.
ppd = wrapper.parent / "brother_ql810w_printer_en.ppd"
ppd.write_text(ppd.read_text())
