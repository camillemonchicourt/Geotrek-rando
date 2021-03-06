import os
import re

from django.conf import settings
from django.core.management.base import BaseCommand
from landez import TilesManager
from landez.sources import DownloadError
from optparse import make_option
from urllib2 import unquote
from zipfile import ZipFile

from rando import logger
from rando.core.models import Settings
from rando.trekking.models import Trek, POIs
from rando.flatpages.models import FlatPage
from rando.mobile import mobile_settings


class ZipTilesBuilder(object):
    def __init__(self, filepath, **builder_args):
        self.zipfile = ZipFile(filepath, 'w')
        self.tm = TilesManager(**builder_args)
        self.tiles = set()

    def add_coverage(self, bbox, zoomlevels):
        self.tiles |= set(self.tm.tileslist(bbox, zoomlevels))

    def run(self):
        for tile in self.tiles:
            name = '{0}/{1}/{2}.png'.format(*tile)
            try:
                data = self.tm.tile(tile)
            except DownloadError:
                logger.warning("Failed to download tile %s" % name)
            else:
                self.zipfile.writestr(name, data)
        self.zipfile.close()


def format_from_url(url):
    """
    Try to guess the tile mime type from the tiles URL.
    Should work with basic stuff like `http://osm.org/{z}/{x}/{y}.png`
    or funky stuff like WMTS (`http://server/wmts?LAYER=...FORMAT=image/jpeg...)
    """
    m = re.search(r'FORMAT=([a-zA-Z/]+)&', url)
    if m:
        return m.group(1)
    return url.rsplit('.')[-1]


def remove_file(path):
    try:
        os.remove(path)
    except OSError:
        pass


