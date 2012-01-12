#!/bin/sh

# Script to be removed after final impl...

pep8 -r nova/api/occi/ nova/tests/api/occi/

pylint -i yes -r no nova/api/occi/ nova/tests/api/occi/

nosetests --with-coverage --cover-package=nova.api.occi --cover-erase --cover-html nova/tests/api/occi/
