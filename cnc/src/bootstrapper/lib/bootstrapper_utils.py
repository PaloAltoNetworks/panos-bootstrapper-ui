import requests


class BootstrapperClient():

    _bootstrapper_host = ''
    _bootstrapper_port = 5000

    @property
    def bootstrapper_host(self):
        return self._bootstrapper_host

    @bootstrapper_host.setter
    def bootstrapper_host(self, value):
        self._bootstrapper_host = value

    @property
    def bootstrapper_port(self):
        return self._bootstrapper_port

    @bootstrapper_port.setter
    def bootstrapper_port(self, value):
        self._bootstrapper_port = value

    def __init__(self, host, port):
        self._bootstrapper_host = host
        self._bootstrapper_port = port

    def list_bootstrap_templates(self):

        template_list = list()
        url = 'http://%s:%s/list_templates' % (self.bootstrapper_host, self.bootstrapper_port)
        res = requests.get(url)
        print(res)
        return template_list

