'use strict';

var controllers = require('./controllers');

function globalFiltersDirective() {
    return {
        restrict: 'E',
        replace: true,
        scope: true,
        template: require('./templates/global-filters.html'),
        controller: controllers.GlobalFiltersController
    };
}

module.exports = {
    globalFiltersDirective: globalFiltersDirective
};