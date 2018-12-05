from django import forms
from django.shortcuts import render, HttpResponseRedirect

from pan_cnc.views import CNCBaseAuth, CNCBaseFormView


class BootstrapWorkflowView(CNCBaseFormView):
    snippet = 'bootstrap-payload'
    header = 'Build Bootsrap Archive'
    title = 'Hostname of VM-Series to bootstrap'
    app_dir = 'bootstrapper'
    fields_to_render = ['vm_name']

    def form_valid(self, form):
        return HttpResponseRedirect('step02')


class BootstrapStep02View(BootstrapWorkflowView):
    title = 'Include Panorama Support?'
    fields_to_render = []

    def generate_dynamic_form(self):
        dynamic_form = forms.Form()
        choices_list = (('yes', 'Include Panorama'), ('no', 'Do not include Panorama'))
        dynamic_form.fields['panorama_support'] = forms.ChoiceField(label='Include Panorama',
                                                                    choices=tuple(choices_list))
        return dynamic_form

    def form_valid(self, form):
        if self.request.POST['panorama_support'] == 'yes':
            return HttpResponseRedirect('step03')
        else:
            return HttpResponseRedirect('step04')


class BootstrapStep03View(BootstrapWorkflowView):
    title = 'Configure Panorama Server'
    fields_to_render = ['panorama_ip']

    def form_valid(self, form):
        return HttpResponseRedirect('step04')


class BootstrapStep04View(BootstrapWorkflowView):
    title = 'Configure Authentication'
    fields_to_render = ['admin_username', 'admin_password']

    def form_valid(self, form):
        context = dict()
        if self.app_dir in self.request.session:
            session_cache = self.request.session[self.app_dir]
            for v in session_cache:
                print(v)
                print(session_cache[v])

        context['results'] = self.render_snippet_template()
        return render(self.request, 'bootstrapper/results.html', context=context)
