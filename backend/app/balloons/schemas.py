from typing import Literal, TypeAlias


BBox: TypeAlias = tuple[float, float, float, float]
PdfPoint: TypeAlias = tuple[float, float]
PlacementStatus: TypeAlias = Literal["placed", "manual_required"]
