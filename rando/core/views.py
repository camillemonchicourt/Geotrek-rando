import os
import mimetypes

from django.conf import settings
from django.views.static import serve as static_serve


def fileserve(request, path):
    """
    Rewrite URLs to use current language as folder root prefix.
    TODO: Could be done with ``mod_rewrite`` at deployment.
    """

    if '.geojson' not in mimetypes.types_map:
        mimetypes.add_type('application/json', '.geojson')
    if '.gpx' not in mimetypes.types_map:
        mimetypes.add_type('application/gpx+xml', '.gpx')
    if '.kml' not in mimetypes.types_map:
        mimetypes.add_type('application/vnd.google-earth.kml+xml', '.kml')
    if '.kmz' not in mimetypes.types_map:
        mimetypes.add_type('application/vnd.google-earth.kmz', '.kmz')

    path = path[1:] if path.startswith('/') else path
    if not os.path.exists(os.path.join(settings.INPUT_DATA_ROOT, path)):
        path = os.path.join(request.LANGUAGE_CODE, path)
    return static_serve(request, path, document_root=settings.INPUT_DATA_ROOT)
