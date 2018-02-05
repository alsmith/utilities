#!/usr/bin/python

import argparse
import cherrypy
import datetime
import json
import logging
import os
import socket
import sys
import time

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
import helpers

class Root():
    favicon_ico = None

class API():
    class Config():
        def __init__(self, api):
            self.api = api
            self.PUT = helpers.notImplemented
            self.POST = helpers.notImplemented
            self.DELETE = helpers.notImplemented

        @cherrypy.tools.json_out()
        def GET(self):
            return self.api.getConfig()

    class Data():
        def __init__(self, api):
            self.api = api
            self.PUT = helpers.notImplemented
            self.DELETE = helpers.notImplemented

        @cherrypy.tools.json_out(handler=helpers.dumper)
        def GET(self):
            (user, readonly) = helpers.authorisedUser()
            if not user or readonly:
                raise cherrypy.HTTPError(403)

            rc = {'history': [], 'prediction': {}}
            last = {}
            for utility in self.api.databaseColumns(updateOnly=False, includeSumColumns=True):
                rc['history'].append([])
                last[utility] = None

            with helpers.DatabaseCursor() as cursor:
                cursor.execute('SELECT %s FROM utilities ORDER BY timestamp ASC' % ', '.join(['timestamp']+self.api.databaseColumns(updateOnly=False)))
                for row in cursor:
                    column = 0
                    for utility in self.api.databaseColumns(updateOnly=False, includeSumColumns=True):
                        utilityConfig = self.api.getUtilityConfig(utility)
                        if utilityConfig['sum']:
                            if len(filter(lambda u: row[u] is not None, utilityConfig['sum'])) == len(utilityConfig['sum']):
                                row[utility] = sum(map(lambda u: row[u], utilityConfig['sum']))
                            else:
                                row[utility] = None

                        if last[utility] and row[utility]:
                            if utilityConfig['raw']:
                                value = row[utility]
                            else:
                                value = (row[utility]-last[utility]['value']) / (row['timestamp'] - last[utility]['timestamp']).total_seconds()*86400

                            value = value * utilityConfig['scale']
                            value = value + utilityConfig['adjust']
                            if utilityConfig['floor'] is not None and value < utilityConfig['floor']:
                                value = utilityConfig['floor']

                            rc['history'][column].append([row['timestamp'], value])

                        if row[utility]:
                            last[utility] = {'timestamp': row['timestamp'], 'value': row[utility]}
                        column += 1
                column = 0
                for utility in self.api.databaseColumns(updateOnly=False):
                    if len(rc['history'][column]) >= 2:
                        dailyConsumption = rc['history'][column][-1][1]
                        daysElapsed = (datetime.datetime.now() - rc['history'][column][-1][0]).total_seconds()/86400
                        rc['prediction'][utility] = last[utility]['value'] + dailyConsumption * daysElapsed
                    column += 1
            return rc

        @cherrypy.tools.json_in()
        @cherrypy.tools.json_out()
        def POST(self):
            (user, readonly) = helpers.authorisedUser()
            if not user or readonly:
                raise cherrypy.HTTPError(403)

            data = cherrypy.request.json

            if set(data.keys()) != set(self.api.databaseColumns()):
                raise cherrypy.HTTPError(400)

            if len(filter(lambda c: data[c], self.api.databaseColumns())) == 0:
                return {}

            with helpers.DatabaseCursor() as cursor:
                cursor.execute('SELECT MAX(timestamp) AS lastTimestamp FROM utilities')
                rows = cursor.fetchall()
                if len(rows) == 1:
                    lastTimestamp = rows[0]['lastTimestamp']

                cursor.execute('INSERT INTO utilities (%s) VALUES(%s)' % (
                    ', '.join(self.api.databaseColumns()),
                    ', '.join(['%s' for c in self.api.databaseColumns()])),
                    map(lambda u: data[u] and data[u] or None, self.api.databaseColumns()))
                thisId = cursor.lastrowid()

                if cherrypy.config['computeAverageTemp'] and lastTimestamp:
                    cursor.execute('SELECT MAX(timestamp) AS thisTimestamp FROM utilities')
                    rows = cursor.fetchall()
                    thisTimestamp = rows[0]['thisTimestamp']

                    cursor.execute('SELECT AVG(numericValue) AS avg FROM buderusData WHERE keyId = (SELECT id FROM buderusKeys WHERE name = %s) AND timestampId IN (SELECT id FROM buderusTimestamps WHERE timestamp >= %s AND timestamp < %s)', ('system.sensors.temperatures.outdoor_t1', lastTimestamp, thisTimestamp))
                    avg = cursor.fetchone()['avg']
                    cursor.execute('UPDATE utilities SET averageTemp = %s WHERE id = %s', (avg, thisId))
            return {}

    def __init__(self):
        self.config = self.Config(self)
        self.config.exposed = True
        self.data = self.Data(self)
        self.data.exposed = True

        self.configData = None
        self.configTimestamp = None

    def getConfig(self):
        lastModified = os.stat(cherrypy.config['configuration']).st_mtime
        if not self.configData or lastModified > self.configTimestamp:
            with open(cherrypy.config['configuration']) as f:
                self.configData = json.loads(f.read())
                self.configTimestamp = lastModified
        return self.configData

    def getUtilityConfig(self, utility):
        return filter(lambda u: u['name'] == utility, self.getConfig())[0]

    def databaseColumns(self, updateOnly=True, includeSumColumns=False):
        return map(lambda v: v['name'], filter(lambda u: not updateOnly or u['update'], filter(lambda s: not s['sum'] or includeSumColumns, self.getConfig())))

    @staticmethod
    def databaseParameters():
        return {'parameters': {'user':    cherrypy.config['database.user'],
                               'passwd':  cherrypy.config['database.password'],
                               'db':      cherrypy.config['database.name'],
                               'host':    cherrypy.config['database.host'],
                               'charset': cherrypy.config['database.charset']}}

    @staticmethod
    def assignDatabaseParameters(threadIndex):
        cherrypy.thread_data.db = API.databaseParameters()

