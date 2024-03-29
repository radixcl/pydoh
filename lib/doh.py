import requests
import random
import dnslib
import re
from box import Box
from lib import globals
from urllib3.util import connection
import dns.resolver

import requests_cache
requests_cache.install_cache('cache', backend='memory')

def custom_dns_resolver(hostname, type='A'):
    """Resolve the hostname to an IP address"""
    nameservers = globals.config.service.initial_dns
    custom_resolver = dns.resolver.Resolver()
    custom_resolver.nameservers = nameservers
    answer = custom_resolver.query(hostname, type)

    return str(random.choice(answer))

_orig_create_connection = connection.create_connection
def patched_create_connection(address, *args, **kwargs):
    """Wrap urllib3's create_connection to resolve the name elsewhere"""
    # resolve hostname to an ip address; use your own
    # resolver here, as otherwise the system resolver will be used.
    host, port = address
    hostname = custom_dns_resolver(host)

    return _orig_create_connection((hostname, port), *args, **kwargs)
connection.create_connection = patched_create_connection


class DOH:
    """ main class to handle all our DoH requests """
    def __init__(self):
        #print(__name__, 'Initialized')
        self.current = 0
    
    def get_random_doh(self, domlist):
        return random.choice(domlist)
    
    def get_roundrobin_doh(self, urls):
        if self.current > len(urls):
            self.current = 0
        
    
        try:
            url = urls[self.current]
            self.current += 1
        except IndexError:
            url = urls[0]
            self.current = 0

        if (self.current > len(urls) - 1):
            # counter reset
            self.current = 0
        return url

    def get_domain_config(self, defaultcfg, wireframe):
        """ get specific domain configuration """

        dnsdata = dnslib.DNSRecord.parse(wireframe)
        dnsdomain = dnsdata.q.get_qname()

        for ruleset in globals.config.rules.match:
            if re.search(str(ruleset.domain), str(dnsdomain)):
                # domain config matches!
                return Box({**defaultcfg, **ruleset})

        return defaultcfg


    def query(self, wireframe):
        """ handle DNS query and forward it to DoH server """

        headers = {
            'content-type': 'application/dns-message'
        }

        dnsdata = dnslib.DNSRecord.parse(wireframe)
        dnsdomain = dnsdata.q.get_qname()
        qtype = dnslib.QTYPE.get(k=dnsdata.q.qtype)

        print(f"Handling query: ({qtype}) {dnsdomain}")

        retval = None
        domconfig = self.get_domain_config(globals.config.default, wireframe)

        if 'static' in domconfig:
            # handle "static" domain configuration

            if qtype in domconfig.static:
                # reply for static configured domain match
                d = dnsdata.reply()
                qanswer = domconfig.static[qtype]
                d.add_answer(*dnslib.RR.fromZone(f"{dnsdomain} 60 {qtype} {qanswer}"))

                d.header.id = dnsdata.header.id
                d.q.qtype = dnsdata.q.qtype
                d.header.qr = 1

                return d.pack()
           
            else:
                # return NXDOMAIN
                r = dnsdata.reply()
                r.header.rcode = dnslib.RCODE.NXDOMAIN
                return r.pack()

        for retries in range(0, domconfig.doh_max_retries):
            if domconfig.doh_url_select == "random":
                url = self.get_random_doh(domconfig.doh_urls)
            elif domconfig.doh_url_select == "roundrobin":
                url = self.get_roundrobin_doh(domconfig.doh_urls)
            else:
                print("Error, no DOH url select method")
                r = dnsdata.reply()
                r.header.rcode = dnslib.RCODE.NXDOMAIN
                return r.pack()

            print("Using", url)

            try:
                r = requests.post(url, headers=headers, data=wireframe, stream=True, verify=globals.config.service.check_doh_ssl)
                assert r.status_code == 200
                retval = r.content
                break

            except Exception as ex:
                print("Error requesting DOH: ", ex)
                continue

        return retval
