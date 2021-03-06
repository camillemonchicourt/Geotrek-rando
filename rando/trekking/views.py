from django.http import Http404
from django.conf import settings
from django.views.generic import TemplateView, DetailView
from django.utils.translation import ugettext_lazy as _
from djpjax import PJAXResponseMixin

from rando import logger
from rando.core.utils import locale_redirect
from .models import Trek


class HomeView(PJAXResponseMixin, TemplateView):

    template_name = 'trekking/home.html'
    pjax_template_name = "trekking/_home_panel.html"

    def get_context_data(self, **kwargs):
        lang = self.request.LANGUAGE_CODE
        alltreks = Trek.objects.filter(language=lang).all()
        if len(alltreks) == 0:
            logger.warn("No trek found for lang %s." % lang)

        context = super(HomeView, self).get_context_data(**kwargs)
        self._add_choices_values(alltreks, context)

        duration_levels = []
        for (label, duration) in settings.FILTER_DURATION_VALUES:
            duration_levels.append({'label': _(label), 'value': duration})

        altitude_levels = []
        for i, ascent in enumerate(settings.FILTER_ASCENT_VALUES):
            if i == 0:
                label = _('< %sm') % ascent
            elif i == len(settings.FILTER_ASCENT_VALUES) -1:
                label = _('> %sm') % ascent
            else:
                label = _('%sm') % ascent
            altitude_levels.append({'label': label, 'value': ascent})

        all_difficulties = {}
        for trek in alltreks:
            if not trek.properties.difficulty:
                continue
            did = trek.properties.difficulty.id
            dlabel = trek.properties.difficulty.label
            all_difficulties[did] = {'label': dlabel, 'value': did}

        difficulty_levels = sorted(all_difficulties.values(),
                                   key=lambda d: d['value'])

        context['difficulty_levels'] = difficulty_levels
        context['duration_levels'] = duration_levels
        context['altitude_levels'] = altitude_levels

        return context

    def _add_choices_values(self, alltreks, context):
        # Build list of distinct attributes
        allthemes = {}
        allusages = {}
        alldistricts = {}
        allcities = {}
        allroutes = {}
        for trek in alltreks:
            for district in trek.properties.districts:
                alldistricts[district.id] = district
            for city in trek.properties.cities:
                allcities[city.code] = city
            for usage in trek.properties.usages:
                allusages[usage.id] = usage
            for theme in trek.properties.themes:
                allthemes[theme.id] = theme
            route = trek.properties.route
            if route:
                allroutes[route.id] = route

        allthemes = sorted(allthemes.values(), key=lambda o: o.label)
        allusages = sorted(allusages.values(), key=lambda o: o.label)
        alldistricts = sorted(alldistricts.values(), key=lambda o: o.name)
        allcities = sorted(allcities.values(), key=lambda o: o.name)
        allroutes = sorted(allroutes.values(), key=lambda o: o.label)

        context.update({
            'treks': alltreks,
            'themes': allthemes,
            'usages': allusages,
            'districts': alldistricts,
            'cities': allcities,
            'routes': allroutes,
        })


class BaseTrekView(DetailView):

    def get_object(self):
        slug = self.kwargs.get(self.slug_url_kwarg, None)
        lang = self.request.LANGUAGE_CODE
        for trek in Trek.objects.filter(language=lang).all():
            if trek.properties.slug == slug:
                return trek
        raise Http404


class TrekView(PJAXResponseMixin, BaseTrekView):

    template_name = 'trekking/detail.html'
    pjax_template_name = "trekking/_detail_panel.html"

    def get_context_data(self, **kwargs):
        obj = self.get_object()
        context = super(TrekView, self).get_context_data(**kwargs)
        context['trek'] = obj
        context['thumbnail'] = self.request.build_absolute_uri(obj.properties.thumbnail)

        context['trek_has_related'] = (len(obj.properties.relationships_departure) > 0 or
                                       len(obj.properties.relationships_edge) > 0 or
                                       len(obj.properties.relationships_circuit))

        pois = obj.pois.all()
        context['pois'] = pois

        # Merge pictures of trek and POIs
        all_pictures = obj.properties.pictures
        for poi in pois:
            all_pictures.extend(poi.properties.pictures)
        context['all_pictures'] = all_pictures

        context['park_center_warning'] = settings.PARK_CENTER_WARNING.get(self.request.LANGUAGE_CODE,
                                                                          settings.PARK_CENTER_WARNING.get(settings.LANGUAGE_CODE, ''))
        context['park_center_link'] = settings.PARK_CENTER_LINK.get(self.request.LANGUAGE_CODE,
                                                                    settings.PARK_CENTER_LINK.get(settings.LANGUAGE_CODE, ''))

        return context


def trek_redirect(request, pk):
    lang = request.LANGUAGE_CODE
    treks = Trek.objects.filter(language=lang).all()
    for trek in treks:
        if trek.pk == int(pk):
            return locale_redirect('trekking:detail',
                                   kwargs={'slug': trek.properties.slug},
                                   locale=lang)
    raise Http404
