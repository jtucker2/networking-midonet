#
# Copyright 2016 Midokura SARL
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""Utility functions used for REST APIs"""


from __future__ import print_function

from ConfigParser import SafeConfigParser
import os
from oslo_serialization import jsonutils
import requests

from rally.common import logging
from rally.task import scenario

LOG = logging.getLogger(__name__)


class RequestScenario(scenario.Scenario):
    """Base class for Request scenarios"""

    @staticmethod
    def get_credentials():
        """Retrieves credentials to connect to neutron from 'midonetrc' file"""
        try:
            parser = SafeConfigParser()
            parser.read(os.path.join(os.path.expanduser('~stack'),
                                     '.midonetrc'))
            return parser
        except Exception as e:
            raise e

    @staticmethod
    def _get_token():
        """Generates authentication token

        This method executes login API of MidoNet and generates authentication
        token. This token is generated by executing /login API providing
        base64 value of credentials
        """

        import base64
        auth_token = None
        creds = RequestScenario.get_credentials()
        credentials = base64.standard_b64encode(creds.get('cli', 'username') +
                                                ":" +
                                                creds.get('cli', 'password'))

        header = {'X-Auth-Project': creds.get('cli', 'project_id'),
                  'Authorization': 'Basic %s' % credentials}
        # Execute login API
        response = requests.request("POST", creds.get('cli', 'api_url') +
                                    "/login", headers=header)
        if response.status_code == requests.codes.ok:
            auth_token = response.json()['key']
        else:
            LOG.error("Error for the operation is: %s" % response.text)
            raise ValueError("Expected HTTP request code is 200 actual %s"
                             % response.status_code)
        return auth_token

    def request_get_all(self, api, header):
        """Executes GET request to get all values for a resource"""

        creds = RequestScenario.get_credentials()
        url = creds.get('cli', 'api_url') + '/' + api
        response = requests.request("GET", url, headers=header)
        if response.status_code == requests.codes.ok:
            LOG.debug("Resource retrieval is successful for: '%s'" % api)
            return response.json()
        elif response.status_code == 401:
            return response.status_code
        else:
            LOG.error("Error for the operation is: %s" % response.text)
            raise ValueError("Expected HTTP request code is 200 actual %s"
                             % response.status_code)

    def request_get_resource(self, api, header):
        """Executes GET request to get information of a particular resource"""

        creds = RequestScenario.get_credentials()
        url = creds.get('cli', 'api_url') + '/' + api
        response = requests.request("GET", url, headers=header)
        if response.status_code == requests.codes.ok:
            LOG.debug("Resource retrieval by ID is successful for: '%s'" % api)
            return response.status_code
        elif response.status_code == 401:
            return response.status_code
        else:
            LOG.error("Error for the operation is: %s" % response.text)
            raise ValueError("Expected HTTP request code is 200 actual %s"
                             % response.status_code)

    def request_post(self, api, header, payload):
        """Executes POST request to create a resource"""

        creds = RequestScenario.get_credentials()
        url = creds.get('cli', 'api_url') + '/' + api
        response = requests.request("POST",
                                    url,
                                    data=jsonutils.dumps(payload),
                                    headers=header)
        if response.status_code == 201:
            LOG.debug("Resource creation successful for: '%s'" % api)
            return response.status_code
        elif response.status_code == 401:
            return response.status_code
        else:
            LOG.error("Error for the operation is: %s" % response.text)
            raise ValueError("Expected HTTP request code is 201 actual %s"
                             % response.status_code)

    def request_put(self, api, header, payload):
        """Executes PUT request to update an existing resource"""

        creds = RequestScenario.get_credentials()
        url = creds.get('cli', 'api_url') + '/' + api
        response = requests.request("PUT",
                                    url,
                                    data=jsonutils.dumps(payload),
                                    headers=header)
        if response.status_code == 204:
            LOG.debug("Resource '%s' updated successfully" % api)
        elif response.status_code == 401:
            return response.status_code
        else:
            LOG.error("Error for the operation is: %s" % response.text)
            raise ValueError("Expected HTTP request code is 204 actual %s"
                             % response.status_code)

    def request_delete(self, api, header):
        """Executes DELETE request to delete a resource"""

        creds = RequestScenario.get_credentials()
        url = creds.get('cli', 'api_url') + '/' + api
        response = requests.request("DELETE", url, headers=header)
        if response.status_code == 204:
            LOG.debug("Resource delete successful for: '%s'" % api)
        elif response.status_code == 401:
            return response.status_code
        else:
            LOG.error("Error for the operation is: %s" % response.text)
            raise ValueError("Expected HTTP request code is 204 actual %s"
                             % response.status_code)