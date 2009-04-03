#!/usr/bin/env python
###############################################################################
# master.py - a master server for Tremulous
# Copyright (c) 2009 Ben Millwood
#
# Thanks to Mathieu Olivier, who wrote the original master in C
# (this project shares none of his code, but used it as a reference)
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 59 Temple
# Place, Suite 330, Boston, MA  02111-1307  USA
###############################################################################
"""The Tremulous Master Server
Requires Python 2.6

Protocol for this is pretty simple.
Accepted incoming messages:
    'heartbeat <game>\\n'
        <game> is ignored for the time being (it's always Tremulous in any
        case). It's a request from a server for the master to start tracking it
        and reporting it to clients. Usually the master will verify the server
        before accepting it into the server list.
    'getservers <protocol> [empty] [full]'
        A request from the client to send the list of servers.
"""

from random import choice, randint
from socket import (socket, error as sockerr, has_ipv6, inet_pton,
                   AF_INET, AF_INET6, SOCK_DGRAM, IPPROTO_UDP)
from select import select
from sys import exit, stdout, stderr
from time import time, strftime

import config

inSocks, outSocks = {}, {}

pending = {}
servers = []

( # Log levels
    LOG_ERROR,
    LOG_PRINT,
    LOG_VERBOSE,
    LOG_DEBUG
) = range(4)

def log(level, *args):
    if level in (LOG_ERROR, LOG_DEBUG):
        f = stderr
    else:
        f = stdout
    f.write(strftime('%T ') + ' '.join(map(str, args)))

class Server(object):
    NEW, CHALLENGED, CONFIRMED = range(3)
    def __init__(self, sock, addr):
        self.addr = addr
        self.sock = outSocks[sock.family]
        self.state = self.NEW
        self.lastactive = 0

    def timeout(self):
        if self.state == self.CONFIRMED:
            return (time() - self.lastactive > config.SERVER_TIMEOUT)
        return (time() - self.lastactive > config.CHALLENGE_TIMEOUT)

    def heartbeat(self, data):
        self.challenge = challenge()
        self.sock.sendto('\xff\xff\xff\xffgetinfo %s' % (self.challenge,),
            self.addr)
        if self.state == self.NEW:
            self.challengetime = time()
            self.state = self.CHALLENGED
        log(LOG_VERBOSE, 'Sent challenge\n')

    def respond(self, data):
        if data.startswith('infoResponse'):
            return self.infoResponse(data)

    def infoResponse(self, data):
        if (self.state == self.CHALLENGED and
                time() - self.challengetime > config.CHALLENGE_TIMEOUT):
            log(LOG_VERBOSE, 'Challenge response rejected: too late\n')
            return False
        infostring = data.split(None, 1)[1]
        info = parseinfo(infostring)
        try:
            if info['challenge'] != self.challenge:
                return False
            self.protocol = info['protocol']
            self.empty = (info['clients'] == '0')
            self.full = (info['clients'] == info['sv_maxclients'])
        except KeyError, ex:
            log(LOG_VERBOSE, 'Server info key missing: %s\n' % (ex,))
            return False
        self.state = self.CONFIRMED
        self.lastactive = time()
        log(LOG_DEBUG, 'Last active time updated for %s:%s\n' % self.addr)
        return True

def prune_timeouts(list):
    for server in filter(lambda s: s.timeout(), list):
        log(LOG_VERBOSE, 'Server dropped due to %ss inactivity: %s:%s\n' %
                (time() - server.lastactive, server.addr[0], server.addr[1]))
        list.remove(server)

def parseinfo(infostring):
    info = dict()
    infostring = infostring.lstrip('\\')
    while True:
        bits = infostring.split('\\', 2)
        try:
            info[bits[0]] = bits[1]
            infostring = bits[2]
        except IndexError:
            break
    return info