class Command(BaseCommand):
    help = "Build data (tiles, json, media) for mobile application"
    option_list = BaseCommand.option_list + (
        make_option('-t', '--no-tiles',
            action='store_true',
            dest='no_tiles',
            default=False,
            help='Do not generate tiles files'),
    )

    def execute(self, *args, **options):

        self.site_url = args[0] if len(args) > 0 else ''

        self.output_folder = os.path.join(settings.INPUT_DATA_ROOT, 'tiles')
        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)

        self.main_tiles_url = None
        self.detail_tiles_url = None
        for tiles_layer in settings.LEAFLET_CONFIG['TILES']:
            if tiles_layer[0] == 'main':
                self.main_tiles_url = tiles_layer[1]
            if tiles_layer[0] == 'detail':
                self.detail_tiles_url = tiles_layer[1]

        self.builder_args = {
            'tiles_headers': {"Referer": self.site_url},
            'ignore_errors': True,
        }

        if not options['no_tiles']:
            self._build_global_tiles()
            for trek in Trek.objects.filter(language=settings.LANGUAGE_CODE).all():
                self._build_trek_tiles(trek)

        server_settings = Settings.objects.all()
        for language in server_settings.languages.available:
            self._build_ressources(language)

        logger.info('Done.')

    def _build_ressources(self, language):
        logger.info("Build ressources file %s..." % language)

        output_folder = os.path.join(settings.INPUT_DATA_ROOT, language, 'api/trek')
        print output_folder
        if not os.path.exists(output_folder):
            print 'mkdir', output_folder
            os.makedirs(output_folder)
        zipfilename = os.path.join(output_folder, 'trek.zip')
        zipfile = ZipFile(zipfilename, 'w')

        treks = Trek.objects.filter(language=language)
        media = set()

        zipfile.write(treks.fullpath, 'trek.geojson')

        for trek in treks.all():
            arcname = os.path.join('trek/{trek.pk}/pois.geojson'.format(trek=trek))
            zipfile.write(trek.pois.fullpath, arcname)
            url = trek.properties.altimetric_profile.replace('.json', '.svg')
            fullpath = os.path.join(settings.INPUT_DATA_ROOT, url.lstrip('/'))
            arcname = os.path.join('trek/{trek.pk}/profile.svg'.format(trek=trek))
            zipfile.write(fullpath, arcname)
            trek_dest = 'trek/{trek.pk}'.format(trek=trek)
            for picture in trek.properties.pictures:
                media.add((picture['url'], trek_dest))
            for desk in trek.properties.information_desks:
                media.add((desk['photo_url'], trek_dest))
            for attr in ('usages', 'themes', 'networks'):
                for item in trek.properties.get(attr):
                    media.add((item['pictogram'], 'trek/pictogram'))
            media.add((trek.properties.difficulty['pictogram'], 'trek/pictogram'))
            for poi in trek.pois.all():
                poi_dest = 'poi/{poi.pk}'.format(poi=poi)
                for picture in poi.properties.pictures:
                    media.add((picture['url'], poi_dest))
                media.add((poi.properties.thumbnail, poi_dest))
                media.add((poi.properties.type['pictogram'], 'poi/pictogram'))

        pages_json = FlatPage.objects.filter(language=language).json
        zipfile.writestr('staticpages/pages.json', pages_json)
        for page in FlatPage.objects.filter(language=language).all():
            for item in page.parse_media():
                media.add((item['url'], 'staticpages/images'))

        for url, dest in media:
            url = unquote(url).lstrip('/')
            fullpath = os.path.join(settings.INPUT_DATA_ROOT, url)
            arcname = os.path.join(dest, os.path.basename(url))
            zipfile.write(fullpath, arcname)

        zipfile.close()
        logger.info('%s done.' % zipfilename)

    def _build_global_tiles(self):
        """ Creates a tiles file on the global extent.
        Builds a temporary file and overwrites the existing one on success.
        """
        self.builder_args['tiles_url'] = self.main_tiles_url
        self.builder_args['tile_format'] = format_from_url(self.main_tiles_url)

        server_settings = Settings.objects.all()
        global_extent = server_settings.map.extent

        logger.info("Global extent is %s" % global_extent)
        global_file = os.path.join(self.output_folder, 'global.zip')
        tmp_gobal_file = global_file + '.tmp'

        logger.info("Build global tiles file...")
        tiles = ZipTilesBuilder(filepath=tmp_gobal_file, **self.builder_args)
        tiles.add_coverage(bbox=global_extent,
                           zoomlevels=mobile_settings.TILES_GLOBAL_ZOOMS)
        tiles.run()
        remove_file(global_file)
        os.rename(tmp_gobal_file, global_file)
        logger.info('%s done.' % global_file)

    def _build_trek_tiles(self, trek):
        """ Creates a tiles file for the specified Trek object.
        Builds a temporary file and overwrites the existing one on success.
        """
        self.builder_args['tiles_url'] = self.detail_tiles_url
        self.builder_args['tile_format'] = format_from_url(self.detail_tiles_url)

        logger.info("Build tiles file for trek '%s'..." % trek.properties.name)
        trek_file = os.path.join(self.output_folder, 'trek-%s.zip' % trek.id)
        tmp_trek_file = trek_file + '.tmp'

        coords = trek.geometry.coordinates
        self._build_tiles_along_coords(tmp_trek_file, coords)

        remove_file(trek_file)
        os.rename(tmp_trek_file, trek_file)
        logger.info('%s done.' % trek_file)

    def _build_tiles_along_coords(self, filepath, coords):
        """ For each point of the specified coordinates, it covers an area
        with a small radius on high zoom levels, and large radius on lower zoom
        levels.
        """
        def _radius2bbox(lng, lat, radius):
            return (lng - radius, lat - radius,
                    lng + radius, lat + radius)

        tiles = ZipTilesBuilder(filepath=filepath, **self.builder_args)

        for (lng, lat) in coords:
            large = _radius2bbox(lng, lat, mobile_settings.TILES_RADIUS_LARGE)
            small = _radius2bbox(lng, lat, mobile_settings.TILES_RADIUS_SMALL)
            tiles.add_coverage(bbox=large, zoomlevels=mobile_settings.TILES_LOW_ZOOMS)
            tiles.add_coverage(bbox=small, zoomlevels=mobile_settings.TILES_HIGH_ZOOMS)

        tiles.run()
