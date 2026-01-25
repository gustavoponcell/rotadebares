import os
from typing import List, Tuple

from loguru import logger

from models import POI

OVERTURE_S3_PATH = "s3://overturemaps-us-west-2/release/latest/theme=places/type=place/*"
OVERTURE_DEFAULT_LIMIT = 300


def is_overture_enabled() -> bool:
    """Retorna True quando a flag ENABLE_OVERTURE está ativa."""

    return os.getenv("ENABLE_OVERTURE", "").lower() in {"1", "true", "yes", "on"}


def fetch_overture_places(
    bbox: Tuple[float, float, float, float],
    limit: int = OVERTURE_DEFAULT_LIMIT,
) -> List[POI]:
    """Busca lugares do Overture Places dentro de uma bbox.

    Parameters
    ----------
    bbox:
        (min_lon, min_lat, max_lon, max_lat).
    limit:
        Número máximo de registros retornados.
    """

    import duckdb

    min_lon, min_lat, max_lon, max_lat = bbox
    conn = duckdb.connect(database=":memory:")
    try:
        conn.execute("INSTALL httpfs;")
        conn.execute("LOAD httpfs;")
        conn.execute("INSTALL spatial;")
        conn.execute("LOAD spatial;")
        conn.execute("SET s3_region='us-west-2';")
        query = """
            SELECT
                id,
                names.primary AS name,
                categories.primary AS category,
                ST_X(ST_Centroid(geometry)) AS lon,
                ST_Y(ST_Centroid(geometry)) AS lat
            FROM read_parquet(?)
            WHERE geometry IS NOT NULL
              AND ST_Intersects(geometry, ST_MakeEnvelope(?, ?, ?, ?))
            LIMIT ?
        """
        rows = conn.execute(
            query,
            [OVERTURE_S3_PATH, min_lon, min_lat, max_lon, max_lat, limit],
        ).fetchall()
    finally:
        conn.close()

    pois: List[POI] = []
    for overture_id, name, category, lon, lat in rows:
        if lat is None or lon is None or not name or not name.strip():
            continue
        poi = POI(
            poi_id=f"overture:{overture_id}",
            name=name,
            category=category,
            lat=float(lat),
            lon=float(lon),
            source="overture",
            raw_tags={"category": category, "names": name},
            extra={"overture_id": str(overture_id), "category_raw": category},
        )
        pois.append(poi)
    logger.info("Overture: %s registros retornados na bbox.", len(pois))
    return pois


__all__ = ["fetch_overture_places", "is_overture_enabled"]