def challenge():
    """Returns a string of config.CHALLENGE_LENGTH characters, chosen from
    those greater than ' ' and less than or equal to '~' (i.e. isgraph)
    Semicolons, backslashes and quotes are precluded because the server won't
    put them in an infostring; forward slashes are not allowed because the
    server's parsing tools can recognise them as comments
    Percent symbols: these used to be disallowed, but subsequent to r1148 they
    should be okay. Any server older than that will translate them into '.'
    and therefore fail to match."""
    valid = [c for c in map(chr, range(0x21, 0x7f)) if c not in '\\;\"/']
    return ''.join([choice(valid) for _ in range(config.CHALLENGE_LENGTH)])

def heartbeat(sock, addr, data):
    s = Server(sock, addr)
    s.heartbeat(data)
    pending[addr] = s

def getservers(sock, addr, data):
    ext = data.startswith('getserversExt')
    start = '\xff\xff\xff\xffgetservers{0}Response'.format(
               'Ext' if ext else '')
    response = start
    end = '\\EOT\0\0\0'
    assert config.GSR_MAXLENGTH > len(response) + len(end)
    for server in servers:
        af = server.sock.family
        sep = '/' if af == AF_INET6 else '\\'
        add = (sep + inet_pton(af, server.addr[0]) +
               chr(server.addr[1] >> 8) + chr(server.addr[1] & 0xff))
        if len(response) + len(add) + len(end) > config.GSR_MAXLENGTH:
            response += end
            sock.sendto(response, addr)
            response = start

try:
    if config.bindaddr:
        inSocks[AF_INET] = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
        inSocks[AF_INET].bind((config.bindaddr, config.inPort))
        outSocks[AF_INET] = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
        outSocks[AF_INET].bind((config.bindaddr, config.outPort))
        log(LOG_PRINT, 'IPv4: Listening on', config.bindaddr,
                       'port', config.inPort)

    if config.bind6addr and has_ipv6:
        inSocks[AF_INET6] = socket(AF_INET6, SOCK_DGRAM, IPPROTO_UDP)
        inSocks[AF_INET6].bind((config.bind6addr, config.inPort))
        outSocks[AF_INET6] = socket(AF_INET6, SOCK_DGRAM, IPPROTO_UDP)
        outSocks[AF_INET6].bind((config.bind6addr, config.outPort))
        log(LOG_PRINT, 'IPv6: Listening on', config.bind6addr,
                       'port', config.inPort)

    if not inSocks and not outSocks:
        log(LOG_ERROR, 'Error: Not listening on any sockets, aborting\n')
        exit(1)
except sockerr, (errno, strerror):
    log(LOG_ERROR, 'Couldn\'t initialise sockets: %s\n' % (strerror,))
    raise

while True:
    (ready, _, _) = select(inSocks.values() + outSocks.values(), [], [])
    prune_timeouts(servers)
    for sock in inSocks.values():
        if sock in ready:
            (data, addr) = sock.recvfrom(2048)
            log(LOG_VERBOSE, 'Packet on sock from %s:%s\n' %
                (addr[0], addr[1]))
            if data[:4] != '\xff\xff\xff\xff':
                log(LOG_VERBOSE, '  rejected (no header)\n')
                continue
            data = data[4:]
            responses = [
                ('heartbeat', heartbeat),
                ('getservers', getservers),
                ('getserversExt', getservers)
            ]
            for (name, func) in responses:
                if data.startswith(name):
                    func(sock, addr, data)
                    break
            else:
                log(LOG_VERBOSE, '  unrecognised content: %r\n' % (data,))
    for sock in outSocks.values():
        if sock in ready:
            (data, addr) = sock.recvfrom(2048)
            log(LOG_VERBOSE, 'Packet on sock from %s:%d\n' % addr)
            if data[:4] != '\xff\xff\xff\xff':
                log(LOG_VERBOSE, '  rejected (no header)\n')
                continue
            data = data[4:]
            if addr not in pending.keys():
                log(LOG_VERBOSE, '  rejected (unsolicited)\n')
                continue
            if pending[addr].respond(data) and pending[addr] not in servers:
                servers.append(pending[addr])
                log(LOG_VERBOSE, 'Server confirmed: %s:%s\n' %
                    (addr[0], addr[1]))
            del pending[addr]
# vim: set expandtab ts=4 sw=4 :
