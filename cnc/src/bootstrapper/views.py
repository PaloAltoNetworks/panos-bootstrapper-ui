import json
import re
from base64 import urlsafe_b64encode

import requests
from django import forms
from django.contrib import messages
from django.shortcuts import render, HttpResponseRedirect, HttpResponse

from pan_cnc.lib import cnc_utils
from pan_cnc.lib import pan_utils
from pan_cnc.lib import snippet_utils
from pan_cnc.views import CNCBaseAuth, CNCBaseFormView


class BootstrapWorkflowView(CNCBaseAuth, CNCBaseFormView):
    snippet = 'bootstrapper-payload'
    header = 'Build Bootstrap Archive'
    title = 'Deployment Information'
    fields_to_render = ['hostname', 'include_panorama', 'deployment_type']

    def form_valid(self, form):
        if self.get_value_from_workflow('deployment_type', '') == 's3':
            return HttpResponseRedirect('cloud_auth')

        if self.get_value_from_workflow('include_panorama', 'no') == 'yes':
            return HttpResponseRedirect('step03')
        else:
            return HttpResponseRedirect('choose_bootstrap')


class DynamicContentView(BootstrapWorkflowView):
    title = 'Include Dynamic Content'
    fields_to_render = ['include_dynamic_content']

    def form_valid(self, form):
        if self.get_value_from_workflow('include_dynamic_content', 'no') == 'yes':
            return HttpResponseRedirect('download_content')
        else:
            return HttpResponseRedirect('complete')


class DownloadDynamicContentView(CNCBaseAuth, CNCBaseFormView):
    header = 'Build Bootstrap Archive'
    title = 'Dynamic Content Authentication'
    snippet = 'content_downloader'

    def form_valid(self, form):
        payload = self.render_snippet_template()

        # get the content_downloader host and port from the .panrc file, environrment, or default name lookup
        # docker-compose will host content_downloader under the 'content_downloader' domain name
        content_downloader_host = cnc_utils.get_config_value('CONTENT_DOWNLOADER_HOST', 'content_downloader')
        content_downloader_port = cnc_utils.get_config_value('CONTENT_DOWNLOADER_PORT', '5003')

        resp = requests.post(f'http://{content_downloader_host}:{content_downloader_port}/download_content',
                             json=json.loads(payload)
                             )

        print(f'Download returned: {resp.status_code}')
        if resp.status_code != 200:
            messages.add_message(self.request, messages.ERROR, f'Could not download dynamic content!')

        if 'Content-Disposition' in resp.headers:
            filename = resp.headers['Content-Disposition'].split('=')[1]
            messages.add_message(self.request, messages.INFO, f'Downloaded Dynamic Content file: {filename}')

        return HttpResponseRedirect('complete')


class GetCloudAuthView(BootstrapWorkflowView):
    title = 'Enter Cloud Auth Information'
    fields_to_render = []

    def generate_dynamic_form(self):
        deployment_type = self.get_value_from_workflow('deployment_type', '')
        if deployment_type == 's3':
            self.fields_to_render += ['aws_key', 'aws_secret', 'aws_location']

        return super().generate_dynamic_form()

    def form_valid(self, form):

        aws_location = self.get_value_from_workflow('aws_location', 'us-east-2')

        if aws_location == 'us-east-1':
            # fix for stupid aws api
            aws_location = ''
            self.save_value_to_workflow('aws_location', aws_location)

        if self.get_value_from_workflow('include_panorama', 'no') == 'yes':
            return HttpResponseRedirect('step03')
        else:
            return HttpResponseRedirect('choose_bootstrap')


class BootstrapStep03View(BootstrapWorkflowView):
    title = 'Configure Panorama Server'
    fields_to_render = ['TARGET_IP', 'TARGET_USERNAME', 'TARGET_PASSWORD']

    def form_valid(self, form):
        target_ip = self.get_value_from_workflow('TARGET_IP', '')
        target_username = self.get_value_from_workflow('TARGET_USERNAME', '')
        target_password = self.get_value_from_workflow('TARGET_PASSWORD', '')
        p = pan_utils.panorama_login(target_ip, target_username, target_password)
        try:
            r = pan_utils.get_vm_auth_key_from_panorama()
        except BaseException:
            print('Could not get vm auth key from panorama')
            messages.add_message(self.request, messages.ERROR, 'Could not contact Panorama!')
            results = dict()
            results['results'] = 'Error, Could not contact Panorama'
            return render(self.request, 'pan_cnc/results.html', context=results)

        matches = re.match('VM auth key (.*?) ', r)
        if matches:
            vm_auth_key = matches[1]
            print(vm_auth_key)
            self.save_value_to_workflow('vm_auth_key', vm_auth_key)
        else:
            print('Could not get VM Auth key from Panorama!')

        return HttpResponseRedirect('include_content')


class BootstrapStep04View(BootstrapWorkflowView):
    title = 'Configure Authentication'
    fields_to_render = ['admin_username', 'admin_password']

    def form_valid(self, form):
        if self.get_value_from_workflow('include_panorama', 'no') == 'no':
            return HttpResponseRedirect('choose_bootstrap')
        else:
            return HttpResponseRedirect('complete')


