#!/usr/bin/env python3
# coding: utf-8

# Quite simple DNS to DNS Over HTTPS proxy daemon.

import argparse
import os
import sys
import threading
import dnslib
import socket
import requests
import random
import json

if os.name == 'posix':
    import pwd
    import grp


class DOH:
    def __init__(self):
        #print(__name__, 'Initialized')
        pass
    
    def get_doh_url(self):
        return random.choice(config.get('doh_urls'))

    def query(self, wireframe):
        headers = {
            'content-type': 'application/dns-message'
        }

        url = self.get_doh_url()
        #print("Using", url)

        try:
            r = requests.post(url, headers=headers, data=wireframe, stream=True)
            assert r.status_code == 200
        except Exception as ex:
            print("Error requesting DOH: ", ex)
            return None

        return r.content


class UDPThread(threading.Thread):
    def __init__(self, client, msg, sock):
        threading.Thread.__init__(self)
        self.client = client
        self.msg = msg
        self.DOH = DOH()
        self.sock = sock

    def run(self):
        dnsq = dnslib.DNSRecord.parse(self.msg)
        resp = self.DOH.query(self.msg)
        if resp is None:
            return
        self.sock.sendto(resp, self.client)


def main():
    global config

    curpath = os.path.basename(os.path.dirname(__file__))
    if curpath == '' or curpath is None:
        curpath = '.'

    parser = argparse.ArgumentParser()
    parser.add_argument('-f', action='store',
                    dest='conffile',
                    help='Specifies config file',
                    default='%s/config.json' % curpath,
                    type=str)

    parser.add_argument('-d', action='store_true',
                    dest='daemon',
                    help='Fork process into background (not available on Windows)',
                    default=False)

    args = parser.parse_args()

    # load config
    try:
        with open(args.conffile) as f:
            config = json.load(f)
    except Exception as ex:
        print("ERROR: Could not read config file:", ex)
        sys.exit(1)

    if ((config.get('doh_urls', None) is None)
    or (type(config.get('doh_urls', None)) == list and len(config.get('doh_urls', None)) < 1)
    or (type(config.get('doh_urls', None)) != list)):
        print("ERROR: No doh_urls defined in config!")
        sys.exit(2)

    # fork into background
    if os.name == 'posix' and args.daemon:
        p = os.fork()
        if p > 0:
            sys.exit(0)
        elif p == -1:
            print("ERROR: Couldn't fork()!")
            sys.exit(1)

    sockServer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sockServer.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sockServer.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except AttributeError:
        pass # Some systems don't support SO_REUSEPORT

    try:
        sockServer.bind((config.get('listen_address', '0.0.0.0'), config.get('listen_port', 53)))
        print("Listening on:", config.get('listen_address', '0.0.0.0'), config.get('listen_port', 53))
    except Exception as ex:
        print("Couldn't listen on %s:%s\n%s" % (config.get('listen_address', '0.0.0.0'), config.get('listen_port', 53), str(ex)))
        sys.exit(1)
    
    drop_privs()
    
    while True:
        msg, client = sockServer.recvfrom(1024)
        
        newthread = UDPThread(client, msg, sockServer)
        newthread.setDaemon(True)
        newthread.start()


def drop_privs(uid_name=None, gid_name=None):
    if os.name != 'posix' or os.getuid() != 0:
        return

    if uid_name is None:
        uid_name = config.get('runas_user', 'nobody')
    if gid_name is None:
        gid_name = config.get('runas_group', 'nobody')

    print("Dropping privileges...")

    running_uid = pwd.getpwnam(uid_name).pw_uid
    running_gid = grp.getgrnam(gid_name).gr_gid

    os.setgroups([])

    os.setgid(running_gid)
    os.setuid(running_uid)

    os.umask(0o77)


if __name__ == '__main__':
    config = None
    main()
