from django.shortcuts import render

from pan_cnc.lib.actions.DockerAction import DockerAction
from pan_cnc.views import CNCBaseAuth, CNCBaseFormView


class DownloadDynamicContentView(CNCBaseFormView):
    snippet = 'download_dynamic_content'
    header = 'Download Dynamic Content'
    title = 'Choose Package Type to Download'
    app_dir = 'dynamic_content'
    base_html = 'bootstrapper/base.html'

    def form_valid(self, form):
        template = self.render_snippet_template()

        # this shold always be set, but we need to include a variable in the docker cmd line
        # so just ensure it's already there (although it def will, just to keep the 'magic' down a bit)
        if 'package' in self.parsed_context:
            package = self.parsed_context['package']
        else:
            package = 'appthreat'

        docker_action = DockerAction()
        docker_action.docker_image = 'nembery/panos_content_downloader'
        docker_action.docker_cmd = f'/app/content_downloader/content_downloader.py -vv -p {package}'
        docker_action.template_name = 'content_downloader.conf'
        results = docker_action.execute_template(template)

        context = dict()
        context['results'] = results

        return render(self.request, 'base/results.html', context=context)
