#!/usr/bin/env python3
# coding: utf-8

# Quite simple DNS to DNS Over HTTPS proxy daemon.

import argparse
import os
import sys
import threading
from typing import List
import dnslib
import socket

if os.name == 'posix':
    import pwd
    import grp

from lib import globals
from lib.doh import DOH
from lib import config as cnf


class UDPThread(threading.Thread):
    def __init__(self, client, msg, sock):
        threading.Thread.__init__(self)
        self.client = client
        self.msg = msg
        self.sock = sock

    def run(self):
        #dnsq = dnslib.DNSRecord.parse(self.msg)
        #print("DNSQ", dnsq)
        resp = globals.DOH.query(self.msg)
        if resp is None:
            return
        self.sock.sendto(resp, self.client)


def main():
    globals.DOH = DOH()

    curpath = os.path.basename(os.path.dirname(__file__))
    if curpath == '' or curpath is None:
        curpath = '.'

    parser = argparse.ArgumentParser()
    parser.add_argument('-f', action='store',
                    dest='conffile',
                    help='Specifies config file',
                    default='%s/config.yaml' % curpath,
                    type=str)

    parser.add_argument('-d', action='store_true',
                    dest='daemon',
                    help='Fork process into background (not available on Windows)',
                    default=False)

    args = parser.parse_args()

    # load config
    globals.config = cnf.load_config(args.conffile)

    if not hasattr(globals.config.default, "doh_urls") and type(globals.config.default.doh_urls) != list:
        print("ERROR: No doh_urls defined in default config!")
        sys.exit(2)

    # fork into background
    if os.name == 'posix' and args.daemon:
        p = os.fork()
        if p > 0:
            sys.exit(0)
        elif p == -1:
            print("ERROR: Couldn't fork()!")
            sys.exit(1)

    sock_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except AttributeError:
        pass # Some systems don't support SO_REUSEPORT

    try:
        sock_server.bind((globals.config.service.get('listen_address', '0.0.0.0'), globals.config.service.get('listen_port', 53)))
        print("Listening on:", globals.config.service.get('listen_address', '0.0.0.0'), globals.config.service.get('listen_port', 53))
    except Exception as ex:
        print("Couldn't listen on %s:%s\n%s" % (globals.config.service.get('listen_address', '0.0.0.0'), globals.config.service.get('listen_port', 53), str(ex)))
        sys.exit(1)
    
    drop_privs()
    
    while True:
        msg, client = sock_server.recvfrom(1024)
        
        newthread = UDPThread(client, msg, sock_server)
        newthread.setDaemon(True)
        newthread.start()


def drop_privs(uid_name=None, gid_name=None):
    if os.name != 'posix' or os.getuid() != 0:
        return

    if uid_name is None:
        uid_name = globals.config.service.get('runas_user', 'nobody')
    if gid_name is None:
        gid_name = globals.config.service.get('runas_group', 'nobody')

    print("Dropping privileges...")

    running_uid = pwd.getpwnam(uid_name).pw_uid
    running_gid = grp.getgrnam(gid_name).gr_gid

    os.setgroups([])

    os.setgid(running_gid)
    os.setuid(running_uid)

    os.umask(0o77)


if __name__ == '__main__':
    globals.config = None
    main()
