from django.urls import path

from bootstrapper.views import *

app_name = 'bootstrapper'
urlpatterns = [
    path('', BootstrapWorkflowView.as_view()),
    path('step02', BootstrapStep02View.as_view()),
    path('step03', BootstrapStep03View.as_view()),
    path('step04', BootstrapStep04View.as_view()),

]