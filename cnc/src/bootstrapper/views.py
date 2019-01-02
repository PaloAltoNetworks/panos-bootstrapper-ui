from django import forms
from django.shortcuts import render, HttpResponseRedirect
from base64 import urlsafe_b64encode
from pan_cnc.views import CNCBaseAuth, CNCBaseFormView
from pan_cnc.lib import snippet_utils
from pan_cnc.lib import pan_utils
import re


class BootstrapWorkflowView(CNCBaseAuth, CNCBaseFormView):
    snippet = 'bootstrapper-payload'
    header = 'Build Bootstrap Archive'
    title = 'Deployment Information'
    fields_to_render = ['hostname', 'include_panorama', 'deployment_type']

    def form_valid(self, form):
        if self.get_value_from_workflow('include_panorama', 'no') == 'yes':
            return HttpResponseRedirect('step03')
        else:
            return HttpResponseRedirect('choose_bootstrap')


class BootstrapStep03View(BootstrapWorkflowView):
    title = 'Configure Panorama Server'
    fields_to_render = ['panorama_ip', 'panorama_user', 'panorama_password']

    def form_valid(self, form):
        panorama_ip = self.get_value_from_workflow('panorama_ip', '')
        panorama_user = self.get_value_from_workflow('panorama_user', '')
        panorama_password = self.get_value_from_workflow('panorama_password', '')
        p = pan_utils.panorama_login(panorama_ip, panorama_user, panorama_password)
        r = pan_utils.get_vm_auth_key_from_panorama()
        matches = re.match('VM auth key (.*?) ', r)
        if matches:
            vm_auth_key = matches[1]
            print(vm_auth_key)
            self.save_value_to_workflow('vm_auth_key', vm_auth_key)
        else:
            print('Could not get VM Auth key from Panorama!')

        return HttpResponseRedirect('complete')


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

        return HttpResponseRedirect('complete')


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
        return HttpResponseRedirect('complete')


class CompleteWorkflowView(BootstrapWorkflowView):
    title = 'License Firewall with Auth Code'
    fields_to_render = ['auth_key']

    def form_valid(self, form):
        context = self.get_snippet_context()
        print('Compiling init-cfg.txt')
        ic = snippet_utils.render_snippet_template(self.service, self.app_dir, context, 'init_cfg.txt')
        print(ic)
        if ic is not None:
            icb = bytes(ic, 'utf-8')
            encoded_init_cfg_string = urlsafe_b64encode(icb)
            self.save_value_to_workflow('init_cfg_string', encoded_init_cfg_string.decode('utf-8'))
            
        results = dict()
        if self.app_dir in self.request.session:
            session_cache = self.request.session[self.app_dir]
            for v in session_cache:
                print(f'{v}: {session_cache[v]}')

        results['results'] = self.render_snippet_template()
        return render(self.request, 'pan_cnc/results.html', context=results)
