# Labels

A small local FastAPI app to type, preview, and print text labels on the Brother
QL-810W. One Python module, one HTML page, no frontend build or database.

```sh
uv run python main.py
```

Open **http://127.0.0.1:8000**. Choose the loaded roll, type a label, and click
**Print label**. Text shrinks to fit inside 4 mm margins. Preview and print use the
same monochrome 300 dpi render. Printing submits to CUPS and reports the job ID;
a queued job does not mean physical printing has completed.

The default is **62 mm continuous tape, cut at 100 mm** for the supplied black/red
on white sample roll. This version produces black text only. It also offers 29 mm
continuous tape at 100 mm, and 29 × 90 / 62 × 100 mm die-cut labels. Arbitrary cut
lengths and red text are not implemented. Choose **62 mm black/red roll** for this
sample roll: even black-only text requires two-color mode. The app uses
`brother-ql` to generate black and empty red raster planes, sent through CUPS with
`-o raw` so the monochrome vendor filter does not alter them. Other roll choices
use a correctly sized PDF through the vendor driver. This targets CUPS 2.x.

## Printer setup

Brother drivers and source archives are **not included** in this repository.
Download them directly from Brother; see [packaging notes](packaging/README.md)
to build the local RHEL 10 x86_64 package.

### Official Brother downloads

[Home](https://support.brother.com/g/b/index.aspx?noautojudge=true) →
[United States](https://support.brother.com/g/b/countrytop.aspx?c=us&lang=en) →
[QL-810W / 810Wc](https://support.brother.com/g/b/producttop.aspx?c=us&lang=en&prod=lpql810weus) →
[Downloads — Linux (rpm)](https://support.brother.com/g/b/downloadlist.aspx?c=us&lang=en&os=131&prod=lpql810weus).

Select **CUPS wrapper/LPR printer driver (rpm package) (32-bit)**. The repack
recipe expects `ql810wpdrv-3.1.5-1.i386.rpm`, downloaded into a local `drivers/`
directory. Despite its filename, this package also contains x86_64 binaries.
The separate CUPS wrapper source archive is not needed for the repack.

This repository contains our app, configuration, and local packaging tools, with
no bundled Brother source code, binaries, PPDs, documentation, or license files.
Downloads, extracted files, and generated RPMs stay local and are ignored by Git.
Brother's software remains subject to its own terms. This is an independent
project, not an official Brother product. Python dependencies are installed by
`uv` from PyPI and are not vendored here.

### Configure CUPS

CUPS must have a queue before the app can print. Turn on the printer and connect
USB. If `ipp-usb` claims the QL-810W, its driverless queue may fail creation. This
host uses a model-specific exclusion so the CUPS USB backend can own the device:

```sh
sudo install -D -m 0644 packaging/ipp-usb-ql810w.conf /etc/ipp-usb/quirks/ql810w.conf
sudo systemctl restart ipp-usb
```

Then find the actual URI:

```sh
sudo lpinfo -v
```

Create a queue using the returned `usb://Brother/...` URI (replace the placeholder):

```sh
sudo lpadmin -p Brother_QL810W -E -v 'USB_URI_FROM_LPINFO' \
  -P /usr/share/cups/model/Brother/brother_ql810w_printer_en.ppd \
  -o PageSize=62X1
```

Click **Refresh printers** in the app. Use `lpstat -p` and `lpstat -o` to check
printer/job status, or `cancel JOB_ID` to cancel a queued job. The app itself runs
as your normal user, with no sudo. Keep it on localhost; it has no user accounts.

System requirements: the Brother driver, CUPS client commands (`lp`, `lpstat`),
and fontconfig with a sans font. `LABEL_FONT=/path/to/font.ttf` overrides the font.

## Checks

```sh
uv run python -m unittest -v
```

Tests cover image dimensions/margins, PDF page size, black/red raster planes, print options, invalid
input, missing printers, CUPS errors, and cross-site print rejection. Print
submission is mocked in these tests, so they use no paper. Physical printing has
also been confirmed on a USB-connected QL-810W with the 62 mm black/red sample
roll on RHEL 10.2.
