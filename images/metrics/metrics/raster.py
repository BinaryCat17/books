from typing import Any


def open_pdf(path: str) -> Any:
    import pymupdf

    return pymupdf.open(path)


def render(page: Any, dpi: float, clip: Any = None) -> Any:
    return page.get_pixmap(dpi=int(dpi), clip=clip)
