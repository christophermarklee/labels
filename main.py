"""Local text labels: uv run python main.py."""
from functools import lru_cache
from io import BytesIO
import os
from pathlib import Path
import re
import subprocess
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field, field_validator

app = FastAPI(title="Labels")
DPI = 300
# Brother PPD identifiers: roll width, label length (mm).
SIZES = {"29x90": (29, 90), "62x100": (62, 100), "29X1": (29, 100), "62X1": (62, 100), "62red": (62, 100)}


class Label(BaseModel):
    text: str = Field(min_length=1, max_length=800)
    size: Literal["29x90", "62x100", "29X1", "62X1", "62red"] = "62red"
    align: Literal["left", "center"] = "center"
    font_size: int = Field(default=24, ge=8, le=72)

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value.splitlines()) > 10:
            raise ValueError("Enter between 1 and 10 lines of text.")
        if any(ord(char) < 32 and char != "\n" for char in value):
            raise ValueError("Use plain text and line breaks.")
        return value


class PrintLabel(Label):
    printer: str = Field(min_length=1, max_length=127, pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
    copies: int = Field(default=1, ge=1, le=20)


@app.middleware("http")
async def local_requests(request: Request, call_next):
    # Prevent other websites from submitting jobs to this local app.
    origin = request.headers.get("origin")
    if request.method == "POST" and (
        (origin and origin != str(request.base_url).rstrip("/"))
        or request.headers.get("sec-fetch-site") == "cross-site"
    ):
        return JSONResponse({"detail": "Open the app directly to print."}, status_code=403)
    return await call_next(request)


def command(args: list[str], data: bytes | None = None) -> str:
    try:
        result = subprocess.run(args, input=data, capture_output=True, timeout=15,
                                env={**os.environ, "LC_ALL": "C"})
    except FileNotFoundError as exc:
        raise HTTPException(503, "Install CUPS client tools (lp and lpstat).") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(504, "CUPS timed out. Check the queue before retrying.") from exc
    if result.returncode:
        error = result.stderr.decode(errors="replace").strip()
        raise HTTPException(503, error or "CUPS is unavailable.")
    return result.stdout.decode(errors="replace").strip()


@lru_cache(maxsize=1)
def font_path() -> str:
    if configured := os.environ.get("LABEL_FONT"):
        return configured
    try:
        return subprocess.check_output(["fc-match", "-f", "%{file}", "sans"], timeout=5).decode()
    except (OSError, subprocess.SubprocessError) as exc:
        raise HTTPException(503, "Install fontconfig and a sans font, or set LABEL_FONT.") from exc


def render(label: Label) -> Image.Image:
    width, length = SIZES[label.size]
    # Horizontal editor; rotate to the roll feed direction when printing.
    image = Image.new("L", (round(length * DPI / 25.4), round(width * DPI / 25.4)), 255)
    draw = ImageDraw.Draw(image)
    margin = round(4 * DPI / 25.4)
    for pixels in range(round(label.font_size * DPI / 72), 7, -1):
        try:
            font = ImageFont.truetype(font_path(), pixels)
        except OSError as exc:
            raise HTTPException(503, "Cannot load the label font. Check LABEL_FONT.") from exc
        spacing = max(2, pixels // 5)
        box = draw.multiline_textbbox((0, 0), label.text, font=font, spacing=spacing, align=label.align)
        tw, th = box[2] - box[0], box[3] - box[1]
        if tw <= image.width - 2 * margin and th <= image.height - 2 * margin:
            x = margin if label.align == "left" else (image.width - tw) / 2
            y = (image.height - th) / 2
            draw.multiline_text((x - box[0], y - box[1]), label.text, font=font,
                                fill=0, spacing=spacing, align=label.align)
            return image.point(lambda value: 255 if value >= 160 else 0, mode="1")
    raise HTTPException(422, "Too much text for this label. Use fewer words or a larger size.")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(Path(__file__).with_name("index.html"))


@app.get("/api/printers")
def printers():
    return {"printers": command(["lpstat", "-e"]).splitlines()}


@app.post("/api/preview")
def preview(label: Label):
    output = BytesIO()
    render(label).save(output, format="PNG")
    return Response(output.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})


@app.post("/api/print")
def print_label(label: PrintLabel):
    if label.printer not in printers()["printers"]:
        raise HTTPException(422, "Select an existing CUPS printer. Refresh the printer list.")
    image = render(label).transpose(Image.Transpose.ROTATE_90)
    args = ["lp", "-d", label.printer, "-n", str(label.copies), "-t", "Label", "-o", "job-sheets=none"]
    if label.size == "62red":
        from brother_ql.conversion import convert
        from brother_ql.raster import BrotherQLRaster
        # 696 printable dots across; the printer supplies 35 feed dots at each end.
        # These cropped areas are white inside our 4 mm margins.
        image = image.crop((18, 35, 714, image.height - 35)).convert("RGB")
        raster = BrotherQLRaster("QL-810W")
        raster.exception_on_warning = True
        data = convert(raster, [image], "62red", red=True, rotate=0, cut=True)
        args += ["-o", "raw"]
    else:
        output = BytesIO()
        image.save(output, format="PDF", resolution=DPI)
        data = output.getvalue()
        args += ["-o", f"PageSize={label.size}", "-o", "orientation-requested=3",
                 "-o", "print-scaling=none", "-o", "BrCutAtEnd=ON"]
    receipt = command(args, data)
    match = re.search(r"request id is (\S+)", receipt)
    return {"job_id": match.group(1) if match else None, "message": receipt or "Submitted to CUPS."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
