import re
from base64 import urlsafe_b64encode

import json
import os
import re
import shutil
from base64 import urlsafe_b64encode
from pathlib import Path

import requests
from django import forms
from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, HttpResponseRedirect, HttpResponse
from django.views.generic import RedirectView

from pan_cnc.lib import cnc_utils
from pan_cnc.lib import git_utils
from pan_cnc.lib import pan_utils
from pan_cnc.lib import snippet_utils
from pan_cnc.lib.exceptions import TargetConnectionException
from pan_cnc.views import CNCBaseFormView, CNCView, CNCBaseAuth


class BootstrapWorkflowView(CNCBaseFormView):
    snippet = 'bootstrapper-payload'
    header = 'Build Bootstrap Archive'
    title = 'Deployment Information'
    fields_to_render = ['hostname', 'include_panorama', 'deployment_type']

    def form_valid(self, form):
        deployment_type = self.get_value_from_workflow('deployment_type', '')
        if deployment_type in ['s3', 'azure', 'gcp']:
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
            return HttpResponseRedirect('configure_management')


class DownloadDynamicContentView(CNCBaseFormView):
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

        return HttpResponseRedirect('configure_management')


class GetCloudAuthView(BootstrapWorkflowView):
    title = 'Enter Cloud Auth Information'
    fields_to_render = []

    def generate_dynamic_form(self):
        deployment_type = self.get_value_from_workflow('deployment_type', '')
        if deployment_type == 's3':
            self.fields_to_render += ['aws_key', 'aws_secret', 'aws_location']
        elif deployment_type == 'azure':
            self.fields_to_render += ['azure_storage_account', 'azure_access_key']
        elif deployment_type == 'gcp':
            self.fields_to_render += ['gcp_project_id', 'gcp_access_token']
        return super().generate_dynamic_form()

    def form_valid(self, form):

        deployment_type = self.get_value_from_workflow('deployment_type', '')
        if deployment_type == 's3':
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
        p = pan_utils.panos_login(target_ip, target_username, target_password)
        if p is None:
            results = dict()
            results['results'] = 'Error, Could not contact Panorama'
            return render(self.request, 'pan_cnc/results.html', context=results)
        try:
            r = pan_utils.get_vm_auth_key_from_panorama()
        except TargetConnectionException:
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
            return HttpResponseRedirect('configure_management')


class ConfigureManagementView(BootstrapWorkflowView):
    title = 'Configure Management Connectivity'
    fields_to_render = ['network_type']

    def form_valid(self, form):
        if self.get_value_from_workflow('network_type', 'dhcp-client') == 'dhcp-client':
            return HttpResponseRedirect('complete')
        else:
            return HttpResponseRedirect('configure_management_ip')


class ConfigureManagementStaticView(BootstrapWorkflowView):
    title = 'Configure Management Static IP Address'
    fields_to_render = ['ipv4_mgmt_address', 'ipv4_mgmt_netmask', 'ipv4_default_gateway']

    def form_valid(self, form):
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
        choices_list.insert(0, ('none', 'Do not include a bootstrap'))
        choices_list.insert(1, ('bootstrap_xml', 'Use Default Bootstrap'))
        choices_list.insert(2, ('upload', 'Upload Custom Bootstrap'))

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
        elif cb == 'none':
            self.save_value_to_workflow('bootstrap_string', '')
            return HttpResponseRedirect('include_content')
        else:
            # custom bootstrap is set to some other value from a snippet
            return HttpResponseRedirect('configure_bootstrap')


class ConfigureBootstrapView(CNCBaseFormView):
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
        print(f'Using bootstrapper_host: {bootstrapper_host}')
        print(f'Using bootstrapper_port: {bootstrapper_port}')
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
            results = super().get_context_data()
            results['results'] = str(resp.status_code)
            results['results'] += '\n'
            results['results'] += resp.text

            return render(self.request, 'pan_cnc/results.html', context=results)