def main():
    parser = argparse.ArgumentParser(usage='usage: %s' % os.path.basename(__file__))

    parser.add_argument('--foreground', action='store_true', help='Don\'t daemonize')
    parser.add_argument('--config', default=os.path.join(os.path.dirname(__file__), 'config.ini'), help='Path to config.ini')
    args = parser.parse_args()

    if not args.config:
        print 'config.ini file not specified'
        return 1

    if not args.foreground:
        cherrypy.process.plugins.Daemonizer(cherrypy.engine).subscribe()

    cherrypy.config.update(args.config)

    if cherrypy.config.get('syslog.server'):
        h = logging.handlers.SysLogHandler(address=(cherrypy.config['syslog.server'], socket.getservbyname('syslog', 'udp')))
        h.setLevel(logging.INFO)
        h.setFormatter(cherrypy._cplogging.logfmt)
        cherrypy.log.access_log.addHandler(h)

    if cherrypy.config.get('log.pid_file'):
        cherrypy.process.plugins.PIDFile(cherrypy.engine, cherrypy.config.get('log.pid_file')).subscribe()

    rootConfig = {'/': {'tools.staticdir.on': True,
                        'tools.staticdir.root': os.path.dirname(os.path.abspath(__file__)),
                        'tools.staticdir.dir': 'static',
                        'tools.staticdir.index': 'index.html',
                        'tools.gzip.mime_types': ['text/*', 'application/*'],
                        'tools.gzip.on': True,
                        'tools.proxy.on': True,
                        'tools.proxy.local': 'Host'}}
    apiConfig  = {'/': {'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
                        'tools.gzip.mime_types': ['text/*', 'application/*'],
                        'tools.gzip.on': True,
                        'tools.proxy.on': True,
                        'tools.proxy.local': 'Host'}}

    api = API()
    cherrypy.tree.mount(Root(), '/', config=rootConfig)
    cherrypy.tree.mount(api, '/api/utilities/1.0', config=apiConfig)

    cherrypy.engine.subscribe('start_thread', API.assignDatabaseParameters)
    cherrypy.engine.start()
    cherrypy.engine.block()

if __name__ == '__main__':
    sys.exit(main())

