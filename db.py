# db.py
# Copyright (c) Ben Millwood 2009
# This file is part of the Tremulous Master server.

from contextlib import closing
from os import O_RDWR, O_CREAT
from tdb import Tdb
from time import asctime, gmtime

from config import log, LOG_VERBOSE, LOG_DEBUG

def log_client(addr, info):
    try:
        # TODO: check if flags are necessary
        with closing(Tdb('clientStats.tdb',
                         flags = O_RDWR|O_CREAT)) as database:
            try:
                version = info['version']
                renderer = info['renderer']
                if '\"' in version + renderer:
                    raise ValueError('Invalid character in info string')
            except KeyError, e:
                raise ValueError('Missing info key: ' + str(e))

            database[addr.host] = '"{0}" "{1}"'.format(version, renderer)

            log(LOG_VERBOSE, addr, 'Recorded client stat', sep = ': ')
    except ValueError, ex:
        log(LOG_PRINT, addr, 'Client not logged', ex, sep = ': ')

def log_gamestat(addr, data):
    with closing(Tdb('gameStats.tdb', flags = O_RDWR|O_CREAT)) as database:
        key = '{0} {1}'.format(addr.host, asctime(gmtime()))
        database[key] = data