class ImportGitRepoView(CNCBaseFormView):
    # define initial dynamic form from this snippet metadata
    snippet = 'import_repo'
    app_dir = 'bootstrapper'
    next_url = '/bootstrapper/repos'

    def get_snippet(self):
        # always return the hard configured snippet
        return self.snippet

    # once the form has been submitted and we have all the values placed in the workflow, execute this
    def form_valid(self, form):
        workflow = self.get_workflow()

        # get the values from the user submitted form here
        url = workflow.get('url')
        branch = workflow.get('branch')
        repo_name = workflow.get('repo_name')
        # FIXME - Ensure repo_name is unique

        # we are going to keep the snippets in the snippets dir in the panhandler app
        # get the dir where all apps are installed
        src_dir = settings.SRC_PATH
        # get the panhandler app dir
        panhandler_dir = os.path.join(src_dir, self.app_dir)
        # get the snippets dir under that
        snippets_dir = os.path.join(panhandler_dir, 'snippets')
        # figure out what our new repo / snippet dir will be
        new_repo_snippets_dir = os.path.join(snippets_dir, repo_name)

        # where to clone from
        clone_url = url
        if 'github' in url.lower():
            details = git_utils.get_repo_upstream_details(repo_name, url)
            if 'clone_url' in details:
                clone_url = details['clone_url']

        if not git_utils.clone_repo(new_repo_snippets_dir, repo_name, clone_url, branch):
            messages.add_message(self.request, messages.ERROR, 'Could not Import Repository')
        else:
            print('Invalidating snippet cache')
            snippet_utils.invalidate_snippet_caches()

            messages.add_message(self.request, messages.INFO, 'Imported Repository Successfully')

        # return render(self.request, 'pan_cnc/results.html', context)
        return HttpResponseRedirect(self.next_url)


class UpdateGitRepoView(CNCBaseAuth, RedirectView):
    next_url = '/bootstrapper/repos'
    app_dir = 'bootstrapper'

    def get_redirect_url(self, *args, **kwargs):
        repo_name = kwargs['repo_name']
        # we are going to keep the snippets in the snippets dir in the panhandler app
        # get the dir where all apps are installed
        src_dir = settings.SRC_PATH
        # get the panhandler app dir
        panhandler_dir = os.path.join(src_dir, self.app_dir)
        # get the snippets dir under that
        snippets_dir = os.path.join(panhandler_dir, 'snippets')
        repo_dir = os.path.join(snippets_dir, repo_name)

        msg = git_utils.update_repo(repo_dir)
        if 'Error' in msg:
            level = messages.ERROR
        else:
            print('Invalidating snippet cache')
            snippet_utils.invalidate_snippet_caches()
            level = messages.INFO

        messages.add_message(self.request, level, msg)
        return self.next_url


class RemoveGitRepoView(CNCBaseAuth, RedirectView):
    next_url = '/bootstrapper/repos'
    app_dir = 'bootstrapper'

    def get_redirect_url(self, *args, **kwargs):
        repo_name = kwargs['repo_name']
        # we are going to keep the snippets in the snippets dir in the panhandler app
        # get the dir where all apps are installed
        src_dir = settings.SRC_PATH
        # get the panhandler app dir
        panhandler_dir = os.path.join(src_dir, self.app_dir)
        # get the snippets dir under that
        snippets_dir = os.path.join(panhandler_dir, 'snippets')
        repo_dir = os.path.abspath(os.path.join(snippets_dir, repo_name))

        if snippets_dir in repo_dir:
            print(f'Removing repo {repo_name}')
            print('Invalidating snippet cache')
            snippet_utils.invalidate_snippet_caches()
            shutil.rmtree(repo_dir)

        messages.add_message(self.request, messages.SUCCESS, 'Repo Successfully Removed')
        return self.next_url


class ListGitReposView(CNCView):
    template_name = 'bootstrapper/repos.html'
    app_dir = 'bootstrapper'

    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)
        snippets_dir = Path(os.path.join(settings.SRC_PATH, self.app_dir, 'snippets'))
        repos = list()
        for d in snippets_dir.rglob('./*'):
            # git_dir = os.path.join(d, '.git')
            git_dir = d.joinpath('.git')
            if git_dir.exists() and git_dir.is_dir():
                print(d)
                repo_name = os.path.basename(d)
                repo_detail = git_utils.get_repo_details(repo_name, d)
                repos.append(repo_detail)
                continue

        context['repos'] = repos
        return context