class ChooseBootstrapXmlView(BootstrapWorkflowView):
    title = 'Include Custom Bootstrap.xml?'
    fields_to_render = []

    def generate_dynamic_form(self):
        dynamic_form = forms.Form()

        # load all templates that report that they are a full panos configuration
        bs_templates = snippet_utils.load_snippets_by_label('template_category', 'panos_full', self.app_dir)

        choices_list = list()
        # grab each bootstrap template and construct a simple tuple with name and label, append to the list
        for bst in bs_templates:
            if bst['name'] == 'upload' or bst['name'] == 'default':
                # do not allow template names that conflict with our choices here
                # do not allow sneaky stuff!
                continue

            choice = (bst['name'], bst['label'])
            choices_list.append(choice)

        # let's sort the list by the label attribute (index 1 in the tuple)
        choices_list = sorted(choices_list, key=lambda k: k[1])
        choices_list.insert(0, ('bootstrap_xml', 'Use Default Bootstrap'))
        choices_list.insert(1, ('upload', 'Upload Custom Bootstrap'))

        dynamic_form.fields['custom_bootstrap'] = forms.ChoiceField(label='Custom Bootstrap',
                                                                    choices=tuple(choices_list))
        return dynamic_form

    def form_valid(self, form):
        """
        Determine if we need a custom bootstrap.xml file uploaded from the user
        since this value is not a service variable in the metadata.yaml file, let's save it
        directly to the workflow manually using save_value_to_workflow here

        called on POST / Form Submit - Dynamic forms are always valid, so this will always be called
        :param form: django Forms.form
        :return: redirect based on input
        """
        cb = self.request.POST.get('custom_bootstrap', '')
        self.save_value_to_workflow('custom_bootstrap', cb)

        if cb == 'upload':
            return HttpResponseRedirect('upload_bootstrap')

        else:
            # custom bootstrap is set to some other value from a snippet
            return HttpResponseRedirect('configure_bootstrap')


class ConfigureBootstrapView(CNCBaseAuth, CNCBaseFormView):
    title = 'Configure Custom Bootstrap'
    header = 'Build bootstrap Archive'
    fields_to_filter = ['hostname', 'FW_NAME']

    def get_snippet(self):
        self.snippet = self.get_value_from_workflow('custom_bootstrap', '')
        print(f'Returning snippet: {self.snippet}')
        return self.snippet

    def form_valid(self, form):
        context = self.get_snippet_context()

        # special case to hide FW_NAME field from iron-skillet
        if 'hostname' in context and 'FW_NAME' in context:
            if context['FW_NAME'] != context['hostname']:
                context['FW_NAME'] = context['hostname']

        bs = snippet_utils.render_snippet_template(self.service, self.app_dir, context)
        if bs is not None:
            bsb = bytes(bs, 'utf-8')
            encoded_bootstrap_string = urlsafe_b64encode(bsb)
            self.save_value_to_workflow('bootstrap_string', encoded_bootstrap_string.decode('utf-8'))

        return HttpResponseRedirect('include_content')


class UploadBootstrapView(BootstrapWorkflowView):
    title = 'Upload Custom Bootstrap.xml'
    fields_to_render = []

    def generate_dynamic_form(self):
        dynamic_form = forms.Form()
        dynamic_form.fields['bootstrap_string'] = forms.CharField(widget=forms.Textarea,
                                                                  label='Bootstrap XML Contents',
                                                                  initial='<xml></xml>')
        return dynamic_form

    def form_valid(self, form):
        bs = self.request.POST.get('bootstrap_string', '')
        if bs != '':
            bsb = bytes(bs, 'utf-8')
            encoded_bootstrap_string = urlsafe_b64encode(bsb)
            self.save_value_to_workflow('bootstrap_string', encoded_bootstrap_string.decode('utf-8'))
        return HttpResponseRedirect('include_content')


class CompleteWorkflowView(BootstrapWorkflowView):
    title = 'License Firewall with Auth Code'
    fields_to_render = ['auth_key']

    def form_valid(self, form):
        context = self.get_snippet_context()

        if 'panorama_ip' not in context and 'TARGET_IP' in context:
            print('Setting panorama ip on context')
            context['panorama_ip'] = context['TARGET_IP']

        print('Compiling init-cfg.txt')
        ic = snippet_utils.render_snippet_template(self.service, self.app_dir, context, 'init_cfg.txt')
        print(ic)
        if ic is not None:
            icb = bytes(ic, 'utf-8')
            encoded_init_cfg_string = urlsafe_b64encode(icb)
            self.save_value_to_workflow('init_cfg_string', encoded_init_cfg_string.decode('utf-8'))

        payload = self.render_snippet_template()

        # get the bootstrapper host and port from the .panrc file, environrment, or default name lookup
        # docker-compose will host bootstrapper under the 'bootstrapper' domain name
        bootstrapper_host = cnc_utils.get_config_value('BOOTSTRAPPER_HOST', 'bootstrapper')
        bootstrapper_port = cnc_utils.get_config_value('BOOTSTRAPPER_PORT', '5000')

        resp = requests.post(f'http://{bootstrapper_host}:{bootstrapper_port}/generate_bootstrap_package',
                             json=json.loads(payload)
                             )
        if 'Content-Type' in resp.headers:
            content_type = resp.headers['Content-Type']
        if 'Content-Disposition' in resp.headers:
            filename = resp.headers['Content-Disposition'].split('=')[1]
        else:
            filename = context.get('hostname')

        print(resp.headers)
        if resp.status_code == 200:
            if 'json' in content_type:
                return_json = resp.json()
                if 'response' in return_json:
                    result_text = return_json["response"]
                else:
                    result_text = resp.text

                results = dict()
                results['results'] = str(resp.status_code)
                results['results'] += '\n'
                results['results'] += result_text
                return render(self.request, 'pan_cnc/results.html', context=results)

            else:
                response = HttpResponse(content_type=content_type)
                response['Content-Disposition'] = 'attachment; filename=%s' % filename
                response.write(resp.content)
                return response
        else:
            results = dict()
            results['results'] = str(resp.status_code)
            results['results'] += '\n'
            results['results'] += resp.text

            return render(self.request, 'pan_cnc/results.html', context=results)
